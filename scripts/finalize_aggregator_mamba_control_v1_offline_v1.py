#!/usr/bin/env python3
"""Offline recomputation of aggregator-mamba-control-v1 from the per-call evaluation files, with no server access.

The registered judge (finalize_aggregator_mamba_control_v1.py) fetched the evaluation files from the GPU server and then
read them with the rule below. This script applies the same rule to the local copies:
  per arm, the per-call metrics (MSE and overestimation e+) are averaged over the three seeds;
  difference = Mamba minus Transformer (negative: Mamba lower), per scenario and for the macro mean of the three scenarios;
  95% interval: 10000 paired bootstrap draws of the calls within each scenario, generator seed 20260909, with one set of
  draws per scenario shared by all metrics; the macro draw is the mean of the three scenario draws;
  noise threshold: twice the standard deviation of the reference arm's three seed values;
  reading: better if the interval lies below 0 and |difference| >= threshold, worse if it lies above 0 and
  |difference| >= threshold, tie if the interval lies within +/- threshold, otherwise indistinguishable.
The verdict follows the macro MSE reading: tie or worse holds (the Transformer aggregator is kept), better does not hold,
indistinguishable is inconclusive. The reference arm without the LLM (Transformer aggregator) is the NL arm of
llm-indispensability-mt-anchor-3seed; its files are byte-identical to the copies the judge fetched.

Usage: python3 scripts/finalize_aggregator_mamba_control_v1_offline_v1.py
Prints the readings and compares them with experiments/results/aggregator_mamba_control_v1/result_main.json.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments/results/aggregator_mamba_control_v1"
NL = ROOT / "experiments/results/llm_indispensability/paper_data/raw"
MET = ["mse", "over", "under", "err"]
ORDER = ["High BW", "Low BW", "Fluctuating"]
SEED, NBOOT = 20260909, 10000


def load(files):
    """Stack the per-call metrics of several runs, calls sorted by name; all runs must list the same calls."""
    arrs, scen = [], None
    for p in files:
        f = sorted(json.loads(Path(p).read_text(encoding="utf-8"))["files"], key=lambda r: r["file"])
        arrs.append(np.array([[r[k] for k in MET] for r in f], dtype=np.float64))
        s = np.array([r["scenario"] for r in f])
        assert scen is None or np.array_equal(scen, s)
        scen = s
    return np.stack(arrs), scen


def read(A, B, scen, multi):
    """Readings of arm A (Mamba) against arm B (Transformer), same computation as the registered judge."""
    a, b = A.mean(0), B.mean(0)
    rng = np.random.default_rng(SEED)
    BI = {s: rng.integers(0, (scen == s).sum(), size=(NBOOT, (scen == s).sum())) for s in ORDER}
    out = {}
    for s in ORDER + ["macro"]:
        out[s] = {}
        for j, k in enumerate(MET[:2]):
            if s == "macro":
                va = np.mean([a[scen == t][:, j].mean() for t in ORDER])
                vb = np.mean([b[scen == t][:, j].mean() for t in ORDER])
                bs = np.mean([a[scen == t][:, j][BI[t]].mean(1) - b[scen == t][:, j][BI[t]].mean(1) for t in ORDER], axis=0)
                sd = np.std([np.mean([B[i][scen == t][:, j].mean() for t in ORDER]) for i in range(len(B))], ddof=1) if multi else None
            else:
                m = scen == s
                va, vb = a[m][:, j].mean(), b[m][:, j].mean()
                bs = a[m][:, j][BI[s]].mean(1) - b[m][:, j][BI[s]].mean(1)
                sd = np.std([B[i][m][:, j].mean() for i in range(len(B))], ddof=1) if multi else None
            dl = 2 * sd if multi else 0.0382 * abs(vb)
            d = va - vb
            lo, hi = np.percentile(bs, [2.5, 97.5])
            rd = "better" if hi < 0 and abs(d) >= dl else ("worse" if lo > 0 and abs(d) >= dl else ("tie" if lo >= -dl and hi <= dl else "indistinguishable"))
            out[s][k] = {"mamba": float(va), "transformer": float(vb), "diff": float(d), "rel_pct": float(d / vb * 100),
                         "ci95": [float(lo), float(hi)], "delta": float(dl), "reading": rd}
    return out


def main():
    A, scen = load([RES / f"MBs{s}_50000.json" for s in (0, 1, 2)])
    B, scen2 = load([NL / f"NLs{s}_50000.json" for s in (0, 1, 2)])
    assert np.array_equal(scen, scen2) and len(scen) == 870
    main_r = read(A, B, scen, True)
    rd = main_r["macro"]["mse"]["reading"]
    verdict = "holds" if rd in ("tie", "worse") else ("does not hold" if rd == "better" else "inconclusive")
    x = main_r["macro"]["mse"]
    print(f"macro MSE: Mamba {x['mamba']:.3f} vs Transformer {x['transformer']:.3f} ({x['rel_pct']:+.1f}%), "
          f"difference {x['diff']:+.3f}, 95% interval [{x['ci95'][0]:.3f}, {x['ci95'][1]:.3f}], threshold {x['delta']:.3f}, "
          f"{x['reading']}; verdict {verdict}")
    e = main_r["macro"]["over"]
    print(f"macro e+: Mamba {e['mamba']:.3f} vs Transformer {e['transformer']:.3f}, {e['reading']}")
    for s in ORDER:
        y = main_r[s]["mse"]
        print(f"  {s} MSE: Mamba {y['mamba']:.3f} vs Transformer {y['transformer']:.3f} ({y['rel_pct']:+.2f}%), {y['reading']}")
    rec = RES / "result_main.json"
    if not rec.exists():
        print("no recorded result_main.json to compare with")
        return 0
    want = json.loads(rec.read_text(encoding="utf-8"))["readings"]
    bad = []
    for s in want:
        for k in want[s]:
            for f in ("mamba", "transformer", "diff", "rel_pct", "delta"):
                if abs(want[s][k][f] - main_r[s][k][f]) > 1e-9 * max(1.0, abs(want[s][k][f])):
                    bad.append(f"{s}/{k}/{f}")
            if any(abs(p - q) > 1e-12 for p, q in zip(want[s][k]["ci95"], main_r[s][k]["ci95"])):
                bad.append(f"{s}/{k}/ci95")
    print("matches the recorded result_main.json" if not bad else "differs from result_main.json: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
