#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main table under one protocol (registered experiment main-table-unified-v1): evaluation only, no retraining.
Every estimator with a per-step dump is scored by the same code for MSE, overestimation, underestimation and clipped error, on the 870-call set and the 712-call leakage-free subset.
Inputs: arb_perstep_dump_v1 (Pioneer, the challenge baseline, Schaferct-R, supervised MLP), llm4bandpp_perstep_dump_v1 and LLM4Band (llm4band_conf_perstep_dump_v1) if present,
and any per-step dump with pred, lens and keys under experiments/results/main_table_unified_v1/extra/ (file name = row name).
Self-check: macro MSE of the one-token LLM variant, Pioneer and Schaferct-R must be within 0.5% of the registered 6.743, 7.37 and 7.07, or the script stops.
Writes result.json and prints both tables. Usage: python main_table_unified_v1.py
"""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/arb"))
import switch_causal_control_v1 as S  # noqa: E402
OUT = ROOT / "experiments/results/main_table_unified_v1"; (OUT / "extra").mkdir(parents=True, exist_ok=True); MET = ["mse", "e_plus", "e_minus", "err"]
z = np.load(S.NPZ, allow_pickle=True); off = z["offsets"]; TR = z["truth_mbps"].astype(np.float64); keys = [str(k) for k in z["keys"]]; dirs = [str(d) for d in z["dirs"]]; scen = np.array([S.SCEN[d] for d in dirs]); n = len(keys)
clean_names = set(json.load(open(ROOT / "experiments/results/_deleak.json"))["main_validation"]["leakage_free_file_names"]); clean = np.array([k.split("/")[-1] in clean_names for k in keys])
rows = {a: z[f"pred__{a}"].astype(np.float64) for a in S.MAIN}
for name, p in [("LLM4band++ (Qwen)", "llm4bandpp_perstep_dump_v1/perstep_llm4bandpp.npz"), ("LLM4Band conference version online weights (Qwen)", "llm4band_conf_perstep_dump_v1/perstep_llm4band_conf.npz")] + [(f.stem, str(f.relative_to(ROOT / "experiments/results"))) for f in sorted((OUT / "extra").glob("*.npz"))]:
    f = ROOT / "experiments/results" / p
    if not f.exists(): print("Missing, skip:", name); continue
    c = np.load(f, allow_pickle=True); assert [str(k) for k in c["keys"]] == keys and np.array_equal(c["lens"], np.diff(off)), f"{name} not aligned with baseline export"; rows[name] = c["pred"].astype(np.float64)


def fm(P):
    out = np.zeros((n, 4))
    for i in range(n):
        a, tr = P[off[i]:off[i + 1]], TR[off[i]:off[i + 1]]
        with np.errstate(divide="ignore", invalid="ignore"): rel = (a - tr) / tr
        out[i] = [np.nanmean((a - tr) ** 2), np.nanmean(np.maximum(rel, 0)), np.mean(np.where(np.isnan(rel), 0.0, np.maximum(-rel, 0))), np.mean(np.where(np.isnan(rel), 1.0, np.minimum(1.0, np.abs(rel))))]
    return out


res = {"n_870": {s: int((scen == s).sum()) for s in S.ORDER}, "n_712": {s: int(((scen == s) & clean).sum()) for s in S.ORDER}, "rows": {}}
for name, P in rows.items():
    M = fm(P); r = {}
    for sn, mk in (("870", np.ones(n, bool)), ("712", clean)):
        r[sn] = {s: {MET[j]: float(M[(scen == s) & mk][:, j].mean()) for j in range(4)} for s in S.ORDER}; r[sn]["macro_mse"] = float(np.mean([r[sn][s]["mse"] for s in S.ORDER]))
    res["rows"][name] = r
ref = {"LLM4band++ (Qwen)": 6.743, "Pioneer": 7.37, "Schaferct(retrained)": 7.07}
for k, v in ref.items():
    got = res["rows"][k]["870"]["macro_mse"]; assert abs(got - v) / v <= 0.005, f"{k} macro MSE {got:.4f} does not match registered {v}"
pi = res["rows"]["Pioneer"]["870"]["macro_mse"]; res["improvement_over_pioneer_pct"] = {k: 100 * (pi - r["870"]["macro_mse"]) / pi for k, r in res["rows"].items()}
(OUT / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
for sn in ("870", "712"):
    print(f"\n[{sn}] per-cell MSE e+ e-, scenario order {S.ORDER}, last column macro MSE")
    for k, r in res["rows"].items(): print(f"{k:34s}" + " | ".join("%7.3f %5.3f %5.3f" % (r[sn][s]["mse"], r[sn][s]["e_plus"], r[sn][s]["e_minus"]) for s in S.ORDER) + " | %6.3f" % r[sn]["macro_mse"])
print("\nMacro MSE improvement relative to Pioneer (870, percentage)", {k: round(v, 2) for k, v in res["improvement_over_pioneer_pct"].items()})
