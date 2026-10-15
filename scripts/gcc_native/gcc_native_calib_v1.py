#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summary for registered batch gcc-native-calib-v1 (measurement, no verdict): native libwebrtc GCC in Chrome loopback at 1000 and 2000 kbit/s, 720p Johnny, against the Python GCC and deployed-estimator runs of hd720-closedloop-ch-v1 on hd_c1 and hd_c2.
Per run over 20 to 70 s: median received video rate, median native GCC estimate (availableOutgoingBitrate), time to reach 0.8 of capacity and freezes per minute; reports link utilization per level and the native-minus-Python gap.
Usage: gcc_native_calib_v1.py [--selftest]
"""
import json, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); RUNS = Path("/path/to/testbed/results/gcc-native-calib-v1/runs"); ID = "gcc-native-calib-v1"
LOCAL = ROOT / "experiments/results/gcc_native_calib_v1"; CAPS = {1000: "hd_c1", 2000: "hd_c2"}; T0, T1 = 20.0, 70.0


def reach(ts, ks, cap, frac=0.8, win=2.0):
    """Return the first time the 2 s moving average reaches frac x capacity, or None if it never does."""
    for i, t in enumerate(ts):
        w = [k for tt, k in zip(ts, ks) if t - win < tt <= t]
        if w and st.mean(w) >= frac * cap: return t
    return None


def native_run(d, cap):
    rows = [json.loads(l) for l in open(d / "stats.jsonl") if l.strip()]
    rec = [(r["t"], next((x for x in r.get("rows", []) if x["side"] == "recv" and x["type"] == "inbound-rtp"), None),
            next((x for x in r.get("rows", []) if x["type"] == "candidate-pair"), None)) for r in rows if "t" in r]
    ts, kb, est, fz = [], [], [], None
    for (t0, a, _), (t1, b, cp) in zip(rec, rec[1:]):
        if a and b and b.get("bytesReceived") is not None and a.get("bytesReceived") is not None and t1 > t0:
            ts.append(t1); kb.append((b["bytesReceived"] - a["bytesReceived"]) * 8 / 1000 / (t1 - t0))
        if cp and cp.get("availableOutgoingBitrate") and T0 <= t1 <= T1: est.append(cp["availableOutgoingBitrate"] / 1000)
        if b and b.get("freezeCount") is not None: fz = b["freezeCount"]
    sel = [k for t, k in zip(ts, kb) if T0 <= t <= T1]
    dur = (ts[-1] - ts[0]) / 60 if len(ts) > 1 else None
    return {"rate_med_kbps": st.median(sel) if sel else None, "util": (st.median(sel) / cap) if sel else None, "est_med_kbps": st.median(est) if est else None,
            "t_reach80_s": reach(ts, kb, cap), "freeze_per_min": (fz / dur) if (fz is not None and dur) else None, "n_samples": len(ts)}


def testbed_runs():
    rows = [json.loads(l) for l in open(ROOT / "experiments/results/hd720_closedloop_ch_v1/runs_full.jsonl")]; out = {}
    for r in rows:
        if not r.get("valid") or r.get("video_id") != "johnny" or r.get("cond") not in CAPS.values(): continue
        cap = next(c for c, n in CAPS.items() if n == r["cond"]); s = r.get("video_kbps_per_s") or []
        sel = s[int(T0):int(T1)]; ts = list(range(1, len(s) + 1))
        out.setdefault((r["arm"], cap), []).append({"rate_med_kbps": st.median(sel) if sel else None, "util": (st.median(sel) / cap) if sel else None,
                                                    "t_reach80_s": reach(ts, s, cap), "freeze_per_min": r.get("file_freeze_per_min")})
    return out


def agg(xs, k):
    v = [x[k] for x in xs if x.get(k) is not None]
    return None if not v else {"mean": st.mean(v), "min": min(v), "max": max(v), "n": len(v)}


def selftest():
    assert reach([1, 2, 3, 4], [100, 900, 900, 900], 1000) == 3 and reach([1, 2], [100, 100], 1000) is None
    print("Self-test passed: arrival time")


def main():
    N = {}
    for d in sorted(RUNS.iterdir()):
        if d.is_dir() and (d / "OK").exists():
            cap = int(d.name.split("_")[0][1:]); N.setdefault(cap, []).append(native_run(d, cap))
    T = testbed_runs()
    res = {"native": {c: {k: agg(v, k) for k in ("util", "rate_med_kbps", "est_med_kbps", "t_reach80_s", "freeze_per_min")} for c, v in N.items()},
           "testbed": {f"{a}@{c}": {k: agg(v, k) for k in ("util", "rate_med_kbps", "t_reach80_s", "freeze_per_min")} for (a, c), v in T.items()}}
    LOCAL.mkdir(parents=True, exist_ok=True); (LOCAL / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    r2 = lambda x: None if x is None else round(x, 2)
    f = lambda d: None if d is None else f"{r2(d['mean'])} ({r2(d['min'])} to {r2(d['max'])}, n={d['n']})"
    basis = ";".join([f"Native GCC {c} kbit/s: utilization {f(v['util'])}, estimated median {f(v['est_med_kbps'])} kbit/s, time to reach 0.8 capacity {f(v['t_reach80_s'])} seconds, freezes per minute {f(v['freeze_per_min'])}" for c, v in sorted(res["native"].items())] +
                      [f"Testbed {k}: utilization {f(v['util'])}, reaching 0.8 capacity in {f(v['t_reach80_s'])} seconds" for k, v in sorted(res["testbed"].items())]) + "."
    print(basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    nok = sum(len(v) for v in N.values())
    ex("data", "--id", ID, "--metrics", json.dumps({str(c): r2(v["util"]["mean"]) if v["util"] else None for c, v in res["native"].items()}, ensure_ascii=False), "--artifact", str(LOCAL / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", "holds" if nok >= 5 else "inconclusive", "--vs-criteria", "Measurement only, no verdict; \"holds\" here means only that at least 5 of the 6 runs are valid." + basis, "--basis", basis,
       "--limitations", "Chrome loopback call, netem rate limit and delay on loopback apply in both directions (round trip about 100 ms, the testbed is 50 ms one way at the sender egress); the encoder is Chrome's VP8 rather than AlphaRTC's; the testbed reading is an existing run of hd720-closedloop-ch-v1, a different batch; only rate utilization and ramp-up are compared, not video quality.",
       "--next", "")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
