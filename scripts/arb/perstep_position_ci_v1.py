#!/usr/bin/env python3
"""Recompute the three per-step position contrasts (Table II and the supplement) from the per-call evaluation files.

Each arm was trained with seeds 0, 1 and 2 and evaluated on the 870 validation calls. Macro MSE of one run is the mean
of the three scenario means (High BW, Low BW, Fluctuating) of the per-call MSE. For a candidate arm C and a reference
arm R we compute, as the registered judges did:
  improvement = 100 * (mean_R - mean_C) / mean_R, with mean_X the mean of the three seed macro MSEs;
  per-seed improvements 100 * (R_s - C_s) / R_s; their standard deviation around the improvement (n - 1 = 2);
  a 95% t interval over seeds, improvement +/- 4.302653 * sd / sqrt(3).
The paper reports the change in error, the negated improvement, so a positive value means the LLM arm is worse.

Arms: LLM (pre-trained Qwen1.5-0.5B with LoRA), NL (same network without the LLM), RI (randomly initialized network
of the LLM's architecture, trained in full), PF (pre-trained network trained in full).
The script checks each result against the numeric registry events and against the strings printed in the paper.

Usage: python3 scripts/arb/perstep_position_ci_v1.py
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "experiments/results"
ORDER = ("High BW", "Low BW", "Fluctuating")
SEEDS = (0, 1, 2)
T975_DF2 = 4.302653   # 0.975 quantile of the t distribution with 2 degrees of freedom, as in the registered judges
ARMS = {
    "LLM": RES / "llm_indispensability/paper_data/raw/LLMs{s}_50000.json",
    "NL": RES / "llm_indispensability/paper_data/raw/NLs{s}_50000.json",
    "RI": RES / "pretrained_fulltrain_fourth_arm/raw/RIs{s}_50000.json",
    "PF": RES / "pretrained_fulltrain_fourth_arm/raw/PFs{s}_50000.json",
}
# (label, candidate, reference, registry id, value printed in the paper)
CONTRASTS = [
    ("pre-trained vs random init., both trained in full (Table II)", "PF", "RI",
     "llm-pretraining-fulltrain-fourth-arm-3seed", "+2.2% [-4.0, +8.4]"),
    ("pre-trained with LoRA vs no LLM", "LLM", "NL",
     "llm-indispensability-mt-anchor-3seed", "+0.1% [-4.8, +5.0]"),
    ("pre-trained with LoRA vs random init. trained in full", "LLM", "RI",
     "llm-pretraining-value-randinit-fair-3seed", "+2.7% [-0.2, +5.5]"),
]


def macro_mse(path):
    """Macro MSE of one evaluation file, recomputed from its per-call rows; also checks the stored value."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = d["files"]
    assert len(rows) == 870, (path, len(rows))
    means = []
    for s in ORDER:
        v = [r["mse"] for r in rows if r["scenario"] == s]
        means.append(sum(v) / len(v))
    m = sum(means) / len(means)
    assert abs(m - d["macro_mse"]) <= 1e-9 * abs(m), (path, m, d["macro_mse"])
    return m


def contrast(cand, ref):
    c = {s: macro_mse(str(ARMS[cand]).format(s=s)) for s in SEEDS}
    r = {s: macro_mse(str(ARMS[ref]).format(s=s)) for s in SEEDS}
    per_seed = {s: 100.0 * (r[s] - c[s]) / r[s] for s in SEEDS}
    mean_c, mean_r = sum(c.values()) / 3.0, sum(r.values()) / 3.0
    imp = 100.0 * (mean_r - mean_c) / mean_r
    sd = math.sqrt(sum((v - imp) ** 2 for v in per_seed.values()) / 2.0)
    se = sd / math.sqrt(3.0)
    return {"mean_macro_candidate": mean_c, "mean_macro_reference": mean_r, "per_seed_improvement_pct": per_seed,
            "mean_improvement_pct": imp, "seed_mean_ci95": [imp - T975_DF2 * se, imp + T975_DF2 * se]}


def registry_metrics(exp_id):
    """The last numeric data event of one experiment in experiments/registry.jsonl."""
    last = None
    for line in (ROOT / "experiments/registry.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("id") == exp_id and e.get("event") == "data" and e.get("metrics"):
            last = e["metrics"]
    return last


def main():
    bad = 0
    for label, cand, ref, exp_id, paper in CONTRASTS:
        m = contrast(cand, ref)
        lo, hi = m["seed_mean_ci95"]
        d = -m["mean_improvement_pct"]
        text = f"{d:+.1f}% [{-hi:+.1f}, {-lo:+.1f}]"
        reg = registry_metrics(exp_id)
        same_reg = reg is not None and abs(reg["mean_improvement_pct"] - m["mean_improvement_pct"]) < 1e-9 \
            and all(abs(a - b) < 1e-9 for a, b in zip(reg["seed_mean_ci95"], m["seed_mean_ci95"]))
        ok = text == paper and same_reg
        bad += not ok
        print(f"{label}: {cand} {m['mean_macro_candidate']:.4f} vs {ref} {m['mean_macro_reference']:.4f}; "
              f"change in macro MSE {text}; paper {paper}; registry {'matches' if same_reg else 'differs'}"
              f"{'' if ok else '  <-- MISMATCH'}")
    print("all three intervals reproduced" if not bad else f"{bad} mismatches")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
