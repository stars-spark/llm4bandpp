#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batches hd720-hb-learned-env-v1 and hd720-hb-learned-alone-v1: 720p at high bandwidth with the sender cap at 20 Mbit/s (constant 3 to 15 Mbit/s and two 4G windows, Johnny and FourPeople).
Arms: deployed estimator and Schaferct-R, each with and without probing envelope v6 (5 kbps floor kept). With envelope: deployed minus Schaferct-R VMAF, non-inferiority margin 6 via hd720_ch_eval_v1.judge; without envelope: holds if the lower bound is above 0 and the difference is at least 6 VMAF.
Usage: hd720_hb_learned_v1.py jobs | smoke | smoke-gate | judge | selftest
"""
import json, shutil, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-hb-learned-v1"); ID1 = "hd720-hb-learned-env-v1"; ID2 = "hd720-hb-learned-alone-v1"
LOCAL = ROOT / "experiments/results/hd720_hb_learned_v1"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v24.sh"
PB = D_ / "profiles/hd720_hb"; PROV = json.load(open(PB / "provenance.json"))["profiles"]; CONDS = ["hb_c3", "hb_c6", "hb_c10", "hb_c15", "hb_t1", "hb_t2"]
CH = AL.CH; HB = {"STALENESS_HIGH_BITRATE": "1"}; REPS = 2
ENV6 = dict(AL.ENV[CH], **HB); ENV0 = dict(ENV6, STALENESS_ENVELOPE="0")
ARMKEYS = {"ch": (CH, ENV6), "scr": ("arm_schaferct_retrained_d", ENV6), "ch0": (CH, ENV0), "scr0": ("arm_schaferct_retrained_d", ENV0)}
CEIL = {"johnny": 12124.2, "fourpeople": 16058.4}


def prepare(Kd=K):
    Kd.mkdir(parents=True, exist_ok=True)
    for n in ("contents.json", "layout.json"):
        src, dst = H.K / n, Kd / n
        if dst.is_file(): assert dst.read_bytes() == src.read_bytes()
        else: shutil.copy(src, dst)
    (Kd / "ceilings.json").write_text(json.dumps({"ceiling_kbps": CEIL, "definition": "As in hd720-highbw-ch-v1: median video rate in calibration hb-calib-explore-v2 with the patched sender", "source": "experiments/results/hb_calib_v2/summary.json"}, ensure_ascii=False, indent=1))


def jobs():
    prepare(); C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []; order = list(ARMKEYS); blk = 0
    for rep in range(1, REPS + 1):
        for cond in CONDS:
            for content in C["main_contents"]:
                rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
                for a in rot:
                    arm, env = ARMKEYS[a]
                    J.append({"cond": f"{cond}__{content}__{a}__r{rep}", "arm": arm, "profile": str(PB / f"{cond}.profile"), "rep": rep, "video_id": content,
                              "queue": PROV[cond]["queue_packets"], "source": H.source_of(content, layout), "env": dict(env)})
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID1, K / "main", J, ROOT / "logs/hd720_hb_learned_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def env0_check(d, tag):
    import hd720_run_metrics_v1 as RM
    p = RM.first(d, f"obs_{tag}.jsonl*")
    if p is None: return False, "missing obs trace"
    vs = {str(o.get("envelope_version")) for o in RM.jl(p) if "est_bps" in o}
    return vs == {"0"}, ("" if vs == {"0"} else f"probing envelope version is not 0: {sorted(vs)}")


def collect(Kd=K):
    """Collect per-run readings as AL.collect, with the envelope v6 check for the two enveloped arms and a version-0 check for the two bare arms."""
    import hd720_run_metrics_v1 as RM
    s = json.load(open(Kd / "main" / "jobs.json")); ceil = json.load(open(Kd / "ceilings.json"))["ceiling_kbps"]; runs = []
    for j in s["jobs"]:
        d = Kd / "main" / j["cond"]; cond = Path(j["profile"]).stem; tag = f"{j['arm']}__{cond}__d0__r{j['rep']}__v{j['video_id']}"; a = j["cond"].split("__")[2]
        if not d.is_dir(): runs.append({"tag": tag, "arm": j["arm"], "cond": cond, "video_id": j["video_id"], "rep": j["rep"], "valid": False, "invalid_reasons": ["Missing run directory"], "job": j["cond"]}); continue
        r = RM.run_metrics(d, tag, j["arm"], cond, ceil[j["video_id"]]); r["video_id"] = j["video_id"]; r["rep"] = j["rep"]; r["job"] = j["cond"]
        if a.endswith("0"):
            ok, why = env0_check(d, tag)
            if not ok: r["valid"] = False; r["invalid_reasons"] = list(r.get("invalid_reasons", [])) + ["probing envelope v0 check did not pass:" + why]
        else:
            r.update(H.env6_check(d, tag))
            if not r["env6_ok"]: r["valid"] = False; r["invalid_reasons"] = list(r.get("invalid_reasons", [])) + ["probing envelope v6 check did not pass:" + ";".join(r["env6_reasons"])]
        runs.append(r)
    return runs, RM.code_audit(runs)


def build_V(runs):
    V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["job"].split("__")[2]), []).append(r["vmaf"])
    return V


def alone_verdict(m):
    safety = bool(m["severe_cells"] or m["all_invalid_cells"])
    if m["n_cells_used"] < 6 and not safety: return "inconclusive"
    if safety or not (m["D"] > 0): return "does not hold"
    return "holds" if (m["ci90"][0] > 0 and m["D"] >= 6) else "direction only"


def selftest():
    H.selftest()
    runs = [{"valid": True, "vmaf": 70.0 + i, "job": f"hb_c3__johnny__{k}__r1", "cond": "hb_c3", "video_id": "johnny"} for i, k in enumerate(ARMKEYS)]
    V = build_V(runs); assert V[("hb_c3__johnny", "ch")] == [70.0] and V[("hb_c3__johnny", "scr0")] == [73.0], V
    base = {"severe_cells": [], "all_invalid_cells": [], "n_cells_used": 12}
    assert alone_verdict(dict(base, D=7.0, ci90=[5.0, 9.0])) == "holds"
    assert alone_verdict(dict(base, D=4.0, ci90=[2.0, 6.0])) == "direction only"
    assert alone_verdict(dict(base, D=7.0, ci90=[-1.0, 9.0])) == "direction only"
    assert alone_verdict(dict(base, D=-1.0, ci90=[-3.0, 1.0])) == "does not hold"
    assert alone_verdict(dict(base, D=8.0, ci90=[5.0, 9.0], severe_cells=["x"])) == "does not hold"
    assert alone_verdict(dict(base, D=8.0, ci90=[5.0, 9.0], n_cells_used=4)) == "inconclusive"
    assert ENV6["STALENESS_HIGH_BITRATE"] == "1" and ENV0["STALENESS_ENVELOPE"] == "0" and ENV6["STALENESS_ENVELOPE"] == AL.ENV[CH]["STALENESS_ENVELOPE"]
    assert all((PB / f"{c}.profile").is_file() for c in CONDS)
    print("Self-test passed: judge, arm keys, no-envelope verdicts, high-bitrate flag")


KS = Path("/path/to/testbed/results/hd720-hb-learned-v1-smoke")


def smoke():
    """Write smoke jobs on hb_c6 with Johnny: one Schaferct-R run with envelope and one deployed-estimator run without, both to pass before the full batch."""
    prepare(KS); C = json.load(open(KS / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []
    for a in ("scr", "ch0"):
        arm, env = ARMKEYS[a]
        J.append({"cond": f"hb_c6__johnny__{a}__r1", "arm": arm, "profile": str(PB / "hb_c6.profile"), "rep": 1, "video_id": "johnny",
                  "queue": PROV["hb_c6"]["queue_packets"], "source": H.source_of("johnny", layout), "env": dict(env)})
    (KS / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID1 + "-smoke", KS / "main", J, ROOT / "logs/hd720_hb_learned_smoke_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (KS / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("smoke jobs:", len(J))


def smoke_gate():
    runs, bad = collect(KS); ok = len(runs) == 2 and all(r.get("valid") for r in runs) and not bad
    print("smoke test", "Pass" if ok else "not passed", [(r["job"], r.get("valid"), r.get("invalid_reasons"), r.get("vmaf"), r.get("video_kbps")) for r in runs], "hash anomaly", bad)
    sys.exit(0 if ok else 1)


def judge():
    runs, bad = collect()
    if not AL.audit_ok(K, ID1, runs, bad): return
    cells = [f"{c}__{v}" for c in CONDS for v in json.load(open(K / "contents.json"))["main_contents"]]; V = build_V(runs)
    v1, m1 = H.judge(V, cells, arm="ch", ref="scr"); _, m2 = H.judge(V, cells, arm="ch0", ref="scr0"); v2 = alone_verdict(m2)
    key = lambda r: r["job"].split("__")[2]
    agg = lambda rs, f: (lambda xs: sum(xs) / len(xs) if xs else None)([r[f] for r in rs if r.get("valid") and r.get(f) is not None])
    ba = {k: {f: agg([r for r in runs if key(r) == k], f) for f in ("vmaf", "ssim", "file_freeze_per_min", "loss_rate", "delay_score", "video_kbps", "envelope_rewrite_frac")} for k in ARMKEYS}
    bc = {k: {c: {f: agg([r for r in runs if key(r) == k and r["cond"] == c], f) for f in ("vmaf", "file_freeze_per_min", "video_kbps")} for c in CONDS} for k in ARMKEYS}
    nv = {k: sum(1 for r in runs if r.get("valid") and key(r) == k) for k in ARMKEYS}
    res = {"env": {"verdict": v1, **m1}, "alone": {"verdict": v2, **m2}, "by_armkey": ba, "by_armkey_cond": bc, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad,
           "invalid_runs": {r["job"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    AL.export(K, LOCAL, runs, res)
    r1 = lambda x: None if x is None else round(x, 1); r2 = lambda x: None if x is None else round(x, 2)
    rep = (f"Report only: per-arm VMAF {json.dumps({k: r1(x['vmaf']) for k, x in ba.items()}, ensure_ascii=False)}; SSIM {json.dumps({k: r2(x['ssim']) for k, x in ba.items()}, ensure_ascii=False)}; freezes per minute {json.dumps({k: r2(x['file_freeze_per_min']) for k, x in ba.items()}, ensure_ascii=False)}; packet loss rate {json.dumps({k: r2(x['loss_rate']) for k, x in ba.items()}, ensure_ascii=False)}; delay score {json.dumps({k: r2(x['delay_score']) for k, x in ba.items()}, ensure_ascii=False)}; video rate {json.dumps({k: r1(x['video_kbps']) for k, x in ba.items()}, ensure_ascii=False)}; probing envelope rewrite {json.dumps({k: r2(x['envelope_rewrite_frac']) for k, x in ba.items()}, ensure_ascii=False)}; per-condition VMAF {json.dumps({k: {c: r1(x['vmaf']) for c, x in d.items()} for k, d in bc.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    b1 = (f"Primary endpoint D_E (C-H minus Schaferct-R, both with probing envelope v6, high bandwidth {m1['n_cells_used']} cells equally weighted) {AL.fmt(m1)}; safety line (cells worse by more than 10 points): {m1['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m1['all_invalid_cells'] or 'none'}; superiority (report only) {'reached' if m1['superiority_report_only'] else 'not reached'}." + rep)
    b2 = (f"Primary endpoint D_A (C-H minus Schaferct-R, both without probing envelope, with only the 5 kb/s floor, high bandwidth {m2['n_cells_used']} cells equally weighted) {AL.fmt(m2)}; safety line (cells worse by more than 10 points): {m2['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m2['all_invalid_cells'] or 'none'}." + rep)
    print(v1, b1); print(v2, b2)
    lim = ("Four constant capacities from 3 to 15 Mbit/s and two UCC 4G windows; patched sender with the 720p cap at 20 Mbit/s; Schaferct-R is the same ONNX as Table I, connected through fixed_x_v2 to the same collector and 5 kb/s floor; 2 runs per arm per cell; single-machine testbed; run script v24.")
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    for cid, v, m, b, crit, nxt in ((ID1, v1, m1, b1, "Criterion as pre-registered (hd720_ch_eval_v1.judge: non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid, superiority report only).", ""),
                                     (ID2, v2, m2, b2, "Criterion as pre-registered (superiority: lower bound greater than 0 and not less than 6 VMAF; safety line 10 points and cells with all C-H runs invalid).", "")):
        ex("data", "--id", cid, "--metrics", json.dumps({k: m[k] for k in ("D", "ci90", "severe_cells", "all_invalid_cells", "n_cells_used", "superiority_report_only")} | {"n_valid": nv}, ensure_ascii=False, default=str),
           "--artifact", str(K / "result_v1.json"), "--artifact", str(LOCAL / "runs_tidy.csv"))
        if v == "inconclusive": ex("note", "--id", cid, "Fewer than 6 usable cells, no conclusion is recorded." + b); continue
        ex("conclude", "--id", cid, "--verdict", v, "--vs-criteria", crit + b, "--basis", b, "--limitations", lim, "--next", nxt)


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest, "smoke": smoke, "smoke-gate": smoke_gate}[sys.argv[1]]()
