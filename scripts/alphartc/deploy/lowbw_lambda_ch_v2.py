#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Low-capacity closed loop of the HCQ weight (lowbw-lambda-ch-v2, the registered rerun of lowbw-lambda-ch-v1, which was void because its scheduler run did not complete): does the quality term of HCQ matter in closed loop? Scheduled by parallel_testbed_v1.
Derived from lowbw_chf_vs_conf_v1.py with the same judge, conditions (constant 100 to 400 kb/s), rotation, intervals,
margin and safety line. All three arms are the deployed C-H with the 5 kb/s floor and without the envelope (arm_ch_x); only
the weights differ: l04 = ch.pt (lambda 0.4, seed 1), l10 = ch_l10s1.pt (lambda 1.0, error term only), l00 = ch_l00s1.pt
(lambda 0, quality term only; cell CB of the 2x2 ablation, seed 1). Run script v26. Primary endpoint judge(arm=l10,
ref=l04): is the arm without the quality term no more than 5.27 points worse than the deployed lambda 0.4;
judge(arm=l00, ref=l04) is reported only.
Judge settings inherited from lowbw_nl_vs_conf_v1.py: D is the utility difference averaged over the four capacity cells
with equal weight (three runs per cell), the 90% interval comes from 10000 within-cell resamples (seed 20261004), and the
non-inferiority margin is -5.27 (the testbed noise threshold of switch-closedloop-noise-v1). Holds: lower bound above
-5.27 and no safety line; direction only: D above -5.27 with the lower bound at or below it; does not hold: D at or below
-5.27, or a safety line (a cell more than 10 points lower, or all three runs of a cell invalid).
Subcommands: smoke OUT, jobs OUT, judge, judge --selftest.
"""
import glob, gzip, json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/lowbw-lambda-ch-v2"); ID1 = "lowbw-lambda-ch-v2"
P = ROOT / "scripts/alphartc/deploy/profiles/lowbw_nl"; CAPS = [100, 200, 300, 400]; REPS = 3
ARMS = {"l04": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_MIN_BPS_FLOOR": "1"}), "l10": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_MIN_BPS_FLOOR": "1", "STALENESS_CH_CHECKPOINT": "/app/model/ch_v1/ch_l10s1.pt"}),
        "l00": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_MIN_BPS_FLOOR": "1", "STALENESS_CH_CHECKPOINT": "/app/model/ch_v1/ch_l00s1.pt"})}
NI, SAFE, SEED, B = -5.27, 10.0, 20261004, 10000
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402


def spec(name, J, pairs):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": name, "K": str(K / name), "log": str(ROOT / "logs/lowbw_lambda_ch_v2.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v26.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 1, "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def job(cap, a, rep):
    arm, env = ARMS[a]
    return {"cond": f"c{cap}__{a}__r{rep}", "arm": arm, "profile": str(P / f"nlc_{cap}.profile"), "env": dict(env)}


def smoke(out):
    """Smoke run, not counted: one run per arm at 400 kb/s without the envelope; checks validity, start-up logs and the asynchronous layer."""
    J = [dict(job(400, "ch0", 0), cond="smoke__ch0"), dict(job(400, "cf0", 0), cond="smoke__cf0")]
    Path(out).write_text(json.dumps(spec("smoke", J, [1, 2]), ensure_ascii=False, indent=1)); print("smoke jobs:", len(J))


def jobs(out):
    J = []; order = list(ARMS); blk = 0
    for rep in range(1, REPS + 1):
        for cap in CAPS:
            rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
            J += [job(cap, a, rep) for a in rot]
    Path(out).write_text(json.dumps(spec("main", J, [1, 2]), ensure_ascii=False, indent=1)); print("jobs:", len(J))


def judge(U, arm, ref, seed=SEED, B_=B):
    """U[(capacity, arm)] = utilities of the valid runs."""
    all_inv = [c for c in CAPS if not U.get((c, arm))]; usable = [c for c in CAPS if U.get((c, arm)) and U.get((c, ref))]
    dropped = [c for c in CAPS if U.get((c, arm)) and not U.get((c, ref))]
    diff = {c: st.mean(U[(c, arm)]) - st.mean(U[(c, ref)]) for c in usable}; D = st.mean(diff.values()) if diff else float("nan")
    rng = random.Random(seed); bs = []
    for _ in range(B_ if usable else 0):
        bs.append(st.mean(sum(rng.choice(U[(c, arm)]) for _ in U[(c, arm)]) / len(U[(c, arm)]) - sum(rng.choice(U[(c, ref)]) for _ in U[(c, ref)]) / len(U[(c, ref)]) for c in usable))
    bs.sort(); lo = bs[int(0.05 * (len(bs) - 1))] if bs else float("nan"); hi = bs[int(0.95 * (len(bs) - 1))] if bs else float("nan")
    severe = [c for c, x in diff.items() if x < -SAFE]; safety = bool(severe or all_inv)
    if len(usable) < 3 and not safety: v = "inconclusive"
    elif safety or not D > NI: v = "does not hold"
    elif lo > NI: v = "holds"
    else: v = "direction only"
    return v, {"D": D, "ci90": [lo, hi], "cell_diff": diff, "severe_cells": severe, "all_invalid_cells": all_inv, "dropped_cells_no_ref": dropped, "n_cells_used": len(usable)}


def selftest():
    r = random.Random(3)
    def mk(delta, sev=None, kill=None):
        U = {}
        for c in CAPS:
            base = 60 + r.gauss(0, 5); U[(c, "ref")] = [base + r.gauss(0, 1) for _ in range(3)]; U[(c, "x")] = [base + delta + r.gauss(0, 1) for _ in range(3)]
        if sev: U[(sev, "x")] = [u - 12 for u in U[(sev, "ref")]]
        if kill: U[(kill, "x")] = []
        return U
    assert judge(mk(0.5), "x", "ref", B_=2000)[0] == "holds"
    Uw = {}
    for i, c in enumerate(CAPS): Uw[(c, "ref")] = [60 - 8, 60, 60 + 8]; Uw[(c, "x")] = [56 - 8, 56, 56 + 8]
    assert judge(Uw, "x", "ref", B_=2000)[0] == "direction only"
    assert judge(mk(-7), "x", "ref", B_=2000)[0] == "does not hold"
    assert judge(mk(1, sev=200), "x", "ref", B_=2000)[0] == "does not hold"
    v, m = judge(mk(1, kill=300), "x", "ref", B_=2000); assert v == "does not hold" and m["all_invalid_cells"] == [300]
    print("Verdict self-test passed (5 cases)")


def read_runs():
    s = json.load(open(K / "jobs_main.json")); R = []
    for j in s["jobs"]:
        cap, a, rep = j["cond"].split("__"); cap = int(cap[1:]); d = K / "main" / j["cond"]; tag = f"{j['arm']}__nlc_{cap}__d0__r1"
        js = d / f"{tag}.json"; inv = list(d.glob("invalid_*")); r = {"cond": j["cond"], "cap": cap, "arm_key": a, "arm": j["arm"], "rep": rep, "valid": js.is_file() and not inv,
                                                                      "invalid": [p.name for p in inv] + ([] if js.is_file() else ["Missing result file"])}
        if js.is_file():
            x = json.load(open(js)); n = x["network"]; r.update({"utility": n["utility"], "video_kbps": n.get("primary_video_payload_rate_kbps"), "queue_delay_mean_ms": n.get("queue_delay_mean_ms"),
                                                                  "queue_delay_p95_ms": n.get("queue_delay_p95_ms"), "rate_score": n.get("rate_score_1s"), "delay_score": n.get("delay_score"),
                                                                  "decision_gap_p95_ms": x["decisions"].get("decision_gap_p95_ms"), "compute_p50_ms": x["decisions"].get("compute_p50_ms")})
        q = d / f"quality_{tag}.json"
        if q.is_file():
            y = json.load(open(q)); r.update({k: y.get(k) for k in ("vmaf", "ssim", "psnr", "skipped_source_frames_per_100", "skip_events_gt2", "rendered_fps")})
        R.append(r)
    return R


def main():
    R = read_runs(); U = {}
    for r in R:
        if r["valid"]: U.setdefault((r["cap"], r["arm_key"]), []).append(r["utility"])
    v1, m1 = judge(U, "l10", "l04"); v0, m0 = judge(U, "l00", "l04")
    keys = ("utility", "video_kbps", "queue_delay_mean_ms", "vmaf", "ssim", "psnr", "skipped_source_frames_per_100", "decision_gap_p95_ms", "compute_p50_ms")
    agg = {a: {c: {k: (lambda xs: st.mean(xs) if xs else None)([r[k] for r in R if r["valid"] and r["arm_key"] == a and r["cap"] == c and r.get(k) is not None]) for k in keys} for c in CAPS} for a in ARMS}
    nval = {a: sum(1 for r in R if r["valid"] and r["arm_key"] == a) for a in ARMS}
    import floor_smoke_v1 as FS; fl = {r["cond"]: FS.floor_stats(K / "main" / r["cond"]) for r in R}
    res = {"primary_l10_vs_l04": {"verdict": v1, **m1}, "report_l00_vs_l04": {"verdict_report_only": v0, **m0}, "floor_report": fl, "by_arm_cap": agg, "n_valid": nval, "n_runs": len(R), "invalid": {r["cond"]: r["invalid"] for r in R if not r["valid"]}}
    LOCAL = ROOT / "experiments/results/lowbw_lambda_ch_v2"; LOCAL.mkdir(parents=True, exist_ok=True)
    (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str)); (LOCAL / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs.jsonl", "w") as f:
        for r in R: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    f1 = lambda x: "none" if x is None else f"{x:.1f}"
    tab = lambda a, k: json.dumps({c: f1(agg[a][c][k]) for c in CAPS}, ensure_ascii=False)
    common = (f"Report only: λ 0 minus λ 0.4 {m0['D']:+.2f}, 90% interval [{m0['ci90'][0]:+.2f}, {m0['ci90'][1]:+.2f}]; utility λ0.4 {tab('l04', 'utility')}, λ1.0 {tab('l10', 'utility')}, λ0 {tab('l00', 'utility')}; number of steps at the 5 kb/s floor {json.dumps({k: (v or {}).get('floor_hits') for k, v in fl.items()}, ensure_ascii=False)}; total number of steps with estimate 0 {sum((v or {}).get('est_zero') or 0 for v in fl.values())}; video rate {json.dumps({a: {c: f1(agg[a][c]['video_kbps']) for c in CAPS} for a in ARMS}, ensure_ascii=False)}; VMAF {json.dumps({a: {c: f1(agg[a][c]['vmaf']) for c in CAPS} for a in ARMS}, ensure_ascii=False)}; mean SSIM {json.dumps({a: (lambda xs: round(st.mean(xs), 3) if xs else None)([agg[a][c]['ssim'] for c in CAPS if agg[a][c]['ssim'] is not None]) for a in ARMS}, ensure_ascii=False)}; valid runs {json.dumps(nval, ensure_ascii=False)}/total {len(R)}.")
    b1 = (f"Primary endpoint D (λ 1.0 minus λ 0.4, deployed C-H seed 1 with the floor and no envelope, {m1['n_cells_used']} cells equally weighted) {m1['D']:+.2f}, 90% interval [{m1['ci90'][0]:+.2f}, {m1['ci90'][1]:+.2f}]; per cell {json.dumps({c: round(x, 2) for c, x in m1['cell_diff'].items()})}; safety line (cells worse by more than 10 points): {m1['severe_cells'] or 'none'}, cells with all runs of the tested arm invalid {m1['all_invalid_cells'] or 'none'}, cells excluded because all λ 0.4 runs were invalid {m1['dropped_cells_no_ref'] or 'none'}." + common)
    print(v1, b1)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    lim = ("All three arms are the deployed C-H seed 1 and differ only in the λ weight (0.4, 1.0, 0; cells of ch-lambda-sweep-v1 and nl_2x2_v1, weights checked for CPU equivalence on gpu-server-1); four constant capacities from 100 to 400 kbps, 3 runs per cell; 320x240 source at 15 fps (ceiling about 610 kbps); one-way delay 50 ms, no random loss; single-machine testbed, two container pairs in parallel; receiver inference is asynchronous (above 40 ms the previous estimate is returned), and LLM4Band's per-step inference is slower on the CPU; C-H is the conference encoder with HCQ, the capacity anchor, 50000 steps and no LLM (cell C-H of ablation-nl-enc-hcq-2x2-v1, seed 1), here with the 5 kbps estimate floor (added after the failure of lowbw-ch-vs-conf-v1, a method change); LLM4Band is the checkpoint of the original authors' online application, without a floor; both arms use collector v6; run script v20.")
    for cid, v, m, b in ((ID1, v1, m1, b1),):
        ex("data", "--id", cid, "--metrics", json.dumps({k: m[k] for k in ("D", "ci90", "cell_diff", "severe_cells", "all_invalid_cells", "n_cells_used")} | {"n_valid": nval}, ensure_ascii=False, default=str),
           "--artifact", str(LOCAL / "result_v1.json"), "--artifact", str(LOCAL / "runs.jsonl"))
        if v == "inconclusive": ex("note", "--id", cid, "Fewer than 3 usable cells, no conclusion is recorded." + b); continue
        ex("conclude", "--id", cid, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (λ 1.0 against λ 0.4, non-inferiority margin 5.27 utility points, safety line 10 points and cells with all λ 1.0 runs invalid)." + b, "--basis", b, "--limitations", lim,
           "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "smoke": smoke(sys.argv[2])
    elif c == "jobs": jobs(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
