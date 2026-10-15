#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the frozen prompts for zero-shot LLM expert selection from the C0 feature table zs_input_v1.npz (X_C0, names, meta).
primary: task text plus definitions of the 25 statistics, with no selection strategy. neutral: knowledge ablation, same task, statistics renamed x1 to x25, no definitions.
Experts are called A to E in table column order (Pioneer, the challenge baseline, Schaferct-R, MLP, the one-token LLM variant).
build writes prompts_primary.jsonl, prompts_neutral.jsonl and MANIFEST.json with hashes; extract cuts zs_input_v1.npz from shift_table_v1.npz.
Usage: python switch_llm_zeroshot_prompts_v1.py extract | build IN.npz OUTDIR
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
L = "ABCDE"
TASK = ("You are the selector in a receiver-side bandwidth estimation system for real-time video. Five bandwidth estimators, called experts A, B, C, D and E, run in parallel. "
        "Every 3 seconds you choose which expert's estimate the system will use for the next 3 seconds. Choose the expert whose estimate will be closest to the true available "
        "bandwidth of the network path over the next 3 seconds; the error is measured as the squared difference in Mbit/s. You only see statistics of the last 3 seconds, "
        "computed over 50 steps of 60 ms each.")
DEFS = ("Definitions of the statistics:\n"
        "- recv_rate_mean: mean receiving rate in Mbit/s. recv_rate_cv: its standard deviation divided by its mean. recv_rate_trend: mean of the second half of the steps divided by mean of the first half.\n"
        "- qdelay_mean and qdelay_p95: mean and 95th percentile of the queuing delay in ms, where queuing delay is the mean one-way delay minus the minimum one-way delay observed so far. qdelay_slope: its change per step in ms.\n"
        "- delay_ratio_mean: mean one-way delay divided by the minimum one-way delay within each step.\n"
        "- jitter_mean: packet inter-arrival jitter in ms.\n"
        "- loss_mean: packet loss ratio.\n"
        "- For each expert X: X_ratio is its mean estimate divided by recv_rate_mean; X_dev is the mean relative deviation of its estimate from the receiving rate, "
        "where estimates above the receiving rate count three times as much as estimates below it; X_slope is the change of its estimate per step in Mbit/s.\n"
        "- disagree: mean over steps of the standard deviation of the five estimates divided by their mean.")
NAMES = ["recv_rate_mean", "recv_rate_cv", "recv_rate_trend", "qdelay_mean", "qdelay_p95", "qdelay_slope", "delay_ratio_mean", "jitter_mean", "loss_mean"] + \
        [f"{x}_{k}" for x in L for k in ("ratio", "dev", "slope")] + ["disagree"]
SRC = ["f0_mean", "f0_cv", "f0_trend", "f3_mean", "f3_p95", "f3_slope", "f6_mean", "f9_mean", "f10_mean"] + \
      [f"{a}_{k}" for a in ["Pioneer", "Schaferct_public", "Schaferct_retrained", "MLP_seed0", "LLM4bandpp"] for k in ("ratio", "pseudo", "slope")] + ["disagree"]
ANS = "Answer with a single letter: A, B, C, D or E."
NEUTRAL = ("Each 3-second block is described by 25 numbers x1 to x25. The numbers x10 to x24 come in groups of three that belong to experts A, B, C, D and E in that order; "
           "the other numbers describe the block as a whole.")


def fmt(v): return "nan" if not np.isfinite(v) else f"{v:.3g}"


def prompt(row, variant):
    if variant == "primary":
        vals = " ".join(f"{n}={fmt(v)}" for n, v in zip(NAMES, row)); return f"{TASK}\n\n{DEFS}\n\nStatistics of the last 3 seconds:\n{vals}\n\n{ANS}"
    vals = " ".join(f"x{i + 1}={fmt(v)}" for i, v in enumerate(row)); return f"{TASK}\n\n{NEUTRAL}\n\nNumbers for the last 3 seconds:\n{vals}\n\n{ANS}"


def build(inp, outdir):
    z = np.load(inp, allow_pickle=True); names = [str(x) for x in z["names"]]; X = z["X_C0"]; assert names == SRC, "Feature column order differs from expected"
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True); man = {}
    for v in ("primary", "neutral"):
        h = hashlib.sha256()
        with open(out / f"prompts_{v}.jsonl", "w") as f:
            for r in range(len(X)):
                p = prompt(X[r], v); h.update(p.encode()); f.write(json.dumps({"row": r, "prompt": p}) + "\n")
        man[v] = {"n": len(X), "sha256": h.hexdigest()}
    (out / "MANIFEST.json").write_text(json.dumps(man, indent=1)); print(json.dumps(man))


def extract():
    root = Path(__file__).resolve().parents[2]; z = np.load(root / "experiments/results/switch_llm_shift_v1/shift_table_v1.npz", allow_pickle=True)
    out = root / "experiments/results/switch_llm_zeroshot_v1"; out.mkdir(parents=True, exist_ok=True)
    np.savez(out / "zs_input_v1.npz", X_C0=z["X_C0"], names=z["names"], meta=z["meta"]); print("wrote", out / "zs_input_v1.npz")


if __name__ == "__main__":
    if sys.argv[1] == "extract": extract()
    else: build(sys.argv[2], sys.argv[3])
