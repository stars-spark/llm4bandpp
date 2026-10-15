#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch lowbw-noanchor-200-v1: tests whether removing the capacity anchor closes the 200 kbit/s gap to LLM4Band.
Arms without envelope: deployed estimator (ch0) and the same recipe without the capacity anchor (a0), both with the 5 kbps floor, and LLM4Band (cf0); conditions 200 kbit/s with and without 1% loss. Main endpoint: a0 minus ch0 utility over the two conditions; holds if the 90% lower bound is above 0 and the difference is at least 3.
Usage: lowbw_noanchor200_v1.py jobs OUT | judge [--selftest]
"""
import json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/lowbw-noanchor-200-v1"); ID1 = "lowbw-noanchor-200-v1"
D_ = ROOT / "scripts/alphartc/deploy/profiles"
CONDS = {"c200": D_ / "lowbw_nl/nlc_200.profile", "c200l1": D_ / "lowbw_loss/nlc_200_l1.profile"}; REPS = 4
ARMS = {"ch0": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_MIN_BPS_FLOOR": "1"}),
        "a0": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_MIN_BPS_FLOOR": "1", "STALENESS_CH_CHECKPOINT": "/app/model/ch_v1/ch_a0s2.pt"}),
        "cf0": ("arm_llm4band_conf_x", {"STALENESS_ENVELOPE": "0"})}
SEED, B, MIN_D = 20261008, 10000, 3.0
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402


def spec(name, J, pairs):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": name, "K": str(K / name), "log": str(ROOT / "logs/lowbw_noanchor200_v1.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v29.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 1, "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def jobs(out):
    J = []; order = list(ARMS); blk = 0
    for rep in range(1, REPS + 1):
        for c, pf in CONDS.items():
            rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
            for a in rot:
                arm, env = ARMS[a]; J.append({"cond": f"{c}__{a}__r{rep}", "arm": arm, "profile": str(pf), "env": dict(env)})
    Path(out).write_text(json.dumps(spec("main", J, [1, 2]), ensure_ascii=False, indent=1)); print("jobs:", len(J))


def judge(U, arm, ref, seed=SEED, B_=B):
    """Return (verdict, metrics) for arm minus ref over two equally weighted conditions with within-condition bootstrap; U maps (condition, arm key) to valid-run utilities."""
    if any(not U.get((c, arm)) for c in CONDS): return "does not hold", {"D": None, "ci90": None, "safety": f"{arm} all conditions invalid"}
    if any(not U.get((c, ref)) for c in CONDS): return "inconclusive", {"D": None, "ci90": None, "safety": f"{ref} all conditions invalid"}
    diff = {c: st.mean(U[(c, arm)]) - st.mean(U[(c, ref)]) for c in CONDS}; D = st.mean(diff.values())
    rng = random.Random(seed); bs = sorted(st.mean(st.mean([rng.choice(U[(c, arm)]) for _ in U[(c, arm)]]) - st.mean([rng.choice(U[(c, ref)]) for _ in U[(c, ref)]]) for c in CONDS) for _ in range(B_))
    lo, hi = bs[int(0.05 * (B_ - 1))], bs[int(0.95 * (B_ - 1))]
    v = "does not hold" if not D > 0 else ("holds" if lo > 0 and D >= MIN_D else "direction only")
    return v, {"D": D, "ci90": [lo, hi], "cell_diff": diff, "safety": None}


def selftest():
    r = random.Random(2); g = lambda m: [m + r.gauss(0, 1) for _ in range(4)]
    mk = lambda da: {(c, a): g(60 + (da if a == "a0" else 0)) for c in CONDS for a in ("a0", "ch0")}
    assert judge(mk(5), "a0", "ch0", B_=2000)[0] == "holds"
    assert judge(mk(1), "a0", "ch0", B_=2000)[0] == "direction only"
    assert judge(mk(-2), "a0", "ch0", B_=2000)[0] == "does not hold"
    U = mk(5); U[("c200", "a0")] = []; assert judge(U, "a0", "ch0", B_=2000)[0] == "does not hold"
    U = mk(5); U[("c200l1", "ch0")] = []; assert judge(U, "a0", "ch0", B_=2000)[0] == "inconclusive"
    t0, t1 = CONDS["c200"].read_text(), CONDS["c200l1"].read_text()
    assert "rate 200" in t0 and "loss" not in t0.replace("loss 0", "") and "rate 200" in t1 and "loss 1" in t1
    print("Self-test passed: verdicts, all-invalid condition for either arm, two conditions present")


def read_runs():
    s = json.load(open(K / "jobs_main.json")); R = []
    for j in s["jobs"]:
        c, a, rep = j["cond"].split("__"); d = K / "main" / j["cond"]; tag = f"{j['arm']}__{Path(j['profile']).stem}__d0__r1"
        js = d / f"{tag}.json"; inv = list(d.glob("invalid_*"))
        r = {"cond": j["cond"], "c": c, "arm_key": a, "arm": j["arm"], "rep": rep, "valid": js.is_file() and not inv, "invalid": [p.name for p in inv][:3] + ([] if js.is_file() else ["Missing result file"])}
        if js.is_file():
            x = json.load(open(js)); n = x["network"]
            r.update({"utility": n["utility"], "video_kbps": n.get("primary_video_payload_rate_kbps"), "queue_delay_mean_ms": n.get("queue_delay_mean_ms")})
        q = d / f"quality_{tag}.json"
        if q.is_file():
            y = json.load(open(q)); r.update({k: y.get(k) for k in ("vmaf", "ssim")})
        R.append(r)
    return R


def main():
    R = read_runs(); U = {}
    for r in R:
        if r["valid"]: U.setdefault((r["c"], r["arm_key"]), []).append(r["utility"])
    v, m = judge(U, "a0", "ch0"); va, ma = judge(U, "a0", "cf0"); vc, mc = judge(U, "ch0", "cf0")
    agg = {a: {c: {k: (lambda xs: round(st.mean(xs), 2) if xs else None)([r[k] for r in R if r["valid"] and r["arm_key"] == a and r["c"] == c and r.get(k) is not None])
                   for k in ("utility", "video_kbps", "queue_delay_mean_ms", "vmaf")} for c in CONDS} for a in ARMS}
    brk = {a: sum(1 for r in R if r["arm_key"] == a and not r["valid"]) for a in ARMS}
    res = {"primary_a0_vs_ch0": {"verdict": v, **m}, "report_a0_vs_cf0": {"verdict_report_only": va, **ma}, "report_ch0_vs_cf0": {"verdict_report_only": vc, **mc},
           "by_arm_cond": agg, "invalid_by_arm": brk, "n_runs": len(R), "invalid": {r["cond"]: r["invalid"] for r in R if not r["valid"]}}
    LOCAL = ROOT / "experiments/results/lowbw_noanchor_200_v1"; LOCAL.mkdir(parents=True, exist_ok=True)
    for f in (K / "result_v1.json", LOCAL / "result_v1.json"): f.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs.jsonl", "w") as f:
        for r in R: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    fm = lambda mm: "none" if mm["D"] is None else f"{mm['D']:+.2f} [{mm['ci90'][0]:+.2f}, {mm['ci90'][1]:+.2f}]"
    b = (f"Primary endpoint D (anchor-free minus deployed, two conditions equally weighted, no probing envelope){fm(m)}; per condition {json.dumps({c: round(x, 2) for c, x in (m.get('cell_diff') or {}).items()})}; safety line {m['safety'] or 'not triggered'}. Report only: anchor-free minus LLM4Band {fm(ma)}; deployed minus LLM4Band {fm(mc)}; per arm per condition {json.dumps(agg, ensure_ascii=False)}; broken calls {json.dumps(brk)}/8 each.")
    print(v, b)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID1, "--metrics", json.dumps({"D": m["D"], "ci90": m["ci90"], "a0_vs_cf0": ma["D"], "ch0_vs_cf0": mc["D"], "invalid_by_arm": brk}, ensure_ascii=False),
       "--artifact", str(LOCAL / "result_v1.json"), "--artifact", str(LOCAL / "runs.jsonl"))
    if v == "inconclusive": ex("note", "--id", ID1, "All runs of one condition of the deployed arm are invalid; no conclusion is recorded." + b); return
    ex("conclude", "--id", ID1, "--verdict", v, "--vs-criteria", "Criterion as pre-registered: D (no anchor minus deployed) holds if its lower bound is above 0 and D is at least 3; does not hold if D is at most 0 or all runs of a no-anchor condition are invalid." + b, "--basis", b,
       "--limitations", "The no-anchor arm has one seed (seed 2, the median of three); 4 runs per condition; 320x240 at 15 fps; two container pairs in parallel on a single-machine testbed; run script v29; its offline macro MSE is 6.356 against 5.795 for the deployed estimator.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "jobs": jobs(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
