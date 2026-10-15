#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-learned-baselines-v1: learned baselines behind the same probing envelope at 720p.
Three arms share the settings of the deployed system (collector v6, 5 kbps floor, envelope v6) and differ only in the model: deployed estimator, Schaferct-R, supervised MLP. Main endpoint: deployed minus Schaferct-R VMAF over 12 cells via hd720_ch_eval_v1.judge (non-inferiority margin 6); the MLP is report-only.
Usage: hd720_learned_v1.py jobs | judge | selftest
"""
import json, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-learned-baselines-v1"); ID = "hd720-learned-baselines-v1"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v24.sh"
CONDS = list(H.CONDS); CH = AL.CH
ARMKEYS = {"ch": (CH, dict(AL.ENV[CH])), "scr": ("arm_schaferct_retrained_d", dict(AL.ENV[CH])), "mlp": ("arm_mlp_d", dict(AL.ENV[CH]))}


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
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_learned_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def build_V(runs):
    V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["job"].split("__")[2]), []).append(r["vmaf"])
    return V


def selftest():
    H.selftest()
    runs = [{"valid": True, "vmaf": 70.0 + i, "job": f"hd_c1__johnny__{k}__r1", "cond": "hd_c1", "video_id": "johnny"} for i, k in enumerate(("ch", "scr", "mlp"))]
    V = build_V(runs); assert V[("hd_c1__johnny", "ch")] == [70.0] and V[("hd_c1__johnny", "mlp")] == [72.0], V
    assert all(e == AL.ENV[CH] for _, e in ARMKEYS.values()) and ARMKEYS["ch"][0] == CH and ARMKEYS["scr"][0] == "arm_schaferct_retrained_d"
    print("Self-test passed: judge, arm keys, shared collector, floor and envelope settings")


def judge():
    runs, bad = AL.collect(K, set())
    if not AL.audit_ok(K, ID, runs, bad): return
    cells = [f"{c}__{v}" for c in CONDS for v in json.load(open(K / "contents.json"))["main_contents"]]; V = build_V(runs)
    v, m = H.judge(V, cells, arm="ch", ref="scr"); mm = H.judge(V, cells, arm="ch", ref="mlp")[1]
    key = lambda r: r["job"].split("__")[2]
    agg = lambda rs, f: (lambda xs: sum(xs) / len(xs) if xs else None)([r[f] for r in rs if r.get("valid") and r.get(f) is not None])
    ba = {k: {f: agg([r for r in runs if key(r) == k], f) for f in ("vmaf", "ssim", "file_freeze_per_min", "webrtc_MeanFreezeDurationMs", "loss_rate", "delay_score", "video_kbps", "envelope_rewrite_frac")} for k in ARMKEYS}
    bc = {k: {c: {f: agg([r for r in runs if key(r) == k and r["cond"] == c], f) for f in ("vmaf", "file_freeze_per_min", "loss_rate", "delay_score", "video_kbps")} for c in CONDS} for k in ARMKEYS}
    nv = {k: sum(1 for r in runs if r.get("valid") and key(r) == k) for k in ARMKEYS}
    res = {"verdict": v, **m, "ch_vs_mlp": mm, "by_armkey": ba, "by_armkey_cond": bc, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad, "invalid_runs": {r["job"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_learned_baselines_v1"; AL.export(K, local, runs, res)
    r1 = lambda x: None if x is None else round(x, 1); r2 = lambda x: None if x is None else round(x, 2)
    basis = (f"Primary endpoint D_S (deployed C-H minus Schaferct-R, with the same collector, 5 kb/s floor and probing envelope, {m['n_cells_used']} cells equally weighted) {AL.fmt(m)}; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m['all_invalid_cells'] or 'none'}, cells excluded because all Schaferct-R runs were invalid {m['dropped_cells_no_ref'] or 'none'}. Report only: superiority {'reached' if m['superiority_report_only'] else 'not reached'}; C-H minus supervised MLP {AL.fmt(mm)}; per-arm packet loss rate {json.dumps({k: r2(x['loss_rate']) for k, x in ba.items()}, ensure_ascii=False)}; per-arm delay score {json.dumps({k: r2(x['delay_score']) for k, x in ba.items()}, ensure_ascii=False)}; per-arm mean freeze duration (ms) {json.dumps({k: r1(x['webrtc_MeanFreezeDurationMs']) for k, x in ba.items()}, ensure_ascii=False)}; per-condition VMAF {json.dumps({k: {c: r1(x['vmaf']) for c, x in d.items()} for k, d in bc.items()}, ensure_ascii=False)}; per-condition freezes per minute {json.dumps({k: {c: r2(x['file_freeze_per_min']) for c, x in d.items()} for k, d in bc.items()}, ensure_ascii=False)}; video rate {json.dumps({k: r1(x['video_kbps']) for k, x in ba.items()}, ensure_ascii=False)}; probing envelope rewrite fraction {json.dumps({k: r2(x['envelope_rewrite_frac']) for k, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    lim = ("Schaferct-R and the supervised MLP are the model files of Table I (ONNX and mlp_seed0.pt), connected through fixed_x_v2.py to the same collector, 5 kb/s floor and probing envelope as C-H; conditions and sequences are those of hd720-closedloop-ch-v1; libwebrtc defaults to a maximum bitrate of 2.5 Mbps for 960x540 and above; single-machine testbed; 3 runs per cell; one checkpoint per arm; run script v24.")
    AL.register(ID, v, m, basis, "Criterion as pre-registered (verbatim the same as hd720_ch_eval_v1.judge of hd720-closedloop-ch-v1: non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid; the reference arm is Schaferct-R behind the same probing envelope).", lim,
                "", K, local, nv, ROOT / "logs/hd720_learned_sched.log")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest}[sys.argv[1]]()
