#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows of obsschema-closedloop-llm4bandpp-v1 (rule obsschema_rt_v1, seed 20261007): the rule of obsschema_cl2_v1 with
another seed and output directory, taking only the 8 evaluation windows rt_1 to rt_8; the evidence windows are es_1 to
es_3 of obsschema-closedloop-v2. The rule of obsschema_cl2_v1: Norwegian 3G traces not used by any profile of this
repository (header trace_id of the .profile files under scripts/alphartc and in the testbed's staleness_profiles
directory); 120 s grid, no missing second, mean 200 to 4000 kbit/s, at most 12 clamped seconds; one eligible window per
trace, car, train, tram and bus traces in one pool. Profiles are written as in make_obsrepair_cl_profiles_v1.py.
"""
import json, random, re
from pathlib import Path
HERE = Path(__file__).resolve(); ROOT = HERE.parents[3]; CORPUS = ROOT / "data/llm_kp/corpus_v1.jsonl"; OUT = HERE.parent / "profiles" / "obsschema_rt"
import sys; sys.path.insert(0, str(HERE.parent)); import make_coldstart_real_profiles_v1 as P  # noqa: E402
used = set()
for p in list((ROOT / "scripts/alphartc").rglob("*.profile")) + list(Path("/path/to/alphartc/LLM4Band/staleness_profiles").glob("*.profile")):
    if OUT in p.parents: continue
    for m in re.finditer(r"trace_id=(\S+)", p.read_text(errors="ignore")): used.add(m.group(1))
rows = [json.loads(l) for l in open(CORPUS)]; rng = random.Random(20261007); OUT.mkdir(parents=True, exist_ok=True); rec = []; pools = {}
pool = []
for mob in ("car", "train", "tram", "bus"):
    for tr in sorted((r for r in rows if r["source"] == "norway_hsdpa" and r["mobility_or_env"] == mob and r["capacity_mbps"] is not None and r["trace_id"] not in used), key=lambda r: r["trace_id"]):
        w = P.windows(tr)
        if w: x = rng.choice(w); x["mob"] = mob; pool.append(x)
    pools[mob] = sum(1 for x in pool if x.get("mob") == mob)
assert len(pool) >= 8, len(pool)
if True:
    for w in rng.sample(pool, 8):
        mob = w["mob"]; name = f"rt_{len(rec) + 1}"
        lines = [f"# trace_id={w['trace_id']} source=norway_hsdpa mobility={mob} window=[{w['start_s']},{w['start_s'] + 120})s mean_kbps={w['mean_kbps']:.1f} clamped_seconds={w['n_clamped']}",
                 f"# corpus_v1 sha256={P.sha(CORPUS)[:16]} rule=obsschema_rt_v1 seed=20261007; 1s values, Mbps to kbit/s, round to int, floor 30"]
        for j, r in enumerate(w["rates"]):
            lines.append(f"rate {r}")
            if j == 0: lines += ["delay 50", "loss 0"]
            lines.append("wait 1")
        p = OUT / f"{name}.profile"; p.write_text("\n".join(lines) + "\n"); rec.append({"profile": p.name, "mobility": mob, "trace_id": w["trace_id"], "start_s": w["start_s"], "mean_kbps": w["mean_kbps"], "sha256": P.sha(p)})
(OUT / "provenance.json").write_text(json.dumps({"rule": "obsschema_rt_v1", "seed": 20261007, "excluded_used_traces": len(used), "fresh_traces_in_pool": pools, "profiles": rec}, ensure_ascii=False, indent=1))
print("traces already used", len(used), "candidate", pools, "; select", [(r["profile"], r["mobility"], round(r["mean_kbps"])) for r in rec])
