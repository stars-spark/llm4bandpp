#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch content320-ch-gcc-v1: 320x240 closed loop on three sequences of low, medium and high motion (Johnny, Mobcal, Parkrun) at constant 200, 400 and 1000 kbit/s, deployed system against Python GCC called every 200 ms.
Measurement batch: reports deployed-minus-GCC utility and VMAF per sequence (cells equally weighted, within-cell bootstrap 90% interval); holds only means every cell has at least 2 valid runs per arm.
Usage: content320_ch_gcc_v1.py jobs OUTDIR | judge [--selftest]
"""
import json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/content320-ch-gcc-v1"); ID1 = "content320-ch-gcc-v1"
P = ROOT / "scripts/alphartc/deploy/profiles/content320"; CAPS = [200, 400, 1000]; REPS = 3; CONTENTS = {"low": "Johnny", "medium": "Mobcal", "high": "Parkrun"}
ARMS = {"dep": ("arm_ch_x", {"STALENESS_ENVELOPE": "6", "STALENESS_MIN_BPS_FLOOR": "1"}), "gcc": ("gcc_pt125_c200", {})}
SEED, B = 20261008, 10000
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402


def spec(name, J, pairs, content):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    src = f"testmedia/qoe_labeled_{content}_320x240.yuv"
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"; env["STALENESS_SOURCE_FILE"] = src
    return {"power_profile": pw, "name": name, "K": str(K / name), "log": str(ROOT / "logs/content320_ch_gcc_v1.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v29.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": src, "media": True, "vmaf_workers": 1, "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def jobs(outdir):
    Path(outdir).mkdir(parents=True, exist_ok=True)
    for content in CONTENTS:
        J = []; order = list(ARMS); blk = 0
        for rep in range(1, REPS + 1):
            for cap in CAPS:
                rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
                for a in rot:
                    arm, env = ARMS[a]; J.append({"cond": f"c{cap}__{a}__r{rep}", "arm": arm, "profile": str(P / f"c320_{cap}.profile"), "env": dict(env)})
        Path(outdir, f"jobs_main_{content}.json").write_text(json.dumps(spec(f"main_{content}", J, [1, 2], content), ensure_ascii=False, indent=1)); print(content, "jobs:", len(J))


def diff_ci(V, cells, seed=SEED, B_=B):
    """Return the deployed-minus-GCC difference over equally weighted cells and its within-cell bootstrap 90% interval; V maps (cell, arm) to valid-run values."""
    use = [c for c in cells if V.get((c, "dep")) and V.get((c, "gcc"))]
    if not use: return None
    D = st.mean(st.mean(V[(c, "dep")]) - st.mean(V[(c, "gcc")]) for c in use)
    rng = random.Random(seed); bs = sorted(st.mean(st.mean([rng.choice(V[(c, "dep")]) for _ in V[(c, "dep")]]) - st.mean([rng.choice(V[(c, "gcc")]) for _ in V[(c, "gcc")]]) for c in use) for _ in range(B_))
    return {"D": D, "ci90": [bs[int(0.05 * (B_ - 1))], bs[int(0.95 * (B_ - 1))]], "n_cells": len(use)}


def selftest():
    V = {(c, a): [60.0 + (2 if a == "dep" else 0) + i for i in range(3)] for c in CAPS for a in ("dep", "gcc")}
    m = diff_ci(V, CAPS, B_=1000); assert abs(m["D"] - 2.0) < 1e-9 and m["n_cells"] == 3 and m["ci90"][0] <= 2.0 <= m["ci90"][1]
    V[(1000, "gcc")] = []; assert diff_ci(V, CAPS, B_=1000)["n_cells"] == 2
    for c in CONTENTS: assert (Path("/path/to/alphartc/LLM4Band/testmedia") / f"qoe_labeled_{c}_320x240.yuv").is_file()
    t = (P / "c320_1000.profile").read_text(); assert "rate 1000" in t and "delay 50" in t and "loss 0" in t
    print("Self-test passed: judge, missing-cell rule, three sources, 1000 kbit/s profile")


def read_runs(content):
    s = json.load(open(K / f"jobs_main_{content}.json")); R = []
    for j in s["jobs"]:
        cap, a, rep = j["cond"].split("__"); cap = int(cap[1:]); d = K / f"main_{content}" / j["cond"]; tag = f"{j['arm']}__c320_{cap}__d0__r1"
        js = d / f"{tag}.json"; inv = list(d.glob("invalid_*"))
        r = {"content": content, "cond": j["cond"], "cap": cap, "arm_key": a, "rep": rep, "valid": js.is_file() and not inv, "invalid": [p.name for p in inv][:3] + ([] if js.is_file() else ["Missing result file"])}
        if js.is_file():
            x = json.load(open(js)); n = x["network"]
            r.update({"utility": n["utility"], "video_kbps": n.get("primary_video_payload_rate_kbps"), "queue_delay_mean_ms": n.get("queue_delay_mean_ms")})
        q = d / f"quality_{tag}.json"
        if q.is_file():
            y = json.load(open(q)); r.update({k: y.get(k) for k in ("vmaf", "ssim", "skip_events_gt2", "rendered_fps")})
        R.append(r)
    return R


def main():
    res = {}; allR = []; complete = True
    for content in CONTENTS:
        R = read_runs(content); allR += R; V = {}
        for k in ("utility", "vmaf"):
            V[k] = {}
            for r in R:
                if r["valid"] and r.get(k) is not None: V[k].setdefault((r["cap"], r["arm_key"]), []).append(r[k])
        complete &= all(sum(1 for r in R if r["valid"] and r["cap"] == c and r["arm_key"] == a) >= 2 for c in CAPS for a in ARMS)
        agg = {a: {c: {k: (lambda xs: round(st.mean(xs), 3) if xs else None)([r[k] for r in R if r["valid"] and r["arm_key"] == a and r["cap"] == c and r.get(k) is not None])
                       for k in ("utility", "vmaf", "ssim", "video_kbps", "queue_delay_mean_ms", "skip_events_gt2")} for c in CAPS} for a in ARMS}
        res[content] = {"sequence": CONTENTS[content], "utility_diff": diff_ci(V["utility"], CAPS), "vmaf_diff": diff_ci(V["vmaf"], CAPS), "by_arm_cap": agg,
                        "invalid_by_arm": {a: sum(1 for r in R if r["arm_key"] == a and not r["valid"]) for a in ARMS}}
    LOCAL = ROOT / "experiments/results/content320_ch_gcc_v1"; LOCAL.mkdir(parents=True, exist_ok=True)
    for f in (K / "result_v1.json", LOCAL / "result_v1.json"): f.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs.jsonl", "w") as f:
        for r in allR: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    fm = lambda m: "none" if not m else f"{m['D']:+.2f} [{m['ci90'][0]:+.2f}, {m['ci90'][1]:+.2f}]"
    b = ";".join(f"{CONTENTS[c]}: utility difference {fm(res[c]['utility_diff'])}, VMAF difference {fm(res[c]['vmaf_diff'])}, broken calls {json.dumps(res[c]['invalid_by_arm'])}" for c in CONTENTS) + \
        ". See result_v1.json for each cell."
    v = "holds" if complete else "inconclusive"
    print(v, b)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID1, "--metrics", json.dumps({c: {"utility": res[c]["utility_diff"], "vmaf": res[c]["vmaf_diff"]} for c in CONTENTS}, ensure_ascii=False, default=str),
       "--artifact", str(LOCAL / "result_v1.json"), "--artifact", str(LOCAL / "runs.jsonl"))
    ex("conclude", "--id", ID1, "--verdict", v, "--vs-criteria", "Measurement only, no verdict; \"holds\" here means only that each sequence has at least 2 valid runs per cell and arm." + b, "--basis", b,
       "--limitations", "320x240, 15 fps; three constant capacities, 3 repetitions per cell; single-machine testbed with two container pairs in parallel; Python GCC starts slower than native GCC; run script v29.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "jobs": jobs(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
