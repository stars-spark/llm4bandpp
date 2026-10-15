#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch lowbw-lambda-seeds-v1: tests on seeds 0 and 2 whether both HCQ terms keep calls alive without the envelope.
Six deployed-estimator arms (5 kbps floor, no envelope) at λ 0.4, 0 and 1.0 with seeds 0 and 2, constant 100 to 400 kbps. Main endpoint B = mean call breaks of λ 0 and λ 1.0 minus those of λ 0.4; holds if the 90% lower bound is above 0 and B is at least 3; does not hold if λ 0.4 breaks 4 or more times.
Usage: lowbw_lambda_seeds_v1.py jobs OUT | judge [--selftest]
"""
import json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/lowbw-lambda-seeds-v1"); ID1 = "lowbw-lambda-seeds-v1"
P = ROOT / "scripts/alphartc/deploy/profiles/lowbw_nl"; CAPS = [100, 200, 300, 400]; REPS = 3
BASE = {"STALENESS_ENVELOPE": "0", "STALENESS_MIN_BPS_FLOOR": "1"}
CKS = {"l04s0": "ch_s0.pt", "l04s2": "ch_s2.pt", "l00s0": "ch_l00s0.pt", "l00s2": "ch_l00s2.pt", "l10s0": "ch_l10s0.pt", "l10s2": "ch_l10s2.pt"}
ARMS = {k: ("arm_ch_x", dict(BASE, STALENESS_CH_CHECKPOINT=f"/app/model/ch_v1/{f}")) for k, f in CKS.items()}
W = {"l04": ["l04s0", "l04s2"], "l00": ["l00s0", "l00s2"], "l10": ["l10s0", "l10s2"]}
NI, SAFE, SEED, B, MIN_B, SAFE_BRK = -5.27, 10.0, 20261008, 10000, 3.0, 4
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402
import lowbw_lambda_mid_v1 as M


def spec(name, J, pairs):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": name, "K": str(K / name), "log": str(ROOT / "logs/lowbw_lambda_seeds_v1.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v29.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 1, "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def job(cap, a, rep):
    arm, env = ARMS[a]
    return {"cond": f"c{cap}__{a}__r{rep}", "arm": arm, "profile": str(P / f"nlc_{cap}.profile"), "env": dict(env)}


def jobs(out):
    J = []; order = list(ARMS); blk = 0
    for rep in range(1, REPS + 1):
        for cap in CAPS:
            rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
            J += [job(cap, a, rep) for a in rot]
    Path(out).write_text(json.dumps(spec("main", J, [1, 2]), ensure_ascii=False, indent=1)); print("jobs:", len(J))


def brk_judge(V, seed=SEED, B_=B):
    """Return (verdict, metrics) for the call-break endpoint B; V maps (capacity, arm key) to per-run break flags (1 broke, 0 did not)."""
    def stat(get):
        n = {w: sum(sum(get(c, a)) for a in ks for c in CAPS) for w, ks in W.items()}
        return (n["l00"] + n["l10"]) / 2 - n["l04"], n
    D, n = stat(lambda c, a: V.get((c, a), []))
    rng = random.Random(seed); bs = []
    for _ in range(B_):
        bs.append(stat(lambda c, a: [rng.choice(V[(c, a)]) for _ in V.get((c, a), [])])[0])
    bs.sort(); lo, hi = bs[int(0.05 * (B_ - 1))], bs[int(0.95 * (B_ - 1))]
    safety = n["l04"] >= SAFE_BRK
    v = "does not hold" if (safety or not D > 0) else ("holds" if lo > 0 and D >= MIN_B else "direction only")
    return v, {"B": D, "ci90": [lo, hi], "breaks_by_weight": n, "safety_l04_breaks_ge4": safety}


def selftest():
    def mk(b04, b00, b10):
        V = {}
        for w, b in (("l04", b04), ("l00", b00), ("l10", b10)):
            k = 0
            for a in W[w]:
                for c in CAPS:
                    V[(c, a)] = [1 if (k := k + 1) <= b else 0 for _ in range(3)]
        return V
    assert brk_judge(mk(0, 6, 10), B_=2000)[0] == "holds"
    assert brk_judge(mk(1, 2, 2), B_=2000)[0] == "direction only"
    assert brk_judge(mk(2, 1, 3), B_=2000)[0] == "does not hold"            # B = 0
    assert brk_judge(mk(4, 12, 14), B_=2000)[0] == "does not hold"
    print("Verdict self-test passed: holds, direction only, does not hold (B is not positive), safety line crossed")


def read_runs():
    s = json.load(open(K / "jobs_main.json")); R = []
    for j in s["jobs"]:
        cap, a, rep = j["cond"].split("__"); cap = int(cap[1:]); d = K / "main" / j["cond"]; tag = f"{j['arm']}__nlc_{cap}__d0__r1"
        js = d / f"{tag}.json"; inv = list(d.glob("invalid_*"))
        r = {"cond": j["cond"], "cap": cap, "arm_key": a, "weight": a[:3], "seed": a[3:], "arm": j["arm"], "rep": rep, "valid": js.is_file() and not inv,
             "invalid": [p.name for p in inv] + ([] if js.is_file() else ["Missing result file"])}
        if js.is_file():
            x = json.load(open(js)); n = x["network"]
            r.update({"utility": n["utility"], "video_kbps": n.get("primary_video_payload_rate_kbps"), "queue_delay_mean_ms": n.get("queue_delay_mean_ms"),
                      "decision_gap_p95_ms": x["decisions"].get("decision_gap_p95_ms")})
        q = d / f"quality_{tag}.json"
        if q.is_file():
            y = json.load(open(q)); r.update({k: y.get(k) for k in ("vmaf", "ssim")})
        R.append(r)
    return R


def main():
    R = read_runs(); V = {}; U = {}
    for r in R:
        V.setdefault((r["cap"], r["arm_key"]), []).append(0 if r["valid"] else 1)
        if r["valid"]: U.setdefault((r["cap"], r["weight"]), []).append(r["utility"])
    v, m = brk_judge(V)
    j10 = M.judge(U, "l10", "l04"); j00 = M.judge(U, "l00", "l04")
    by_arm = {a: sum(1 for r in R if r["arm_key"] == a and not r["valid"]) for a in ARMS}
    by_arm_cap = {a: {c: sum(1 for r in R if r["arm_key"] == a and r["cap"] == c and not r["valid"]) for c in CAPS} for a in ARMS}
    keys = ("utility", "video_kbps", "queue_delay_mean_ms", "vmaf")
    agg = {a: {c: {k: (lambda xs: round(st.mean(xs), 2) if xs else None)([r[k] for r in R if r["valid"] and r["arm_key"] == a and r["cap"] == c and r.get(k) is not None]) for k in keys} for c in CAPS} for a in ARMS}
    res = {"primary": {"verdict": v, **m}, "breaks_by_arm": by_arm, "breaks_by_arm_cap": by_arm_cap, "report_l10_vs_l04": {"verdict_report_only": j10[0], **j10[1]},
           "report_l00_vs_l04": {"verdict_report_only": j00[0], **j00[1]}, "by_arm_cap": agg, "n_runs": len(R), "invalid": {r["cond"]: r["invalid"] for r in R if not r["valid"]}}
    LOCAL = ROOT / "experiments/results/lowbw_lambda_seeds_v1"; LOCAL.mkdir(parents=True, exist_ok=True)
    for f in (K / "result_v1.json", LOCAL / "result_v1.json"): f.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs.jsonl", "w") as f:
        for r in R: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    b = (f"Primary endpoint B ((λ 0 broken calls + λ 1.0 broken calls) ÷ 2 - λ 0.4 broken calls, seeds 0 and 2 pooled, 24 runs per weight) {m['B']:+.1f}, 90% interval [{m['ci90'][0]:+.1f}, {m['ci90'][1]:+.1f}]; broken calls per weight {json.dumps(m['breaks_by_weight'])}; safety line (λ 0.4 broken calls ≥ 4) {'trigger' if m['safety_l04_breaks_ge4'] else 'not triggered'}. Report only: per-arm broken calls {json.dumps(by_arm)}; per-arm per-capacity broken calls {json.dumps(by_arm_cap)}; utility λ 1.0 minus λ 0.4 {j10[1]['D']:+.2f} [{j10[1]['ci90'][0]:+.2f}, {j10[1]['ci90'][1]:+.2f}] ({j10[0]}, report only), λ 0 minus λ 0.4 {j00[1]['D']:+.2f} [{j00[1]['ci90'][0]:+.2f}, {j00[1]['ci90'][1]:+.2f}] ({j00[0]}, report only); invalid reasons {json.dumps(res['invalid'], ensure_ascii=False)}.")
    print(v, b)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID1, "--metrics", json.dumps({"B": m["B"], "ci90": m["ci90"], "breaks_by_weight": m["breaks_by_weight"], "breaks_by_arm": by_arm}, ensure_ascii=False),
       "--artifact", str(LOCAL / "result_v1.json"), "--artifact", str(LOCAL / "runs.jsonl"))
    ex("conclude", "--id", ID1, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (B lower bound > 0 and B >= 3 holds; B <= 0 or lambda 0.4 broken calls >= 4 does not hold)." + b, "--basis", b,
       "--limitations", "seeds 0 and 2, 24 runs per weight; constant 100 to 400 kbps, 320x240 at 15 fps, one-way delay 50 ms, no random loss; broken calls count as invalid runs; single-machine testbed with two container pairs in parallel; run script v29; the readings for seed 1 are in lowbw-lambda-ch-v2 and are not merged.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "jobs": jobs(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
