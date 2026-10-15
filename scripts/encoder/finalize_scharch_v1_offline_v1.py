#!/usr/bin/env python3
"""Offline recomputation of schaferct-arch-recipe-v1 (Schaferct's network trained with our recipe) from local files.

The registered judge (finalize_scharch_v1.py) first copied the three evaluation files from the GPU server. This script
reads the local copies and applies the same summary: for each arm, the mean, minimum and maximum over seeds 0 to 2 of
macro MSE (checked to equal the mean of the three scenario MSEs, 870 calls per file) and of each scenario's MSE, e+ and
e-. The arms are the Schaferct network with our recipe (eval/SCHs0-2.json) and C-H, the conference encoder with our
recipe (nl_2x2_v1/eval/CHs0-2.json). Schaferct-R, retrained with its own recipe, is 7.074 (Table I).

Usage: python3 scripts/encoder/finalize_scharch_v1_offline_v1.py
Prints the comparison and checks it against experiments/results/schaferct_arch_recipe_v1/summary.json.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/results/schaferct_arch_recipe_v1"
SC = ("High BW", "Low BW", "Fluctuating")
SEEDS = (0, 1, 2)
SCR = 7.074


def stat(xs):
    return {"mean": sum(xs) / len(xs), "min": min(xs), "max": max(xs)}


def cell(files):
    D = [json.loads(Path(f).read_text(encoding="utf-8")) for f in files]
    for d, f in zip(D, files):
        assert abs(d["macro_mse"] - sum(d["summaries"][s]["mse"] for s in SC) / 3) < 1e-9, f
        assert sum(d["summaries"][s]["n"] for s in SC) == 870, f
    return {"macro": stat([d["macro_mse"] for d in D]),
            **{f"{s}|{k}": stat([d["summaries"][s][k] for d in D]) for s in SC for k in ("mse", "over", "under")}}


def main():
    sch = cell([OUT / "eval" / f"SCHs{s}.json" for s in SEEDS])
    ch = cell([ROOT / f"experiments/results/nl_2x2_v1/eval/CHs{s}.json" for s in SEEDS])
    res = {"SCH_arch_our_recipe": sch, "CH": ch, "Schaferct_R_own_recipe_macro": SCR}
    f = lambda x: f"{x['mean']:.3f} ({x['min']:.3f} to {x['max']:.3f})"
    print(f"three-seed macro MSE: Schaferct network with our recipe {f(sch['macro'])}; C-H {f(ch['macro'])}; "
          f"Schaferct-R (own recipe) {SCR}")
    print(f"mean difference {sch['macro']['mean'] - ch['macro']['mean']:+.3f}, "
          f"{100 * (sch['macro']['mean'] / ch['macro']['mean'] - 1):+.1f}% against C-H, "
          f"{100 * (sch['macro']['mean'] / SCR - 1):+.1f}% against Schaferct-R")
    for s in SC:
        print(f"  {s} MSE {sch[s + '|mse']['mean']:.3f} vs {ch[s + '|mse']['mean']:.3f}; "
              f"e+ {sch[s + '|over']['mean']:.3f} vs {ch[s + '|over']['mean']:.3f}")
    rec = OUT / "summary.json"
    if not rec.exists():
        print("no recorded summary.json to compare with")
        return 0
    want = json.loads(rec.read_text(encoding="utf-8"))
    bad = [f"{arm}/{k}/{q}" for arm in ("SCH_arch_our_recipe", "CH") for k in want[arm] for q in ("mean", "min", "max")
           if abs(want[arm][k][q] - res[arm][k][q]) > 1e-12 * max(1.0, abs(want[arm][k][q]))]
    print("matches the recorded summary.json" if not bad else "differs from summary.json: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
