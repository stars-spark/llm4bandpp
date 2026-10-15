#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-seeds-ch-v1: tests whether the 720p result depends on the training seed of the deployed estimator.
Arms: Python GCC called every 200 ms and the deployed system with the seed 0 and seed 2 checkpoints. Main endpoint: pooled seed 0 and 2 VMAF minus GCC over the 12 hd720-closedloop-ch-v1 cells, criterion via hd720_ch_eval_v1.judge (non-inferiority margin 6).
Usage: hd720_seeds_v1.py jobs | judge | selftest
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-seeds-ch-v1"); ID = "hd720-seeds-ch-v1"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v21.sh"
CONDS = list(H.CONDS); GCC, CH = AL.GCC, AL.CH
ARMKEYS = {"gcc200": (GCC, {}), "s0": (CH, dict(AL.ENV[CH], STALENESS_CH_CHECKPOINT="/app/model/ch_v1/ch_s0.pt")), "s2": (CH, dict(AL.ENV[CH], STALENESS_CH_CHECKPOINT="/app/model/ch_v1/ch_s2.pt"))}


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
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_seeds_sched.log", ly); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def build_V(runs, cells):
    """Build V[(cell, arm key)] from valid runs and add the pooled arm seeds = s0 plus s2."""
    V = {}
    for r in runs:
        if not (r.get("valid") and r.get("vmaf") is not None): continue
        key = r["job"].split("__")[2]; cell = f"{r['cond']}__{r['video_id']}"
        V.setdefault((cell, key), []).append(r["vmaf"])
        if key in ("s0", "s2"): V.setdefault((cell, "seeds"), []).append(r["vmaf"])
    return V


def selftest():
    H.selftest()
    runs = [{"valid": True, "vmaf": 70.0 + i, "job": f"hd_c1__johnny__{k}__r1", "cond": "hd_c1", "video_id": "johnny"} for i, k in enumerate(("gcc200", "s0", "s2"))]
    V = build_V(runs, ["hd_c1__johnny"]); assert V[("hd_c1__johnny", "seeds")] == [71.0, 72.0] and V[("hd_c1__johnny", "gcc200")] == [70.0], V
    print("Self-test passed: judge; seeds told apart by arm key and pooled")


def judge():
    runs, bad = AL.collect(K, set())
    if not AL.audit_ok(K, ID, runs, bad): return
    cells = [f"{c}__{v}" for c in CONDS for v in json.load(open(K / "contents.json"))["main_contents"]]; V = build_V(runs, cells)
    v, m = H.judge(V, cells, arm="seeds", ref="gcc200"); m0 = H.judge(V, cells, arm="s0", ref="gcc200")[1]; m2 = H.judge(V, cells, arm="s2", ref="gcc200")[1]
    key = lambda r: r["job"].split("__")[2]
    agg = lambda k, f: (lambda xs: sum(xs) / len(xs) if xs else None)([r[f] for r in runs if r.get("valid") and key(r) == k and r.get(f) is not None])
    ba = {k: {f: agg(k, f) for f in ("vmaf", "ssim", "file_freeze_per_min", "video_kbps", "envelope_rewrite_frac")} for k in ARMKEYS}
    nv = {k: sum(1 for r in runs if r.get("valid") and key(r) == k) for k in ARMKEYS}
    res = {"verdict": v, **m, "seed0_vs_gcc": m0, "seed2_vs_gcc": m2, "by_armkey": ba, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad, "invalid_runs": {r["job"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_seeds_ch_v1"; AL.export(K, local, runs, res)
    r1 = lambda x: None if x is None else round(x, 1)
    basis = (f"Primary endpoint D_S (seeds 0 and 2 pooled minus Python GCC called every 200 ms, {m['n_cells_used']} cells equally weighted) {AL.fmt(m)}; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all runs of the pooled arm invalid {m['all_invalid_cells'] or 'none'}, cells excluded because all GCC runs were invalid: {m['dropped_cells_no_ref'] or 'none'}. Report only: seed 0 versus GCC {AL.fmt(m0)}; seed 2 versus GCC {AL.fmt(m2)}; deployed seed 1 in earlier batches: +4.58 (hd720-closedloop-ch-v1) and +4.38 (hd720-echo-attr-ch-v1); average VMAF {json.dumps({k: r1(x['vmaf']) for k, x in ba.items()}, ensure_ascii=False)}; freezes per minute {json.dumps({k: (round(x['file_freeze_per_min'], 2) if x['file_freeze_per_min'] is not None else None) for k, x in ba.items()}, ensure_ascii=False)}; video rate {json.dumps({k: r1(x['video_kbps']) for k, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    lim = ("seeds 0 and 2 are the other two seeds of the C-H cell of ablation-nl-enc-hcq-2x2-v1 (offline macro MSE 5.868 and 5.792), and the weights passed the CPU equivalence check on gpu-server-1; the deployed system is C-H with the 5 kbps floor and probing envelope v6; conditions and sequences as in hd720-closedloop-ch-v1; libwebrtc defaults to a maximum bitrate of 2.5 Mbps above 960x540; single-machine testbed; 3 runs per cell; run script v21.")
    AL.register(ID, v, m, basis, "Criterion as pre-registered (after merging the two seeds, verbatim the same as hd720-closedloop-ch-v1: non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid).", lim,
                "", K, local, nv, ROOT / "logs/hd720_seeds_sched.log")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest}[sys.argv[1]]()
