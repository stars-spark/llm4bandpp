#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testbed freeze floor (hd720-freeze-floor-v1, measurement only, no verdict): does the single-machine testbed itself
cause freezes? Fixed-estimate calibration as in hb_calib_v2, with media capture on: a 20 Mb/s link
(profiles/hd720/hd_cal20, queue 521 packets) and a fixed receiver estimate (fixed_env) of 3 Mb/s with the default 720p
sender cap (2.5 Mb/s), or 18 Mb/s with the high-bitrate sender (STALENESS_HIGH_BITRATE=1). Johnny and FourPeople, three
runs each, 12 runs on one container pair, run script v24. The link is wider than the send rate, so queueing and loss stay near zero
and any freeze is the testbed's own floor. Reported per cell (mean and range): freezes per minute (file-growth definition,
as in the other batches), W3C freezes per minute, mean freeze duration, VMAF, video rate, loss, mean queueing delay,
decoded frame rate, and receiver and sender container CPU.
Subcommands: jobs, judge, selftest.
"""
import json, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
import hd720_run_metrics_v1 as RM  # noqa: E402
K = Path("/path/to/testbed/results/hd720-freeze-floor-v1"); ID = "hd720-freeze-floor-v1"; LOCAL = ROOT / "experiments/results/hd720_freeze_floor_v1"
RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v24.sh"
MODES = {"cap25": {"BWE_RECEIVER_FIXED_BPS": "3000000"}, "hb": {"BWE_RECEIVER_FIXED_BPS": "18000000", "STALENESS_HIGH_BITRATE": "1"}}
CONTENTS = ["johnny", "fourpeople"]; REPS = 3
CEIL = {"cap25": None, "hb": {"johnny": 12124.2, "fourpeople": 16058.4}}
FIELDS = ("file_freeze_per_min", "webrtc_NumberFreezesPerMinute", "webrtc_MeanFreezeDurationMs", "vmaf", "video_kbps", "loss_rate", "queue_delay_mean_ms", "decoded_fps", "rendered_fps")


def jobs():
    AL.prepare(K); C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []
    for rep in range(1, REPS + 1):
        for mode, env in MODES.items():
            for c in CONTENTS:
                J.append({"cond": f"cal20__{c}__{mode}__r{rep}", "arm": "fixed_env", "profile": str(H.P / "hd_cal20.profile"), "rep": rep, "video_id": c, "queue": 521,
                          "source": H.source_of(c, layout), "env": dict(env)})
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_freeze_floor_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def cpu_of(d):
    """Means of host_busy_pct and of each process role's cpu_pct over the cpu_*.jsonl samples of a run directory; samples without the role are skipped."""
    host, roles = [], {}
    for p in d.glob("cpu_*.jsonl"):
        for l in open(p):
            if not l.strip(): continue
            r = json.loads(l)
            if isinstance(r.get("host_busy_pct"), (int, float)): host.append(r["host_busy_pct"])
            for k, v in (r.get("roles") or {}).items():
                if isinstance(v.get("cpu_pct"), (int, float)): roles.setdefault(k, []).append(v["cpu_pct"])
    out = {"host_busy_pct": st.mean(host)} if host else {}
    out.update({f"{k}_cpu_pct": st.mean(x) for k, x in roles.items()})
    return out


def collect():
    s = json.load(open(K / "main" / "jobs.json")); ceil = json.load(open(K / "ceilings.json"))["ceiling_kbps"]; runs = []
    for j in s["jobs"]:
        d = K / "main" / j["cond"]; tag = f"{j['arm']}__hd_cal20__d0__r{j['rep']}__v{j['video_id']}"; mode = j["cond"].split("__")[2]
        if not d.is_dir(): runs.append({"job": j["cond"], "mode": mode, "video_id": j["video_id"], "valid": False, "invalid_reasons": ["Missing run directory"]}); continue
        cap = (CEIL[mode] or ceil)[j["video_id"]]
        r = RM.run_metrics(d, tag, j["arm"], "hd_cal20", cap); r.update(job=j["cond"], mode=mode, video_id=j["video_id"], cpu=cpu_of(d)); runs.append(r)
    bad = []
    for m in MODES: bad += RM.code_audit([r for r in runs if r.get("mode") == m and "tag" in r])
    return runs, bad


def summarize(runs):
    out = {}
    for mode in MODES:
        for c in CONTENTS:
            rs = [r for r in runs if r["mode"] == mode and r["video_id"] == c and r.get("valid")]
            cell = {"n_valid": len(rs)}
            for f in FIELDS:
                xs = [r[f] for r in rs if isinstance(r.get(f), (int, float))]
                cell[f] = None if not xs else {"mean": st.mean(xs), "min": min(xs), "max": max(xs)}
            ck = sorted({k for r in rs for k in r.get("cpu", {})})
            cell["cpu"] = {k: st.mean([r["cpu"][k] for r in rs if k in r.get("cpu", {})]) for k in ck}
            out[f"{mode}__{c}"] = cell
    return out


def selftest():
    runs = [{"mode": "cap25", "video_id": "johnny", "valid": True, "file_freeze_per_min": x, "vmaf": 80.0, "cpu": {"recv": 10.0}} for x in (0.0, 1.0, 2.0)] + \
           [{"mode": "cap25", "video_id": "johnny", "valid": False, "file_freeze_per_min": 99.0}]
    s = summarize(runs)["cap25__johnny"]
    assert s["n_valid"] == 3 and s["file_freeze_per_min"]["mean"] == 1.0 and s["file_freeze_per_min"]["max"] == 2.0 and s["cpu"] == {"recv": 10.0}
    assert set(MODES) == {"cap25", "hb"} and MODES["hb"]["STALENESS_HIGH_BITRATE"] == "1" and "STALENESS_HIGH_BITRATE" not in MODES["cap25"]
    print("Self-test passed: per-cell means and ranges, invalid runs not counted, CPU summary; both ceiling settings match")


def judge():
    runs, bad = collect()
    if not AL.audit_ok(K, ID, runs, bad): return
    summ = summarize(runs); res = {"cells": summ, "n_runs": len(runs), "bad_hash": bad, "invalid_runs": {r["job"]: r.get("invalid_reasons") for r in runs if not r.get("valid")}}
    LOCAL.mkdir(parents=True, exist_ok=True); (LOCAL / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str)); (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs_full.jsonl", "w") as f:
        for r in runs: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    r2 = lambda x: None if x is None else round(x, 2)
    g = lambda cell, f: None if cell[f] is None else f"{r2(cell[f]['mean'])} ({r2(cell[f]['min'])} to {r2(cell[f]['max'])})"
    basis = ";".join(f"{k}: valid {v['n_valid']}/3, freezes per minute {g(v, 'file_freeze_per_min')}, W3C freezes per minute {g(v, 'webrtc_NumberFreezesPerMinute')}, VMAF {g(v, 'vmaf')}, video {g(v, 'video_kbps')} kbit/s, loss {g(v, 'loss_rate')}, queueing {g(v, 'queue_delay_mean_ms')} ms, CPU {json.dumps({c: r2(x) for c, x in v['cpu'].items()}, ensure_ascii=False)}"
                      for k, v in summ.items()) + "."
    print(basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: {f: (v[f]["mean"] if v[f] else None) for f in ("file_freeze_per_min", "vmaf", "video_kbps")} for k, v in summ.items()}, ensure_ascii=False),
       "--artifact", str(LOCAL / "result_v1.json"))
    nval = sum(v["n_valid"] for v in summ.values())
    ex("conclude", "--id", ID, "--verdict", "holds" if nval >= 10 else "inconclusive", "--vs-criteria", "Measurement only, no verdict; \"holds\" only means that at least 10 of the 12 runs are valid and all readings are present." + basis, "--basis", basis,
       "--limitations", "Fixed estimate, 20 Mbit/s link, one-way delay 50 ms; two talking-head sequences; 3 runs per cell; single-machine testbed; run script v24.", "--next", "")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest}[sys.argv[1]]()
