#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evaluation windows of obsschema-closedloop-v1 (rule obsschema_cl_v1, seed 20261003): Norwegian 3G ferry and bus traces not
used by any profile of this repository (header trace_id of the .profile files under scripts/alphartc and in the testbed's
staleness_profiles directory). The window rule is that of coldstart_real_v1 (120 s grid, no missing second, mean 200 to
4000 kbit/s, at most 12 clamped seconds); one eligible window is drawn per trace and 4 traces of each kind at random:
sc_1 to sc_4 are ferry, sc_5 to sc_8 bus. Profiles are written as in make_obsrepair_cl_profiles_v1.py.
"""
import json, random, re
from pathlib import Path
HERE = Path(__file__).resolve(); ROOT = HERE.parents[3]; CORPUS = ROOT / "data/llm_kp/corpus_v1.jsonl"; OUT = HERE.parent / "profiles" / "obsschema_cl"
import sys; sys.path.insert(0, str(HERE.parent)); import make_coldstart_real_profiles_v1 as P  # noqa: E402
used = set()
for p in list((ROOT / "scripts/alphartc").rglob("*.profile")) + list(Path("/path/to/alphartc/LLM4Band/staleness_profiles").glob("*.profile")):
    if OUT in p.parents: continue
    for m in re.finditer(r"trace_id=(\S+)", p.read_text(errors="ignore")): used.add(m.group(1))
rows = [json.loads(l) for l in open(CORPUS)]; rng = random.Random(20261003); OUT.mkdir(parents=True, exist_ok=True); rec = []; pools = {}
for mob in ("ferry", "bus"):
    pool = []
    for tr in sorted((r for r in rows if r["source"] == "norway_hsdpa" and r["mobility_or_env"] == mob and r["capacity_mbps"] is not None and r["trace_id"] not in used), key=lambda r: r["trace_id"]):
        w = P.windows(tr)
        if w: pool.append(rng.choice(w))
    pools[mob] = len(pool); assert len(pool) >= 4, (mob, len(pool))
    for w in rng.sample(pool, 4):
        name = f"sc_{len(rec) + 1}"
        lines = [f"# trace_id={w['trace_id']} source=norway_hsdpa mobility={mob} window=[{w['start_s']},{w['start_s'] + 120})s mean_kbps={w['mean_kbps']:.1f} clamped_seconds={w['n_clamped']}",
                 f"# corpus_v1 sha256={P.sha(CORPUS)[:16]} rule=obsschema_cl_v1 seed=20261003; 1s values, Mbps to kbit/s, round to int, floor 30"]
        for j, r in enumerate(w["rates"]):
            lines.append(f"rate {r}")
            if j == 0: lines += ["delay 50", "loss 0"]
            lines.append("wait 1")
        p = OUT / f"{name}.profile"; p.write_text("\n".join(lines) + "\n"); rec.append({"profile": p.name, "mobility": mob, "trace_id": w["trace_id"], "start_s": w["start_s"], "mean_kbps": w["mean_kbps"], "sha256": P.sha(p)})
(OUT / "provenance.json").write_text(json.dumps({"rule": "obsschema_cl_v1", "seed": 20261003, "excluded_used_traces": len(used), "fresh_traces_in_pool": pools, "profiles": rec}, ensure_ascii=False, indent=1))
print("traces already used", len(used), "candidate", pools, "; select", [(r["profile"], r["mobility"], round(r["mean_kbps"])) for r in rec])
