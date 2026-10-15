#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge of obsschema-llm-v1 (criteria in its pre-registration). A group succeeds when the median, over its evaluation calls, of the error under the mapping divided by the error under the true mapping is at most 1.2.
Holds: with real field names the LLM succeeds in at least 8 more groups than the better of DIST and NAME, and in at least 24; does not hold: in no more groups than the better one; otherwise inconclusive.
Mechanism reading: real names succeed in at least 8 more groups than masked names.
Reads eval_test<TAG>.json and writes judge_test<TAG>.json in experiments/results/obsschema_v1 (set the /path/to/llm4bandpp placeholder first).
Usage: python obsschema_judge_v1.py [--tag _open] [--selftest]
"""
import json, sys
from pathlib import Path
import numpy as np
O = Path("/path/to/llm4bandpp/experiments/results/obsschema_v1")


def judge(succ, n):
    best = max(succ["DIST"], succ["NAME"]); L = succ["LLM"]
    v = "holds" if (L >= best + 8 and L >= 24) else ("does not hold" if L <= best else "inconclusive")
    return v, {"best_nonllm": best, "mechanism_names_matter": succ["LLM"] - succ.get("LLM_OBF", 0) >= 8}


def selftest():
    assert judge({"DIST": 5, "NAME": 10, "LLM": 30, "LLM_OBF": 20}, 32)[0] == "holds"
    assert judge({"DIST": 5, "NAME": 30, "LLM": 30, "LLM_OBF": 20}, 32)[0] == "does not hold"
    assert judge({"DIST": 5, "NAME": 10, "LLM": 20, "LLM_OBF": 20}, 32)[0] == "inconclusive"
    assert judge({"DIST": 5, "NAME": 20, "LLM": 26, "LLM_OBF": 20}, 32)[0] == "inconclusive"
    print("Self-test passed")


def main(tag):
    E = json.load(open(O / f"eval_test{tag}.json")); G = {g["id"]: g for g in json.load(open(O / "groups.json"))["groups"]}; M = ["DIST", "NAME", "LLM", "LLM_OBF", "ORACLE"]
    succ = {m: 0 for m in M}; per = {}; rows = []
    for gid, res in E["results"].items():
        med = {m: float(np.nanmedian([r.get(m, np.nan) for r in res.values()])) for m in M}; g = G[int(gid)]
        for m in M:
            ok = bool(med[m] <= 1.2); succ[m] += ok; per.setdefault(g["schema"], {k: 0 for k in M}); per[g["schema"]][m] += ok
        rows.append({"id": int(gid), "schema": g["schema"], "scen": g["scen"], **med})
    n = len(E["results"]); v, info = judge(succ, n)
    res = {"verdict": v if n == 32 else "incomplete, not adjudicated", "n": n, "success": succ, "per_schema": per, **info, "rows": rows}
    (O / f"judge_test{tag}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1)); print(json.dumps({k: res[k] for k in ("verdict", "n", "success", "per_schema", "best_nonllm", "mechanism_names_matter")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main(sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "")
