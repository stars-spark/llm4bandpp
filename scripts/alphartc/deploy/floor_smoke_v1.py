#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exploratory smoke test of the 5 kbps estimate floor on the deployed estimator without envelope; no registered criterion, not paper evidence.
An estimate of exactly 0 makes the sender pause and the call break; the floor keeps the estimate at or above 5 kbps (AlphaRTC GetMinBitrateBps). Seven runs at constant 100, 200 and 300 kbps, 320x240 at 15 fps.
Usage: floor_smoke_v1.py jobs | summarize
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy"))
import guard_smoke_v1 as GS
K = Path("/path/to/testbed/results/ch-floor-smoke-v1"); ID = "ch-min-floor-smoke-explore-v1"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v20.sh"
ENV = {"STALENESS_ENVELOPE": "0", "STALENESS_COLLECTOR": "v6", "STALENESS_MIN_BPS_FLOOR": "1"}
PLAN = [(100, 3), (200, 2), (300, 2)]


def jobs():
    J = []
    for rep in (1, 2, 3):
        for cap, n in PLAN:
            if rep <= n: J.append({"cond": f"c{cap}__f1__r{rep}", "arm": "arm_ch_x", "profile": str(GS.P / f"nlc_{cap}.profile"), "env": dict(ENV)})
    s = GS.low_spec(J); s.update({"K": str(K / "low"), "log": str(ROOT / "logs/floor_smoke_v1.log"), "runner": str(RUNNER)})
    K.mkdir(parents=True, exist_ok=True); (K / "jobs_low.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J), s["runner"])


def floor_stats(d):
    O = [o for o in GS.obs_rows(d) if "est_bps" in o]
    if not O: return None
    return {"floor_seen": any("floor_hit" in o for o in O), "floor_hits": sum(bool(o.get("floor_hit")) for o in O), "est_min_kbps": round(min(o["est_bps"] for o in O) / 1000, 1),
            "est_zero": sum(o["est_bps"] <= 0 for o in O), "raw_nonpos": sum((o.get("model_raw_bps") or 1) <= 0 for o in O), "obs_end_s": round((O[-1]["t_ms"] - O[0]["t_ms"]) / 1000, 1)}


def summarize():
    R = []
    for j in json.load(open(K / "jobs_low.json"))["jobs"]:
        cap = int(j["cond"].split("__")[0][1:]); d = K / "low" / j["cond"]
        r = {"cond": j["cond"], "cap": cap, **(GS.low_run(d, j["arm"], cap) if d.is_dir() else {"valid": False, "missing": True})}; r["floor"] = floor_stats(d) if d.is_dir() else None; R.append(r)
    ref = {}
    for cap, _ in PLAN:
        for a, arm in (("ch0", "arm_ch_x"), ("cf0", "arm_llm4band_conf_x")):
            rs = [GS.low_run(GS.REF_LOW / "main" / f"c{cap}__{a}__r{rep}", arm, cap) for rep in (1, 2, 3)]
            ref[f"c{cap}__{a}"] = {"valid": sum(x["valid"] for x in rs), "utility": [round(x["utility"], 1) if x.get("valid") else None for x in rs]}
    out = {"runs": R, "ref_low": ref}; LOCAL = ROOT / "experiments/results/ch_floor_smoke_v1"; LOCAL.mkdir(parents=True, exist_ok=True)
    for p in (LOCAL / "summary.json", K / "summary.json"): p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    f = []
    for cap, _ in PLAN:
        rs = [r for r in R if r["cap"] == cap]
        f.append(f"{cap} kbps: valid {sum(r['valid'] for r in rs)}/{len(rs)}, utility {[round(r['utility'], 1) if r.get('valid') else None for r in rs]}, steps at the 5 kb/s floor {[(r['floor'] or {}).get('floor_hits') for r in rs]}, steps with estimate 0 {[(r['floor'] or {}).get('est_zero') for r in rs]}, observation ends at {[(r['floor'] or {}).get('obs_end_s') for r in rs]} s; C-H without the floor in an earlier batch {ref[f'c{cap}__ch0']}, conference version {ref[f'c{cap}__cf0']}")
    finding = ";".join(f) + f". All startup logs correct: {all(r.get('boot_ok') for r in R if not r.get('missing'))}."
    print(finding)
    subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "explore", "--id", ID,
                    "--what", "C-H without envelope, with only the 5 kb/s estimate floor (the minimum congestion-control rate of AlphaRTC and libwebrtc); 100 kbps 3 times, 200 and 300 kbps 2 times each; run script v20, entry point v15, arm module v8.",
                    "--finding", finding, "--why", "In ch-startup-guard-smoke-explore-v1 every failed run had estimates of 0 and the sender stopped sending; the startup guard did not prevent this, so this batch tries the 5 kb/s floor.",
                    "--parent", "ch-startup-guard-smoke-explore-v1", "--artifact", str(LOCAL / "summary.json"),
                    "--next", ""], check=True)


if __name__ == "__main__":
    {"jobs": jobs, "summarize": summarize}[sys.argv[1]]()
