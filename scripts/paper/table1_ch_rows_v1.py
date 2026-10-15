#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered experiment table1-ch-paired-v1: the deployed-estimator row of Table I and its paired offline intervals.
Deployed row: per-call MSE of cell C-H, seeds 0 to 2, from experiments/results/nl_2x2_v1/eval/CHs{0,1,2}.json (eval_value_per_file.py, the main-table
MSE definition: nanmean of the per-step squared error of each call). Other rows: per-call MSE from the per-step exports of main-table-unified-v1.
Gates: Pioneer, Schaferct-R and the one-token LLM variant reproduce the main-table macro MSE within 1e-9; C-H seed 1 macro lies in [5.795301, 5.795341].
Intervals: (reference - deployed)/reference x 100, scenario-stratified resampling of calls with replacement (10,000 draws, fixed seed), 2.5th and
97.5th percentiles, for the 870 calls and the 712-call leakage-free subset. Output: experiments/results/table1_ch_paired_v1/result.json.
Usage: python3 scripts/paper/table1_ch_rows_v1.py
"""
import csv, json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/arb"))
import switch_causal_control_v1 as S  # noqa: E402
R = ROOT / "experiments/results"; OUT = R / "table1_ch_paired_v1"; SEED, B = 20261004, 10000
SC = ["High BW", "Low BW", "Fluctuating"]


def main():
    z = np.load(S.NPZ, allow_pickle=True); off = z["offsets"]; TR = z["truth_mbps"].astype(np.float64); keys = [str(k) for k in z["keys"]]; dirs = [str(d) for d in z["dirs"]]
    scen = [S.SCEN[d] for d in dirs]; n = len(keys)
    clean = set(json.load(open(R / "_deleak.json"))["main_validation"]["leakage_free_file_names"])
    P = {a: z[f"pred__{a}"].astype(np.float64) for a in S.MAIN}
    for name, p in (("LLM4band++ (Qwen)", "llm4bandpp_perstep_dump_v1/perstep_llm4bandpp.npz"), ("LLM4Band conference version online weights (Qwen)", "llm4band_conf_perstep_dump_v1/perstep_llm4band_conf.npz")):
        c = np.load(R / p, allow_pickle=True); assert [str(k) for k in c["keys"]] == keys; P[name] = c["pred"].astype(np.float64)
    def per_call(pred):
        return np.array([np.nanmean((pred[off[i]:off[i + 1]] - TR[off[i]:off[i + 1]]) ** 2) for i in range(n)])
    M = {k: dict(zip(keys, per_call(v))) for k, v in P.items()}
    sc_of = dict(zip(keys, scen))
    nl = {}
    for t in ("CHs0", "CHs1", "CHs2"):
        for x in json.load(open(R / f"nl_2x2_v1/eval/{t}.json"))["files"]: nl.setdefault(t, {})[x["file"]] = float(x["mse"])
    def norm(k):
        parts = k.replace("\\", "/").split("/"); return "/".join(parts[-2:])
    # Match the file names of both sources on their last two path parts (directory/file).
    kmap = {norm(k): k for k in keys}
    for t in nl: nl[t] = {kmap[norm(f)]: v for f, v in nl[t].items()}
    assert all(len(nl[t]) == n for t in nl), {t: len(nl[t]) for t in nl}
    for t in nl: M[t] = nl[t]
    def macro(d, sub=None):
        return float(np.mean([np.mean([d[k] for k in keys if sc_of[k] == s and (sub is None or k.split("/")[-1] in clean)]) for s in SC]))
    ref = json.load(open(R / "main_table_unified_v1/result.json"))["rows"]
    for a in ("Pioneer", "Schaferct(retrained)", "LLM4band++ (Qwen)"):
        assert abs(macro(M[a]) - ref[a]["870"]["macro_mse"]) < 1e-9, (a, macro(M[a]), ref[a]["870"]["macro_mse"])
    assert 5.795301 <= macro(M["CHs1"]) <= 5.795341, macro(M["CHs1"])
    def boot(cand, base, sub):
        """Paired bootstrap of (base - cand)/base x 100 in macro MSE, resampling calls within each scenario B times; returns the point estimate and 95% interval."""
        rng = np.random.default_rng(SEED); mb = np.zeros(B); mc = np.zeros(B); pb = []; pc = []
        for s in SC:
            ks = [k for k in keys if sc_of[k] == s and (sub is None or k.split("/")[-1] in clean)]
            vb = np.array([M[base][k] for k in ks]); vc = np.array([M[cand][k] for k in ks]); idx = rng.integers(0, len(ks), size=(B, len(ks)))
            mb += vb[idx].mean(axis=1) / len(SC); mc += vc[idx].mean(axis=1) / len(SC); pb.append(vb.mean()); pc.append(vc.mean())
        pt = (np.mean(pb) - np.mean(pc)) / np.mean(pb) * 100; bs = np.sort((mb - mc) / mb * 100)
        return {"rel_improvement_pct": float(pt), "ci95": [float(bs[int(0.025 * (B - 1))]), float(bs[int(0.975 * (B - 1))])]}
    res = {"deployed": "CHs1", "rows": {}, "paired": {}}
    for t in ("CHs0", "CHs1", "CHs2"):
        res["rows"][t] = {sn: {**{s: float(np.mean([M[t][k] for k in keys if sc_of[k] == s and (sub is None or k.split("/")[-1] in clean)])) for s in SC}, "macro_mse": macro(M[t], sub)} for sn, sub in (("870", None), ("712", "clean"))}
    for base in ("Pioneer", "Schaferct(retrained)", "LLM4Band conference version online weights (Qwen)", "LLM4band++ (Qwen)"):
        res["paired"][base] = {sn: boot("CHs1", base, sub) for sn, sub in (("870", None), ("712", "clean"))}
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    for b, v in res["paired"].items(): print(b, {sn: (round(x["rel_improvement_pct"], 2), [round(c, 2) for c in x["ci95"]]) for sn, x in v.items()})
    print({t: {sn: round(v[sn]["macro_mse"], 3) for sn in v} for t, v in res["rows"].items()})


if __name__ == "__main__":
    main()
