#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trace profiles of obsrepair-closedloop-v1 (rule obsrepair_cl_v1, seed 20261002): Norwegian 3G bus traces not used by
coldstart_real_v1, with the window rule of coldstart_real_v1 (120 s grid, no missing second, mean 200 to 4000 kbit/s, at
most 12 clamped seconds); one eligible window per trace, then 9 traces at random: the first 3 are the early evidence calls
ev_1 to ev_3, the other 6 the evaluation windows cl_1 to cl_6. Profiles are written as in make_lowbw_real_profiles_v1.py.
"""
import json, random
from pathlib import Path
HERE = Path(__file__).resolve(); ROOT = HERE.parents[3]; CORPUS = ROOT / "data/llm_kp/corpus_v1.jsonl"; OUT = HERE.parent / "profiles" / "obsrepair_cl"
import sys; sys.path.insert(0, str(HERE.parent)); import make_coldstart_real_profiles_v1 as P  # noqa: E402
used = {p["trace_id"] for p in json.load(open(HERE.parent / "profiles/coldstart_real/provenance.json"))["profiles"]}
rows = [json.loads(l) for l in open(CORPUS)]; rng = random.Random(20261002); OUT.mkdir(parents=True, exist_ok=True)
pool = []
for tr in sorted((r for r in rows if r["source"] == "norway_hsdpa" and r["mobility_or_env"] == "bus" and r["capacity_mbps"] is not None and r["trace_id"] not in used), key=lambda r: r["trace_id"]):
    w = P.windows(tr)
    if w: pool.append(rng.choice(w))
chosen = rng.sample(pool, 9); rec = []
for i, w in enumerate(chosen):
    name = f"ev_{i + 1}" if i < 3 else f"cl_{i - 2}"
    lines = [f"# trace_id={w['trace_id']} source=norway_hsdpa mobility=bus window=[{w['start_s']},{w['start_s'] + 120})s mean_kbps={w['mean_kbps']:.1f} clamped_seconds={w['n_clamped']}",
             f"# corpus_v1 sha256={P.sha(CORPUS)[:16]} rule=obsrepair_cl_v1 seed=20261002; 1s values, Mbps to kbit/s, round to int, floor 30"]
    for j, r in enumerate(w["rates"]):
        lines.append(f"rate {r}")
        if j == 0: lines += ["delay 50", "loss 0"]
        lines.append("wait 1")
    p = OUT / f"{name}.profile"; p.write_text("\n".join(lines) + "\n"); rec.append({"profile": p.name, "trace_id": w["trace_id"], "start_s": w["start_s"], "mean_kbps": w["mean_kbps"], "sha256": P.sha(p)})
(OUT / "provenance.json").write_text(json.dumps({"rule": "obsrepair_cl_v1", "seed": 20261002, "fresh_traces_in_pool": len(pool), "profiles": rec}, ensure_ascii=False, indent=1))
print("candidate traces", len(pool), "; select", [(r["profile"], round(r["mean_kbps"])) for r in rec])
