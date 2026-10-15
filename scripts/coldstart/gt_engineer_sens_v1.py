#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exploratory, post hoc: BA on the 12 client stacks with the external engineer's blind labels as ground truth; no registered verdict changes.
The labels come from gt-blind-expert-v1 (pages S08 to S19, the 12 stacks): for same, the engineer's field, differencing and scale; none and different definition as labelled.
The designer mappings (llm_deepseek.jsonl), the seven baseline mappings (base_maps), the scoring M.score and the judge M.judge are those of realtel_scale_v1.cmd_judge; only the labels change.
A cell where the engineer chose a field that is not among the stack's candidate fields is left unscored and counted.
Writes experiments/results/gt_blind_expert_v1/engineer_truth_sens_v1.json.
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_scale_v1 as RS  # noqa: E402
M = RS.M
G = json.load(open(ROOT / "experiments/results/gt_blind_expert_v1/result.json"))
S = RS.load_sources(); names = list(S)
L = {}
for j in map(json.loads, open(RS.OUT / "llm_deepseek.jsonl")): L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
for n in S:
    for k in range(M.NPRES): L.setdefault((n, k), None)
B = RS.base_maps(S)
pages = sorted({c["page"] for c in G["cells"]}); stack_pages = [p for p in pages if int(p[1:]) >= 8]
assert len(stack_pages) == 12, stack_pages
T, dropped, changed = {}, [], 0
for p, n in zip(stack_pages, names):
    cells = sorted([c for c in G["cells"] if c["page"] == p], key=lambda c: c["k"]); assert len(cells) == 15, (p, len(cells))
    fields = [f[0] for f in S[n]["fields"]]; t = []
    for c in cells:
        if c["label"] == "same":
            if c.get("field") in fields: t.append(["same", c["field"], bool(c.get("diff")), float(c.get("scale") or 1.0)])
            else: t.append(["kind"]); dropped.append((n, c["k"], c.get("field")))
        else: t.append([c["label"]])
    changed += sum(1 for a, b in zip(t, S[n]["truth"]) if a != b); T[n] = t
Se = {n: dict(s, truth=T[n]) for n, s in S.items()}
# Engineer's labels first; the call after it uses the current labels and must reproduce the registered 0.920 and 0.560.
v, m = M.judge(RS.rows(Se, L), {b: RS.rows(Se, {(n, 0): B[b][n] for n in S}) for b in B})
v0, m0 = M.judge(RS.rows(S, L), {b: RS.rows(S, {(n, 0): B[b][n] for n in S}) for b in B})
cnt = lambda TT, c: sum(x[0] == c for tt in TT.values() for x in tt)
res = {"current_truth": {k: m0[k] for k in ("ba_llm", "ba_base", "best_base", "delta", "ci90")}, "engineer_truth": {"verdict_rule_only": v, **{k: m[k] for k in ("ba_llm", "ba_base", "best_base", "delta", "ci90")}},
       "engineer_counts": {c: cnt(T, c) for c in ("same", "none", "kind")}, "current_counts": {c: cnt({n: s["truth"] for n, s in S.items()}, c) for c in ("same", "none", "kind")},
       "cells_changed": changed, "engineer_field_not_in_candidates": dropped}
out = ROOT / "experiments/results/gt_blind_expert_v1/engineer_truth_sens_v1.json"; out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("Current ground truth: designer BA", round(m0["ba_llm"], 3), "best baseline", m0["best_base"], round(m0["ba_base"][m0["best_base"]], 3))
print("Engineer's labels as ground truth: designer BA", round(m["ba_llm"], 3), "best baseline", m["best_base"], round(m["ba_base"][m["best_base"]], 3), "Δ", round(m["delta"], 3), [round(x, 3) for x in m["ci90"]])
print("label counts: engineer", res["engineer_counts"], "current", res["current_counts"], "cells changed", changed, "cells left unscored (engineer's field is not a candidate field)", len(dropped))
