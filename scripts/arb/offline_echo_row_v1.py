#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Table I row of offline-trivial-baselines-v1: the receiving-rate echo, which learns nothing and reports at every step the
receiving rate of the latest 60 ms window (column 0 of feat_short in arb_perstep_dump_v1, divided by 1e6), scored with
exactly the per-call metrics and the 870 and 712 aggregations of main_table_unified_v1; a constant 0.3 Mb/s is computed
as a further reference. The result file of main_table_unified_v1 is not changed.
Gate: the same computation applied to Pioneer must reproduce main_table_unified_v1/result.json within a relative 1e-12.
"""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/arb"))
import switch_causal_control_v1 as S  # noqa: E402
OUT = ROOT / "experiments/results/offline_trivial_baselines_v1"; OUT.mkdir(parents=True, exist_ok=True); MET = ["mse", "e_plus", "e_minus", "err"]
z = np.load(S.NPZ, allow_pickle=True); off = z["offsets"]; TR = z["truth_mbps"].astype(np.float64); keys = [str(k) for k in z["keys"]]; dirs = [str(d) for d in z["dirs"]]
scen = np.array([S.SCEN[d] for d in dirs]); n = len(keys)
clean_names = set(json.load(open(ROOT / "experiments/results/_deleak.json"))["main_validation"]["leakage_free_file_names"]); clean = np.array([k.split("/")[-1] in clean_names for k in keys])


def fm(P):
    out = np.zeros((n, 4))
    for i in range(n):
        a, tr = P[off[i]:off[i + 1]], TR[off[i]:off[i + 1]]
        with np.errstate(divide="ignore", invalid="ignore"): rel = (a - tr) / tr
        out[i] = [np.nanmean((a - tr) ** 2), np.nanmean(np.maximum(rel, 0)), np.mean(np.where(np.isnan(rel), 0.0, np.maximum(-rel, 0))), np.mean(np.where(np.isnan(rel), 1.0, np.minimum(1.0, np.abs(rel))))]
    return out


def agg(P):
    M = fm(P); r = {}
    for sn, mk in (("870", np.ones(n, bool)), ("712", clean)):
        r[sn] = {s: {MET[j]: float(M[(scen == s) & mk][:, j].mean()) for j in range(4)} for s in S.ORDER}; r[sn]["macro_mse"] = float(np.mean([r[sn][s]["mse"] for s in S.ORDER]))
    return r


ref = json.load(open(ROOT / "experiments/results/main_table_unified_v1/result.json"))["rows"]["Pioneer"]; got = agg(z["pred__Pioneer"].astype(np.float64))
for sn in ("870", "712"):
    for s in S.ORDER:
        for m in MET: assert abs(got[sn][s][m] - ref[sn][s][m]) <= 1e-12 * max(1.0, abs(ref[sn][s][m])), ("Gate: Pioneer recomputation is inconsistent with the main table", sn, s, m)
rows = {"ReceiveRateEcho": agg(z["feat_short"][:, 0].astype(np.float64) / 1e6), "Constant0.3": agg(np.full(len(TR), 0.3))}
(OUT / "result.json").write_text(json.dumps({"source": str(S.NPZ), "gate_pioneer_identical": True, "rows": rows}, ensure_ascii=False, indent=1))
for k, r in rows.items(): print(k, {sn: {s: round(r[sn][s]["mse"], 3) for s in S.ORDER} | {"macro": round(r[sn]["macro_mse"], 2)} for sn in ("870", "712")})
