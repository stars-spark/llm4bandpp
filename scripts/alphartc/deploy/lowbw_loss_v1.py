#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch lowbw-loss200-ch-v1: one condition, constant 200 kbit/s with 50 ms one-way delay and 1% random loss.
Four arms, 6 runs each: deployed estimator without envelope (ch0), LLM4Band without envelope (cf0), deployed system (dep) and Python GCC called every 200 ms. Main endpoint: ch0 minus cf0 utility, bootstrap 90% interval, non-inferiority margin -5.27; dep minus GCC is report-only.
Usage: lowbw_loss_v1.py jobs OUT | judge [--selftest]
"""
import glob, json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/lowbw-loss200-ch-v1"); ID1 = "lowbw-loss200-ch-v1"
LOCAL = ROOT / "experiments/results/lowbw_loss200_ch_v1"
PF = ROOT / "scripts/alphartc/deploy/profiles/lowbw_loss/nlc_200_l1.profile"; REPS = 6
ARMS = {"ch0": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_MIN_BPS_FLOOR": "1"}), "cf0": ("arm_llm4band_conf_x", {"STALENESS_ENVELOPE": "0"}),
        "dep": ("arm_ch_x", {"STALENESS_ENVELOPE": "6", "STALENESS_MIN_BPS_FLOOR": "1"}), "gcc": ("gcc_pt125_c200", {})}
NI, SAFE, SEED, B = -5.27, 10.0, 20261007, 10000
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402


def spec(name, J, pairs):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": name, "K": str(K / name), "log": str(ROOT / "logs/lowbw_loss200_v1.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v28.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 1, "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def jobs(out):
    J = []; order = list(ARMS)
    for rep in range(1, REPS + 1):
        rot = order[(rep - 1) % len(order):] + order[:(rep - 1) % len(order)]
        for a in rot:
            arm, env = ARMS[a]; J.append({"cond": f"c200l1__{a}__r{rep}", "arm": arm, "profile": str(PF), "env": dict(env)})
    Path(out).write_text(json.dumps(spec("main", J, [1, 2]), ensure_ascii=False, indent=1)); print("jobs:", len(J))


def diff_ci(a, b, seed=SEED, B_=B):
    rng = random.Random(seed); bs = sorted(sum(rng.choice(a) for _ in a) / len(a) - sum(rng.choice(b) for _ in b) / len(b) for _ in range(B_))
    return st.mean(a) - st.mean(b), [bs[int(0.05 * (B_ - 1))], bs[int(0.95 * (B_ - 1))]]


def decide(U):
    a, b = U.get("ch0", []), U.get("cf0", [])
    if not a: return "does not hold", {"D": None, "ci90": None, "safety": "ch0 all void"}
    if not b: return "inconclusive", {"D": None, "ci90": None, "safety": "cf0 all invalid"}
    D, ci = diff_ci(a, b)
    if D < -SAFE: return "does not hold", {"D": D, "ci90": ci, "safety": "more than 10 points lower"}
    if not D > NI: return "does not hold", {"D": D, "ci90": ci, "safety": None}
    return ("holds" if ci[0] > NI else "direction only"), {"D": D, "ci90": ci, "safety": None}


def selftest():
    r = random.Random(1); g = lambda m, s=1.0: [m + r.gauss(0, s) for _ in range(6)]
    assert decide({"ch0": g(60), "cf0": g(60)})[0] == "holds"
    assert decide({"ch0": [52, 60, 68, 50, 66, 58], "cf0": [62, 60, 64, 59, 61, 63]})[0] == "direction only"
    assert decide({"ch0": g(50), "cf0": g(57)})[0] == "does not hold"
    assert decide({"ch0": g(40), "cf0": g(60)})[1]["safety"] == "more than 10 points lower"
    assert decide({"ch0": [], "cf0": g(60)})[0] == "does not hold" and decide({"ch0": g(60), "cf0": []})[0] == "inconclusive"
    txt = PF.read_text(); assert "rate 200" in txt and "loss 1" in txt and "delay 50" in txt
    print("Self-test passed: verdicts, safety line, all-invalid reference arm; loss profile present")


def async_stats(d):
    c = {}; age = []
    for f in glob.glob(str(d / "async_*.jsonl")):
        for l in open(f):
            try: j = json.loads(l)
            except Exception: continue
            c[j["mode"]] = c.get(j["mode"], 0) + 1; age.append(j["t_req_ms"] - j["out_start_ms"])
    n = sum(c.values())
    return {"fresh_frac": (c.get("fresh", 0) / n) if n else None, "age_p50_ms": st.median(age) if age else None}


def read_runs():
    s = json.load(open(K / "jobs_main.json")); R = []
    for j in s["jobs"]:
        _, a, rep = j["cond"].split("__"); d = K / "main" / j["cond"]; tag = f"{j['arm']}__nlc_200_l1__d0__r1"
        js = d / f"{tag}.json"; inv = list(d.glob("invalid_*"))
        r = {"cond": j["cond"], "arm_key": a, "arm": j["arm"], "rep": rep, "valid": js.is_file() and not inv, "invalid": [p.name for p in inv][:3] + ([] if js.is_file() else ["Missing result file"])}
        if js.is_file():
            x = json.load(open(js)); n = x["network"]
            r.update({"utility": n["utility"], "video_kbps": n.get("primary_video_payload_rate_kbps"), "queue_delay_mean_ms": n.get("queue_delay_mean_ms"), "loss_rate": (n.get("loss") or {}).get("loss_rate")})
        q = d / f"quality_{tag}.json"
        if q.is_file():
            y = json.load(open(q)); r.update({k: y.get(k) for k in ("vmaf", "ssim")})
        if a == "cf0": r.update(async_stats(d))
        R.append(r)
    return R


def main():
    R = read_runs(); U = {a: [r["utility"] for r in R if r["valid"] and r["arm_key"] == a] for a in ARMS}
    v, m = decide(U); dg = diff_ci(U["dep"], U["gcc"]) if U["dep"] and U["gcc"] else (None, None)
    agg = {a: {k: (lambda xs: st.mean(xs) if xs else None)([r[k] for r in R if r["valid"] and r["arm_key"] == a and r.get(k) is not None])
               for k in ("utility", "vmaf", "ssim", "video_kbps", "queue_delay_mean_ms", "loss_rate", "fresh_frac", "age_p50_ms")} for a in ARMS}
    brk = {a: sum(1 for r in R if r["arm_key"] == a and not r["valid"]) for a in ARMS}
    res = {"verdict": v, **m, "dep_minus_gcc": {"D": dg[0], "ci90": dg[1]}, "by_arm": agg, "invalid_by_arm": brk, "n_runs": len(R), "invalid": {r["cond"]: r["invalid"] for r in R if not r["valid"]}}
    LOCAL.mkdir(parents=True, exist_ok=True)
    for p in (K / "result_v1.json", LOCAL / "result_v1.json"): p.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs.jsonl", "w") as f:
        for r in R: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    r2 = lambda x: None if x is None else round(x, 2)
    ci = lambda c: None if c is None else [r2(c[0]), r2(c[1])]
    b = (f"Primary endpoint D (C-H with the 5 kb/s floor minus LLM4Band, neither behind the probing envelope, 200 kbit/s with 1% random loss, 6 runs each){r2(m['D'])}, 90% interval {ci(m['ci90'])}; safety line {m['safety'] or 'none'}. Report only: deployed system minus GCC {r2(dg[0])}, interval {ci(dg[1])}; each arm {json.dumps({a: {k: r2(x) for k, x in d.items()} for a, d in agg.items()}, ensure_ascii=False)}; void (broken calls) {json.dumps(brk, ensure_ascii=False)}/6 each.")
    print(v, b)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID1, "--metrics", json.dumps({"D": m["D"], "ci90": m["ci90"], "dep_minus_gcc": dg[0], "invalid_by_arm": brk}, ensure_ascii=False, default=str), "--artifact", str(LOCAL / "result_v1.json"), "--artifact", str(LOCAL / "runs.jsonl"))
    if v == "inconclusive": ex("note", "--id", ID1, "All six conference-version runs invalid; no conclusion is recorded." + b); return
    ex("conclude", "--id", ID1, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (non-inferiority margin 5.27 utility points, safety line 10 points, and all C-H runs invalid)." + b, "--basis", b,
       "--limitations", "Single condition, 200 kbit/s with 1% random loss, 6 runs per arm; source 320x240 at 15 fps; LLM4Band runs its released online checkpoint, no 5 kb/s floor, and asynchronous receiver-side inference (when it takes longer than 40 ms, the previous estimate is returned); single-machine testbed, two container pairs in parallel; run script v28.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "jobs": jobs(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
