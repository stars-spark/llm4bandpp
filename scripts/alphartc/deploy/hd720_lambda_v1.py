#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-lambda-ch-v1: deployed system with the λ 0.8 checkpoint (l08) against the deployed λ 0.4 (l04) on the hd720-closedloop-ch-v1 cells.
Main endpoint: l08 minus l04 VMAF over 12 cells, criterion via hd720_ch_eval_v1.judge (non-inferiority margin 6 VMAF). Both arms run arm_ch_x and are told apart by the arm key in the job name.
Usage: hd720_lambda_v1.py jobs | judge | selftest
"""
import json, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-lambda-ch-v1"); ID = "hd720-lambda-ch-v1"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v23.sh"
CONDS = list(H.CONDS); CH = AL.CH
ARMKEYS = {"l04": (CH, dict(AL.ENV[CH])), "l08": (CH, dict(AL.ENV[CH], STALENESS_CH_CHECKPOINT="/app/model/ch_v1/ch_l08s1.pt"))}


def jobs():
    AL.prepare(K); C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []; order = list(ARMKEYS); blk = 0
    for rep in range(1, AL.REPS + 1):
        for cond in CONDS:
            for content in C["main_contents"]:
                rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
                for a in rot:
                    arm, env = ARMKEYS[a]
                    J.append({"cond": f"{cond}__{content}__{a}__r{rep}", "arm": arm, "profile": str(H.P / f"{cond}.profile"), "rep": rep, "video_id": content,
                              "queue": H.queue_of(cond), "source": H.source_of(content, layout), "env": dict(env)})
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_lambda_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def build_V(runs):
    V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["job"].split("__")[2]), []).append(r["vmaf"])
    return V


def selftest():
    H.selftest()
    runs = [{"valid": True, "vmaf": 70.0 + i, "job": f"hd_c1__johnny__{k}__r1", "cond": "hd_c1", "video_id": "johnny"} for i, k in enumerate(("l04", "l08"))]
    V = build_V(runs); assert V[("hd_c1__johnny", "l04")] == [70.0] and V[("hd_c1__johnny", "l08")] == [71.0], V
    assert ARMKEYS["l04"][1].get("STALENESS_CH_CHECKPOINT") is None and ARMKEYS["l08"][1]["STALENESS_CH_CHECKPOINT"].endswith("ch_l08s1.pt")
    print("Self-test passed: judge, arm keys; l04 loads the deployed ch.pt")


def judge():
    runs, bad = AL.collect(K, set())
    if not AL.audit_ok(K, ID, runs, bad): return
    cells = [f"{c}__{v}" for c in CONDS for v in json.load(open(K / "contents.json"))["main_contents"]]; V = build_V(runs)
    v, m = H.judge(V, cells, arm="l08", ref="l04")
    key = lambda r: r["job"].split("__")[2]
    agg = lambda rs, f: (lambda xs: sum(xs) / len(xs) if xs else None)([r[f] for r in rs if r.get("valid") and r.get(f) is not None])
    ba = {k: {f: agg([r for r in runs if key(r) == k], f) for f in ("vmaf", "ssim", "file_freeze_per_min", "video_kbps", "envelope_rewrite_frac")} for k in ARMKEYS}
    bc = {k: {c: {f: agg([r for r in runs if key(r) == k and r["cond"] == c], f) for f in ("vmaf", "file_freeze_per_min", "video_kbps")} for c in CONDS} for k in ARMKEYS}
    nv = {k: sum(1 for r in runs if r.get("valid") and key(r) == k) for k in ARMKEYS}
    res = {"verdict": v, **m, "by_armkey": ba, "by_armkey_cond": bc, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad, "invalid_runs": {r["job"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_lambda_ch_v1"; AL.export(K, local, runs, res)
    r1 = lambda x: None if x is None else round(x, 1); r2 = lambda x: None if x is None else round(x, 2)
    basis = (f"Primary endpoint D_L (λ 0.8 minus λ 0.4, both in the deployed system with seed 1, {m['n_cells_used']} cells equally weighted) {AL.fmt(m)}; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all λ 0.8 runs invalid {m['all_invalid_cells'] or 'none'}, cells excluded because all λ 0.4 runs were invalid {m['dropped_cells_no_ref'] or 'none'}. Report only: superiority {'reached' if m['superiority_report_only'] else 'not reached'}; per-condition VMAF {json.dumps({k: {c: r1(x['vmaf']) for c, x in d.items()} for k, d in bc.items()}, ensure_ascii=False)}; per-condition freezes per minute {json.dumps({k: {c: r2(x['file_freeze_per_min']) for c, x in d.items()} for k, d in bc.items()}, ensure_ascii=False)}; video rate {json.dumps({k: r1(x['video_kbps']) for k, x in ba.items()}, ensure_ascii=False)}; probing envelope rewrite fraction {json.dumps({k: r2(x['envelope_rewrite_frac']) for k, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    lim = ("λ 0.8 seed 1 is one cell of ch-lambda-sweep-v1 (offline macro MSE about 5.45), weights verified by the CPU equivalence check on gpu-server-1; both arms are C-H with the 5 kbps floor and probing envelope v6; conditions and sequences as in hd720-closedloop-ch-v1; libwebrtc default max bitrate 2.5 Mbps for 960x540 and above; single-machine testbed; 3 runs per cell; single seed; run script v23.")
    AL.register(ID, v, m, basis, "Criterion as pre-registered (verbatim the same as hd720_ch_eval_v1.judge of hd720-closedloop-ch-v1: non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid; the reference arm is λ 0.4).", lim,
                "", K, local, nv, ROOT / "logs/hd720_lambda_sched.log")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest}[sys.argv[1]]()
