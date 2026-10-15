#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch lowbw-loss1-env6-v1: deployed system against LLM4Band, both with probing envelope v6, at constant 100 to 400 kbit/s with 1% random loss (320x240 Mobcal, 15 fps).
Criterion as lowbw-ch-vs-conf-env6-v1: utility difference over four cells, within-cell bootstrap 90% interval, non-inferiority margin -5.27.
Usage: lowbw_loss1_env6_v1.py jobs OUT | judge [--selftest]
"""
import json, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/lowbw-loss1-env6-v1"); ID1 = "lowbw-loss1-env6-v1"
P = ROOT / "scripts/alphartc/deploy/profiles/lowbw_loss1"; CAPS = [100, 200, 300, 400]; REPS = 3
ARMS = {"ch6": ("arm_ch_x", {"STALENESS_ENVELOPE": "6", "STALENESS_MIN_BPS_FLOOR": "1"}), "cf6": ("arm_llm4band_conf_x", {"STALENESS_ENVELOPE": "6"})}
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402
import lowbw_lambda_mid_v1 as M


def spec(name, J, pairs):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": name, "K": str(K / name), "log": str(ROOT / "logs/lowbw_loss1_env6_v1.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v29.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 1, "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def jobs(out):
    J = []; order = list(ARMS); blk = 0
    for rep in range(1, REPS + 1):
        for cap in CAPS:
            rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
            for a in rot:
                arm, env = ARMS[a]; J.append({"cond": f"c{cap}__{a}__r{rep}", "arm": arm, "profile": str(P / f"nlc_{cap}_l1.profile"), "env": dict(env)})
    Path(out).write_text(json.dumps(spec("main", J, [1, 2]), ensure_ascii=False, indent=1)); print("jobs:", len(J))


def read_runs():
    s = json.load(open(K / "jobs_main.json")); R = []
    for j in s["jobs"]:
        cap, a, rep = j["cond"].split("__"); cap = int(cap[1:]); d = K / "main" / j["cond"]; tag = f"{j['arm']}__nlc_{cap}_l1__d0__r1"
        js = d / f"{tag}.json"; inv = list(d.glob("invalid_*"))
        r = {"cond": j["cond"], "cap": cap, "arm_key": a, "arm": j["arm"], "rep": rep, "valid": js.is_file() and not inv, "invalid": [p.name for p in inv][:3] + ([] if js.is_file() else ["Missing result file"])}
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
        if r["valid"]: U.setdefault((r["cap"], r["arm_key"]), []).append(r["utility"])
    v, m = M.judge(U, "ch6", "cf6")
    agg = {a: {c: {k: (lambda xs: round(st.mean(xs), 2) if xs else None)([r[k] for r in R if r["valid"] and r["arm_key"] == a and r["cap"] == c and r.get(k) is not None])
                   for k in ("utility", "vmaf", "video_kbps", "queue_delay_mean_ms")} for c in CAPS} for a in ARMS}
    brk = {a: sum(1 for r in R if r["arm_key"] == a and not r["valid"]) for a in ARMS}
    import floor_smoke_v1 as FS; fl = {r["cond"]: FS.floor_stats(K / "main" / r["cond"]) for r in R if r["arm_key"] == "ch6"}
    res = {"primary": {"verdict": v, **m}, "by_arm_cap": agg, "invalid_by_arm": brk, "floor_report": fl, "n_runs": len(R), "invalid": {r["cond"]: r["invalid"] for r in R if not r["valid"]}}
    LOCAL = ROOT / "experiments/results/lowbw_loss1_env6_v1"; LOCAL.mkdir(parents=True, exist_ok=True)
    for f in (K / "result_v1.json", LOCAL / "result_v1.json"): f.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    with open(LOCAL / "runs.jsonl", "w") as f:
        for r in R: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    b = (f"Primary endpoint D (deployed minus LLM4Band, both behind probing envelope v6, 1% random loss, four cells equally weighted){m['D']:+.2f}, 90% interval [{m['ci90'][0]:+.2f}, {m['ci90'][1]:+.2f}]; per cell {json.dumps({c: round(x, 2) for c, x in m['cell_diff'].items()})}; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all deployed-system runs invalid {m['all_invalid_cells'] or 'none'}, cells excluded because all LLM4Band runs were invalid {m['dropped_cells_no_ref'] or 'none'}. Report only: per arm per cell {json.dumps(agg, ensure_ascii=False)}; broken calls {json.dumps(brk)}/12 each; total steps at the 5 kb/s floor {sum((x or {}).get('floor_hits') or 0 for x in fl.values())}, total steps with estimate 0 {sum((x or {}).get('est_zero') or 0 for x in fl.values())}.")
    print(v, b)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID1, "--metrics", json.dumps({k: m[k] for k in ("D", "ci90", "cell_diff", "severe_cells", "all_invalid_cells", "n_cells_used")} | {"invalid_by_arm": brk}, ensure_ascii=False, default=str),
       "--artifact", str(LOCAL / "result_v1.json"), "--artifact", str(LOCAL / "runs.jsonl"))
    if v == "inconclusive": ex("note", "--id", ID1, "Fewer than 3 usable cells, no conclusion is recorded." + b); return
    ex("conclude", "--id", ID1, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (verbatim the same as lowbw-ch-vs-conf-env6-v1: non-inferiority margin 5.27 utility points, safety line 10 points and cells with all deployed-system runs invalid)." + b, "--basis", b,
       "--limitations", "3 runs per cell; 320x240 Mobcal at 15 fps; random loss 1%, one-way delay 50 ms; two container pairs in parallel on a single-machine testbed; run script v29; the earlier low-bandwidth batches used 50 ms round trip, this one 50 ms one way.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "jobs": jobs(sys.argv[2])
    elif c == "judge": M.selftest() if "--selftest" in sys.argv else main()
