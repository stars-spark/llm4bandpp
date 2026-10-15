#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Correlation of the two HCQ reward terms on the training tuples (registered experiment hcq-term-correlation-v1).
Reads the original training pickle (actions, true capacities, rewards), recovers the quality term q from r = 0.6 q - 0.4 e with e = |a - B| / B, and aborts if that identity fails on any row.
Reports Pearson and Spearman correlation between -e (uncapped and capped at 5) and q, overall, per 1 Mbit/s capacity bin and for over- and under-estimates.
Usage: python hcq_term_corr_v1.py OUT.json
"""
import json, pickle, sys, time
import numpy as np

PKL = "/path/to/challenge/solution/dataset/training_dataset_pickle/MRE/MRE_4.pickle"
LAM, CAP = 0.4, 5.0
BINS = [(i, i + 1) for i in range(7)] + [(7, None)]


def ranks(x):
    """Return average ranks, with tied values sharing their mean rank."""
    o = np.argsort(x, kind="mergesort"); xs = x[o]; r = np.empty(len(x), dtype=np.float64)
    i = 0; n = len(x)
    starts = np.flatnonzero(np.r_[True, xs[1:] != xs[:-1]]); ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends): r[o[s:e]] = (s + e - 1) / 2.0 + 1.0
    return r


def corr(a, b):
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0: return {"n": int(len(a)), "pearson": None, "spearman": None}
    return {"n": int(len(a)), "pearson": float(np.corrcoef(a, b)[0, 1]), "spearman": float(np.corrcoef(ranks(a), ranks(b))[0, 1])}


def main(out):
    t = time.time(); d = pickle.load(open(PKL, "rb"))
    a = d["actions"].reshape(-1).astype(np.float64); B = d["true_capacitys"].reshape(-1).astype(np.float64); r = d["rewards"].reshape(-1).astype(np.float64)
    ok = np.isfinite(a) & np.isfinite(B) & np.isfinite(r) & (B > 0)
    a, B, r = a[ok], B[ok], r[ok]
    # Invert r = (1 - LAM) q - LAM e to recover the quality term q.
    e = np.abs(a - B) / (B + 1e-6); q = (r + LAM * e) / (1 - LAM)
    recon = float(np.max(np.abs((1 - LAM) * q - LAM * e - r)))
    if not recon < 1e-9: raise SystemExit(f"void: r = 0.6·r_q − 0.4·e does not hold line by line, maximum error {recon}")
    E, Ec = -e, -np.minimum(e, CAP); Bm = B / 1e6
    res = {"pickle": PKL, "rows_total": int(len(ok)), "rows_valid": int(ok.sum()), "recon_max_abs_err": recon,
           "q_range": [float(q.min()), float(q.max())], "e_median": float(np.median(e)), "e_p99": float(np.quantile(e, 0.99)),
           "overall": {"uncapped": corr(E, q), "capped5": corr(Ec, q)}, "by_bin": {}, "by_side": {}}
    for lo, hi in BINS:
        m = (Bm >= lo) & ((Bm < hi) if hi is not None else True); k = f"{lo}-{hi}" if hi is not None else f">{lo}"
        res["by_bin"][k] = {"uncapped": corr(E[m], q[m]), "capped5": corr(Ec[m], q[m])}
    for k, m in (("over", a > B), ("under", a < B)):
        res["by_side"][k] = {"uncapped": corr(E[m], q[m]), "capped5": corr(Ec[m], q[m])}
    res["seconds"] = round(time.time() - t, 1)
    open(out, "w").write(json.dumps(res, ensure_ascii=False, indent=1)); print(json.dumps(res["overall"], ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
