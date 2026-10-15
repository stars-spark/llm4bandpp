#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Low-capacity closed loop of the multi-scale estimator without an LLM against LLM4Band
(lowbw-nl-vs-conf-v1 and lowbw-nl-vs-conf-env6-v1). Constant 100, 200, 300 and 400 kb/s (deploy/profiles/lowbw_nl/
nlc_*.profile; 50 ms delay, no loss, 120 s), 320x240 source at 15 frames per second, collector v6. Arms:
arm_llm4bandpp_nl_x and arm_llm4band_conf_x, each without the envelope (BWE_ENVELOPE=0) and with probing envelope
version 6; three runs per cell, arms rotated within capacity and repetition; 48 runs, run script v17, two container pairs in
parallel. The multi-scale checkpoint and the conference checkpoint are not in the package (see NOTICE and
docs/OFFLINE.md). Both claims (without and with the envelope) use the same judge: D is the utility difference (without
the LLM minus LLM4Band) averaged over the four capacity cells, with a 90% interval from 10000 within-cell resamples
(seed 20261004) and the non-inferiority margin -5.27 (switch-closedloop-noise-v1). Holds: lower bound above -5.27 and no
safety line; direction only: D above -5.27 with the lower bound at or below it; does not hold: D at or below -5.27 or a
safety line. Safety line: a cell more than 10 points below LLM4Band, or all three runs of a cell invalid
for the arm under test; cells where all conference runs are invalid are dropped, and fewer than three usable cells is
inconclusive. Report only: per-cell utility, video rate, queueing delay, VMAF, SSIM, PSNR, frame skips, decision
interval, inference time and envelope rewrites.
Subcommands: smoke OUT, jobs OUT, judge, judge --selftest.
"""
import glob, gzip, json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/lowbw-nl-vs-conf-v1"); ID1, ID2 = "lowbw-nl-vs-conf-v1", "lowbw-nl-vs-conf-env6-v1"
P = ROOT / "scripts/alphartc/deploy/profiles/lowbw_nl"; CAPS = [100, 200, 300, 400]; REPS = 3
ARMS = {"nl0": ("arm_llm4bandpp_nl_x", "0"), "cf0": ("arm_llm4band_conf_x", "0"), "nl6": ("arm_llm4bandpp_nl_x", "6"), "cf6": ("arm_llm4band_conf_x", "6")}
NI, SAFE, SEED, B = -5.27, 10.0, 20261004, 10000
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402


def spec(name, J, pairs):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": name, "K": str(K / name), "log": str(ROOT / "logs/lowbw_nl_vs_conf_v1.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v17.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 1, "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def job(cap, a, rep):
    arm, envl = ARMS[a]
    return {"cond": f"c{cap}__{a}__r{rep}", "arm": arm, "profile": str(P / f"nlc_{cap}.profile"), "env": {"STALENESS_ENVELOPE": envl}}


def smoke(out):
    """Smoke run, not counted: one run of each arm at 400 kb/s without the envelope; checks validity, start-up logs and the asynchronous layer."""
    J = [dict(job(400, "nl0", 0), cond="smoke__nl0"), dict(job(400, "cf0", 0), cond="smoke__cf0")]
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
    v1, m1 = judge(U, "nl0", "cf0"); v2, m2 = judge(U, "nl6", "cf6")
    keys = ("utility", "video_kbps", "queue_delay_mean_ms", "vmaf", "ssim", "psnr", "skipped_source_frames_per_100", "decision_gap_p95_ms", "compute_p50_ms")
    agg = {a: {c: {k: (lambda xs: st.mean(xs) if xs else None)([r[k] for r in R if r["valid"] and r["arm_key"] == a and r["cap"] == c and r.get(k) is not None]) for k in keys} for c in CAPS} for a in ARMS}
    nval = {a: sum(1 for r in R if r["valid"] and r["arm_key"] == a) for a in ARMS}
    res = {"claim1_env0": {"verdict": v1, **m1}, "claim2_env6": {"verdict": v2, **m2}, "by_arm_cap": agg, "n_valid": nval, "n_runs": len(R), "invalid": {r["cond"]: r["invalid"] for r in R if not r["valid"]}}
    LOCAL = ROOT / "experiments/results/lowbw_nl_vs_conf_v1"; LOCAL.mkdir(parents=True, exist_ok=True)
    (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str)); (LOCAL / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs.jsonl", "w") as f:
        for r in R: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    f1 = lambda x: "none" if x is None else f"{x:.1f}"
    tab = lambda a, k: json.dumps({c: f1(agg[a][c][k]) for c in CAPS}, ensure_ascii=False)
    common = (f"Report only: utility without the LLM and without the envelope {tab('nl0', 'utility')}, LLM4Band without the envelope {tab('cf0', 'utility')}, without the LLM with envelope v6 {tab('nl6', 'utility')}, LLM4Band with envelope v6 {tab('cf6', 'utility')}; video rate {json.dumps({a: {c: f1(agg[a][c]['video_kbps']) for c in CAPS} for a in ARMS}, ensure_ascii=False)}; VMAF {json.dumps({a: {c: f1(agg[a][c]['vmaf']) for c in CAPS} for a in ARMS}, ensure_ascii=False)}; mean SSIM {json.dumps({a: (lambda xs: round(st.mean(xs), 3) if xs else None)([agg[a][c]['ssim'] for c in CAPS if agg[a][c]['ssim'] is not None]) for a in ARMS}, ensure_ascii=False)}; valid runs {json.dumps(nval, ensure_ascii=False)} of {len(R)}.")
    b1 = (f"Primary endpoint D (without the LLM minus LLM4Band, no envelope, {m1['n_cells_used']} cells equally weighted) {m1['D']:+.2f}, 90% interval [{m1['ci90'][0]:+.2f}, {m1['ci90'][1]:+.2f}]; per cell {json.dumps({c: round(x, 2) for c, x in m1['cell_diff'].items()})}; safety line (cells worse by more than 10 points): {m1['severe_cells'] or 'none'}, cells with all runs of the tested arm invalid {m1['all_invalid_cells'] or 'none'}, cells excluded because all LLM4Band runs were invalid {m1['dropped_cells_no_ref'] or 'none'}." + common)
    b2 = (f"Primary endpoint D (without the LLM minus LLM4Band, both arms with envelope v6, {m2['n_cells_used']} cells equally weighted) {m2['D']:+.2f}, 90% interval [{m2['ci90'][0]:+.2f}, {m2['ci90'][1]:+.2f}]; per cell {json.dumps({c: round(x, 2) for c, x in m2['cell_diff'].items()})}; safety line (cells worse by more than 10 points): {m2['severe_cells'] or 'none'}, cells with all runs of the tested arm invalid {m2['all_invalid_cells'] or 'none'}, cells excluded because all LLM4Band runs were invalid {m2['dropped_cells_no_ref'] or 'none'}. Same batch as claim one.")
    print(v1, b1); print(v2, b2)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    lim = ("Four constant capacities, 100 to 400 kbit/s, 3 runs per cell; 320x240 source at 15 fps (ceiling about 610 kbit/s); one-way delay 50 ms, no random loss; single-machine testbed, two container pairs in parallel; receiver inference is asynchronous (above 40 ms the previous estimate is returned), and LLM4Band's per-step inference is slower on the CPU; the arm without the LLM is our recipe without the LLM (15 features, capacity anchor, 50000 steps, seed 1); LLM4Band is the checkpoint of the original authors' online application; both arms use collector v6.")
    for cid, v, m, b in ((ID1, v1, m1, b1), (ID2, v2, m2, b2)):
        ex("data", "--id", cid, "--metrics", json.dumps({k: m[k] for k in ("D", "ci90", "cell_diff", "severe_cells", "all_invalid_cells", "n_cells_used")} | {"n_valid": nval}, ensure_ascii=False, default=str),
           "--artifact", str(LOCAL / "result_v1.json"), "--artifact", str(LOCAL / "runs.jsonl"))
        if v == "inconclusive": ex("note", "--id", cid, "Fewer than 3 usable cells, no conclusion is recorded." + b); continue
        ex("conclude", "--id", cid, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (non-inferiority margin 5.27 utility points, safety line 10 points and all runs of a cell invalid)." + b, "--basis", b, "--limitations", lim,
           "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "smoke": smoke(sys.argv[2])
    elif c == "jobs": jobs(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
