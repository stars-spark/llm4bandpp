#!/usr/bin/env python3
"""Offline recomputation of ablation-enc-hcq-2x2-v1 and ablation-hcq-lowbw-v1 (the encoder by reward ablation repeated
on the fifteen-token LLM variant with LoRA and the capacity anchor, supplement) from the released per-call metrics,
with no server access.

The registered judge (finalize_enc_hcq_2x2_v1.py) fetched one per-step prediction file per run from the GPU servers,
scored every call with main_table_unified_v1.fm and wrote the scores to per_call_metrics.csv. This script rebuilds the
per-run score matrices from that CSV (columns cell, seed, call, scenario, deleak712, mse, e_plus, e_minus, err; calls in
the order of the reference per-step export) and calls the judge's own judge() function, so the claims, intervals,
safety checks and report-only effects are computed by exactly the registered code. The void checks (code and buffer
hashes, checkpoints, paper-checkpoint recomputation) need the run markers and are not repeated here.

Claim 1: (C-B - M-H) / C-B macro MSE, seeds 0 to 4, 90% interval from 10000 stratified paired bootstrap draws of the
calls (generator seed 20260909). Claim 2: HCQ main effect on Low BW MSE, seeds 0 to 2.

Usage: python3 scripts/finalize_enc_hcq_2x2_v1_offline_v1.py
Prints both claims and the main effects and compares everything with experiments/results/enc_hcq_2x2_v1/result.json.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "experiments/results/enc_hcq_2x2_v1"
ORDER = ["High BW", "Low BW", "Fluctuating"]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import finalize_enc_hcq_2x2_v1 as F  # noqa: E402  (import has no side effects; only judge() is used)


def load_csv(path):
    runs, calls, scen, clean = {}, {}, {}, {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["cell"], int(r["seed"]))
            runs.setdefault(key, []).append([float(r[k]) for k in ("mse", "e_plus", "e_minus", "err")])
            calls.setdefault(key, []).append(r["call"])
            scen.setdefault(key, []).append(r["scenario"])
            clean.setdefault(key, []).append(int(r["deleak712"]))
    ref = next(iter(calls))
    for k in runs:   # every run must list the same calls in the same order
        assert calls[k] == calls[ref] and scen[k] == scen[ref] and clean[k] == clean[ref], k
    M_by_run = {k: np.asarray(v, dtype=np.float64) for k, v in runs.items()}
    return M_by_run, np.asarray(scen[ref]), np.asarray(clean[ref], bool)


def diff(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k not in b: out.append(f"{path}/{k} missing")
            else: diff(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): out.append(f"{path} length")
        for i, (x, y) in enumerate(zip(a, b)): diff(x, y, f"{path}[{i}]", out)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > 1e-9 * max(1.0, abs(a)): out.append(f"{path}: {a} vs {b}")
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")


def main():
    M_by_run, scen, clean = load_csv(LOCAL / "per_call_metrics.csv")
    assert len(scen) == 870 and sorted(M_by_run) == sorted((c, s) for c in F.CELLS for s in F.SEEDS[c]), sorted(M_by_run)
    res = json.loads(json.dumps(F.judge(M_by_run, scen, ORDER, clean), default=str))
    c1, c2, rep = res["claim1"], res["claim2"], res["report_only"]
    print(f"claim 1, macro MSE of M-H against C-B (seeds 0-4): {c1['point_pct']:.2f}% lower, "
          f"90% interval [{c1['ci90'][0]:.2f}, {c1['ci90'][1]:.2f}]; verdict {c1['verdict']}")
    print(f"claim 2, HCQ on Low BW MSE (seeds 0-2): {c2['point_pct']:.2f}% lower, "
          f"90% interval [{c2['ci90'][0]:.2f}, {c2['ci90'][1]:.2f}]; verdict {c2['verdict']}")
    print(f"main effects (report only): reward {rep['reward_main_effect_pct']['point']:.2f}%, "
          f"encoder {rep['encoder_main_effect_pct']['point']:.2f}%")
    want = json.loads((LOCAL / "result.json").read_text(encoding="utf-8"))
    bad = []
    for k in ("claim1", "claim2", "report_only"):
        diff(res[k], want[k], k, bad)
    print("matches the recorded result.json" if not bad else "differs from result.json:\n  " + "\n  ".join(bad[:20]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
