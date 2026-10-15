#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-realtrace-ch-v1: 720p closed loop on eight unused cellular trace windows (UCC 4G and Chorus, means 1.2 to 3 Mbit/s) with Johnny and FourPeople.
Deployed system against Python GCC called every 200 ms, 3 runs per arm and cell; criterion as hd720-closedloop-ch-v1 via hd720_ch_eval_v1.judge.
Usage: hd720_realtrace_v1.py jobs | judge | selftest
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-realtrace-ch-v1"); ID = "hd720-realtrace-ch-v1"
PT = D_ / "profiles/hd720_real8"; PROV = json.load(open(PT / "provenance.json"))["profiles"]; CONDS = [f"hd_t{i}" for i in range(1, 9)]
ARMS = AL.ARMS_L; GCC, CH = AL.GCC, AL.CH


def jobs():
    AL.prepare(K); C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []; order = list(ARMS); blk = 0
    for rep in range(1, AL.REPS + 1):
        for cond in CONDS:
            for content in C["main_contents"]:
                rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
                for a in rot:
                    J.append({"cond": f"{cond}__{content}__{a}__r{rep}", "arm": ARMS[a], "profile": str(PT / f"{cond}.profile"), "rep": rep, "video_id": content,
                              "queue": PROV[cond]["queue_packets"], "source": H.source_of(content, layout), "env": dict(AL.ENV[ARMS[a]])})
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_realtrace_sched.log", ly); s["runner"] = str(AL.RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def judge():
    runs, bad = AL.collect(K, set())
    if not AL.audit_ok(K, ID, runs, bad): return
    cells = [f"{c}__{v}" for c in CONDS for v in json.load(open(K / "contents.json"))["main_contents"]]; V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["arm"]), []).append(r["vmaf"])
    v, m = H.judge(V, cells, arm=CH, ref=GCC)
    ba, bc = AL.by_arm_cond(runs, ARMS, CONDS); nv = {a: sum(1 for r in runs if r["arm"] == arm and r.get("valid")) for a, arm in ARMS.items()}
    res = {"verdict": v, **m, "by_arm": ba, "by_cond": bc, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad, "profiles": PROV, "invalid_runs": {r["tag"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_realtrace_ch_v1"; AL.export(K, local, runs, res)
    r1 = lambda x: None if x is None else round(x, 1)
    basis = (f"Primary endpoint D_T (deployed system C-H minus Python GCC called every 200 ms, {m['n_cells_used']} cells equally weighted){AL.fmt(m)}; per cell {json.dumps({c: round(x, 2) for c, x in m['cell_diff'].items()}, ensure_ascii=False)}; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m['all_invalid_cells'] or 'none'}, cells excluded because all GCC runs were invalid: {m['dropped_cells_no_ref'] or 'none'}. Report only: superiority {'reached' if m['superiority_report_only'] else 'not reached'}; per-window VMAF {json.dumps({a: {c: r1(x['vmaf']) for c, x in d.items()} for a, d in bc.items()}, ensure_ascii=False)}; video rate {json.dumps({a: r1(x['video_kbps']) for a, x in ba.items()}, ensure_ascii=False)}; freezes per minute {json.dumps({a: (round(x['file_freeze_per_min'], 2) if x['file_freeze_per_min'] is not None else None) for a, x in ba.items()}, ensure_ascii=False)}; mean queueing delay {json.dumps({a: r1(x['queue_delay_mean_ms']) for a, x in ba.items()}, ensure_ascii=False)} milliseconds; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    lim = ("The system under test is C-H with the 5 kbps floor and probing envelope v6; 8 previously unused cellular trace windows (6 UCC 4G stationary, 1 Chorus driving and 1 high-speed rail, mean 1.5 to 2.9 Mbit/s, sampled with a fixed seed), two 720p talking-head sequences (Johnny, FourPeople); libwebrtc default maximum bitrate 2.5 Mbps for 960x540 and above; single-machine testbed, sender egress shaping, one-way delay 50 ms, no random packet loss; 3 runs per cell; run script v20.")
    AL.register(ID, v, m, basis, "Criterion as pre-registered (verbatim the same as hd720-closedloop-ch-v1: non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid).", lim,
                "", K, local, nv, ROOT / "logs/hd720_realtrace_sched.log")


def selftest():
    H.selftest(); assert len(CONDS) == 8 and all((PT / f"{c}.profile").is_file() for c in CONDS); print("Self-test passed: judge; 8 trace profiles present")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest}[sys.argv[1]]()
