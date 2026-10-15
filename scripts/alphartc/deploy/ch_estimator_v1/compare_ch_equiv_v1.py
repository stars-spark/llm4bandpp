#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equivalence check of the C-H estimator module: compares the per-call metrics of a CPU re-evaluation (our evaluator
eval_value_per_file.py with the generated ch_estimator_v1.py as estimator.py) with the per-call file written when the run
was evaluated on GPU with the training code (for example experiments/results/nl_2x2_v1/eval/CHs1.json).
Gate: all 870 calls present, largest relative difference in per-call MSE below 1e-3, relative difference in macro MSE
below 1e-4. As a discrimination control, the CPU result of another seed must fail the gate against the selected seed.
Usage: python3 compare_ch_equiv_v1.py CPU_RESULT.json REFERENCE.json
"""
import json, sys, statistics as st
cpu = json.load(open(sys.argv[1])); ref = json.load(open(sys.argv[2]))
rows = {x["file"]: x for x in cpu.get("files", cpu.get("rows", []))}; rf = {x["file"]: x for x in ref["files"]}
assert len(rf) == 870, len(rf)
miss = sorted(set(rf) - set(rows)); rel = [abs(float(rows[f]["mse"]) - float(x["mse"])) / max(abs(float(x["mse"])), 1e-12) for f, x in rf.items() if f in rows]
def macro(d):
    g = {}
    for v in d.values(): g.setdefault(v["scenario"], []).append(float(v["mse"]))
    return st.mean(st.mean(xs) for xs in g.values())
m_cpu, m_ref = macro(rows), macro(rf); mrel = abs(m_cpu - m_ref) / m_ref
ok = not miss and max(rel) < 1e-3 and mrel < 1e-4
print(json.dumps({"cpu": sys.argv[1], "ref": sys.argv[2], "n_files_cpu": len(rows), "missing": len(miss), "max_rel_file_mse": max(rel), "median_rel_file_mse": st.median(rel),
                  "macro_cpu": m_cpu, "macro_ref": m_ref, "macro_rel": mrel, "pass": ok}, ensure_ascii=False))
sys.exit(0 if ok else 1)
