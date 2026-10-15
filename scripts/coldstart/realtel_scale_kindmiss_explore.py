#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exploratory, not judged: on the 12 client stacks, score the different-definition cells as features to be declared missing, as realtel_revise_v1.kind_as_none does for the seven specifications.
The designer and the seven baselines are rescored with the same full scoring, and the share of such cells where a method mapped a field is reported.
Designer answers and baseline mappings come from the realtel-scale-v1 result files; nothing is called again.
Writes experiments/results/realtel_scale_v1/kindmiss_explore.json. Usage: python3 scripts/coldstart/realtel_scale_kindmiss_explore.py
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_scale_v1 as RS  # noqa: E402


def main():
    S = RS.load_sources(); S2 = {n: dict(s, truth=[x if x[0] != "kind" else ["none"] for x in s["truth"]]) for n, s in S.items()}
    L = {}
    for j in map(json.loads, open(RS.OUT / "llm_deepseek.jsonl")): L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    for n in S:
        for k in range(M.NPRES): L.setdefault((n, k), None)
    B = RS.base_maps(S)
    out = {}
    for tag, SS in (("main", S), ("kind_as_missing", S2)):
        v, m = M.judge(RS.rows(SS, L), {b: RS.rows(SS, {(n, 0): B[b][n] for n in S}) for b in B})
        out[tag] = {"ba_llm": m["ba_llm"], "best_base": m["best_base"], "ba_best": m["ba_base"][m["best_base"]], "delta": m["delta"], "ci90": m["ci90"], "false_map_rate": m["false_map_rate"], "rule_verdict": v}
    (RS.OUT / "kindmiss_explore.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
