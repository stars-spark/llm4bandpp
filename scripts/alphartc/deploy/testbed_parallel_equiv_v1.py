#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for batch testbed-parallel-equiv-v1: tests whether the parallel testbed gives the same results as serial runs of run script v10.
A: the original pair runs ev_1 to ev_3 serially; B: four new pairs run each window 4 times in parallel with background scoring; C: the original pair repeats A after the scoring pool drains. All runs are arm_default_schema without a synthetic schema, with media capture.
Usage: testbed_parallel_equiv_v1.py jobs | judge [--selftest]
"""
import json, statistics as st, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/testbed-parallel-equiv-v1"); ID = "testbed-parallel-equiv-v1"
P = ROOT / "scripts/alphartc/deploy/profiles/obsrepair_cl"; V9 = Path("/path/to/alphartc/LLM4Band/result/staleness/obsrepair-cl-screen-v1"); WINS = ["ev_1", "ev_2", "ev_3"]
COMMON = {"STALENESS_POLICY": "v2", "STALENESS_COLLECTOR": "v6", "STALENESS_OBS_TRACE": "1", "STALENESS_CONTROL_SLACK_S": "80", "STALENESS_CAPTURE_MEDIA": "1",
          "STALENESS_SOURCE_FILE": "testmedia/qoe_labeled_medium_320x240.yuv", "STALENESS_SOURCE_FPS": "15", "STALENESS_SOURCE_WIDTH": "320", "STALENESS_SOURCE_HEIGHT": "240",
          "STALENESS_ADAPT_MODEL": "/app/model/adapt_v2/adapt_mlp.npz"}
ARM = "arm_default_schema"


def jobs():
    J = [{"phase": "A", "cond": f"A__{w}", "arm": ARM, "profile": str(P / f"{w}.profile")} for w in WINS]
    order = ["ev_1", "ev_2", "ev_3", "ev_1", "ev_2", "ev_3", "ev_1", "ev_2", "ev_3", "ev_1", "ev_2", "ev_3"]; cnt = {}
    for w in order: cnt[w] = cnt.get(w, 0) + 1; J.append({"phase": "B", "cond": f"B__{w}__{cnt[w]}", "arm": ARM, "profile": str(P / f"{w}.profile")})
    J += [{"phase": "C", "cond": f"C__{w}", "arm": ARM, "profile": str(P / f"{w}.profile")} for w in WINS]
    spec = {"name": ID, "K": str(K), "log": str(ROOT / "logs/testbed_parallel_equiv_v1.log"), "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v10.sh"),
            "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 3, "max_pending": 6, "stagger_s": 7, "common_env": COMMON,
            "phases": [{"name": "A", "pairs": ["canon"], "vmaf": "defer"}, {"name": "B", "pairs": [1, 2, 3, 4], "vmaf": "async"}, {"name": "C", "pairs": ["canon"], "vmaf": "defer", "drain_before": True}], "jobs": J}
    K.mkdir(parents=True, exist_ok=True); (K / "jobs.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def judge(R, v9dur):
    """Return (verdict, metrics) from R[cond] (valid, U, vmaf, dur, applies, cp95, gp95, wait) and v9dur, the reference clean-run durations per window."""
    S = {c: r for c, r in R.items() if c[0] in "AC"}; B = {c: r for c, r in R.items() if c[0] == "B"}; win = lambda c: "ev_" + c.split("__")[1].split("_")[1]
    c1 = len(R) == 18 and all(r["valid"] for r in R.values())
    b_only_invalid = any(not r["valid"] for r in B.values()) and all(r["valid"] for r in S.values())
    c2 = all(r["valid"] and abs(r["dur"] - v9dur[win(c)]) <= 2 and r["applies"] == 120 for c, r in S.items())
    vs = [r for r in S.values() if r["valid"]]; vb = [r for r in B.values() if r["valid"]]
    med = lambda rs, k: st.median([r[k] for r in rs]) if rs else float("nan")
    c3 = bool(vs and vb) and med(vb, "cp95") <= 1.5 * med(vs, "cp95") and max(r["cp95"] for r in vb) <= 20 and med(vb, "gp95") <= 1.2 * med(vs, "gp95") and all(r["applies"] == 120 for r in vb)
    d, dv = {}, {}
    for w in WINS:
        us = [r["U"] for c, r in S.items() if r["valid"] and win(c) == w]; ub = [r["U"] for c, r in B.items() if r["valid"] and win(c) == w]
        qs = [r["vmaf"] for c, r in S.items() if r["valid"] and win(c) == w and r["vmaf"] is not None]; qb = [r["vmaf"] for c, r in B.items() if r["valid"] and win(c) == w and r["vmaf"] is not None]
        d[w] = float(np.mean(ub) - np.mean(us)) if us and ub else float("nan"); dv[w] = float(np.mean(qb) - np.mean(qs)) if qs and qb else float("nan")
    md, mdv = float(np.mean(list(d.values()))), float(np.mean(list(dv.values())))
    c4 = abs(md) <= 1.5 and max(abs(x) for x in d.values()) <= 3 and abs(mdv) <= 3
    if c1 and c2 and c3 and c4: v = "holds"
    elif b_only_invalid or not c2 or not c3 or not abs(md) <= 3 or not abs(mdv) <= 5: v = "does not hold"
    else: v = "inconclusive"
    return v, {"c1_all_valid": c1, "c2_call_unchanged_vs_v9": c2, "c3_timing": c3, "c4_outcome": c4, "dU_by_window": d, "dU_mean": md, "dVMAF_by_window": dv, "dVMAF_mean": mdv,
               "cp95_serial_median": med(vs, "cp95"), "cp95_parallel_median": med(vb, "cp95"), "cp95_parallel_max": max((r["cp95"] for r in vb), default=float("nan")),
               "gp95_serial_median": med(vs, "gp95"), "gp95_parallel_median": med(vb, "gp95"), "wait_s_serial": [r["wait"] for r in vs], "n_valid": sum(r["valid"] for r in R.values())}


def selftest():
    base = lambda u: {"valid": True, "U": u, "vmaf": 70.0, "dur": 129.0, "applies": 120, "cp95": 9.0, "gp95": 199.0, "wait": 12}
    mk = lambda ub, **kw: {**{f"A__{w}": base(80) for w in WINS}, **{f"C__{w}": base(80.4) for w in WINS}, **{f"B__{w}__{i}": {**base(ub), **kw} for w in WINS for i in range(1, 5)}}
    v9 = {w: 129.0 for w in WINS}
    assert judge(mk(80.5), v9)[0] == "holds"
    assert judge(mk(80.5, cp95=30.0), v9)[0] == "does not hold"
    assert judge(mk(76.0), v9)[0] == "does not hold"
    assert judge(mk(78.3), v9)[0] == "inconclusive"
    R = mk(80.5); R["A__ev_1"]["dur"] = 190.0; assert judge(R, v9)[0] == "does not hold"
    R = mk(80.5); R["B__ev_2__3"]["valid"] = False; assert judge(R, v9)[0] == "does not hold"
    print("Equivalence verdict self-test passed (holds, three kinds of does not hold, inconclusive, parallel-only invalid)")


def collect():
    R = {}
    for d in sorted(K.glob("[ABC]__*")):
        js = d / f"{ARM}__{d.name.split('__')[1]}__d0__r1.json"; q = d / f"quality_{ARM}__{d.name.split('__')[1]}__d0__r1.json"; ok = js.is_file() and not list(d.glob("invalid_*"))
        r = {"valid": False}
        if ok:
            j = json.load(open(js)); vm = json.load(open(q)).get("vmaf") if q.is_file() else None; log = (d / "runner.log").read_text(errors="ignore")
            wait = next((int(x.split("wait ")[1].split("s")[0]) for x in log.splitlines() if x.startswith("v10 call exit wait")), None)
            r = {"valid": vm is not None, "U": j["network"]["utility"], "vmaf": vm, "dur": j["measurement"]["duration_s"], "applies": j["controls"]["n_applies"],
                 "cp95": j["decisions"]["compute_p95_ms"], "gp95": j["decisions"]["decision_gap_p95_ms"], "wait": wait, "pair": json.load(open(d / "run_meta.json")).get("pair")}
        R[d.name] = r
    v9dur = {w: json.load(open(V9 / f"{w}__CLEAN" / f"arm_default_repair__{w}__d0__r1.json"))["measurement"]["duration_s"] for w in WINS}
    return R, v9dur


def main():
    R, v9dur = collect(); v, m = judge(R, v9dur); m["v9_duration"] = v9dur; m["runs"] = R
    (K / "result_v1.json").write_text(json.dumps({"verdict": v, **m}, ensure_ascii=False, indent=1))
    basis = (f"valid {m['n_valid']}/18; serial call duration matches v9 {m['c2_call_unchanged_vs_v9']} (v10 idle-waits {m['wait_s_serial']} seconds); estimator computation 95th percentile serial median {m['cp95_serial_median']:.1f}, parallel median {m['cp95_parallel_median']:.1f}, parallel maximum {m['cp95_parallel_max']:.1f} milliseconds; decision interval 95th percentile serial {m['gp95_serial_median']:.0f}, parallel {m['gp95_parallel_median']:.0f} milliseconds; utility parallel minus serial per window {', '.join(f'{k} {x:+.2f}' for k, x in m['dU_by_window'].items())}, mean {m['dU_mean']:+.2f}; video quality mean {m['dVMAF_mean']:+.2f}.")
    print(v, basis); (K / "decision.txt").write_text("pairs" if v == "holds" else "canon")
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m[k] for k in m if k != "runs"}, ensure_ascii=False), "--artifact", str(K / "result_v1.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered." + basis, "--basis", basis, "--limitations", "Three windows, 6 serial runs versus 12 parallel runs; only the arm with the challenge baseline behind the probing envelope is tested.",
       "--next", "")


if __name__ == "__main__":
    {"jobs": jobs, "judge": lambda: selftest() if "--selftest" in sys.argv else main()}[sys.argv[1]]()
