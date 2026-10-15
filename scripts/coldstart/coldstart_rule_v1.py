#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared parts of LLM rule induction for expert selection: prompt text, evidence formatting, the model call and a sandbox for the returned rule.
The model writes a short Python function choose(s) that picks one of five bandwidth experts (A to E) for each 3-second block from block statistics.
Evidence comes from earlier deployments (evidence_source) and from the first calls of a new deployment, with ground-truth errors (evidence_compact) or without (evidence_unlabeled).
The tables X (block statistics), Rc (per-expert block errors) and FILE (call id per block) are arguments. Used by registered experiment switch-llm-coldstart-v3.
ask() sends one request to deepseek-flash at temperature 0; the designer and schema-matching scripts reuse it.
"""
import json, math, re, sys, time, urllib.request
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart")); sys.path.insert(0, str(ROOT / "scripts/arb"))
import api_runner_v1 as AR  # noqa: E402
import switch_llm_zeroshot_prompts_v1 as ZP  # noqa: E402
L = "ABCDE"
TASK = ("You will design the expert selector for a new deployment of a receiver-side bandwidth estimation system for real-time video. Five bandwidth estimators, experts A to E, "
        "run in parallel. Every 3 seconds the selector picks one expert, whose estimate is used for the next 3 seconds; the goal is the smallest squared error between the used "
        "estimate and the true available bandwidth (Mbit/s), summed over whole calls. The selector only sees statistics of the last 3 seconds.")
ASK_SIMPLE = ("Write a short Python function `choose(s)` where `s` is a dict mapping each statistic name to its value for the current block; it must return one of 'A', 'B', 'C', 'D', 'E'. "
              "Use at most four if-conditions. Base it on the evidence above and on what the statistics mean, so that it works on future calls of this deployment. "
              "Squared errors summed over calls are dominated by blocks where an expert is far off, so prefer choices that are never very wrong. "
              "Keep your reasoning brief. Use only arithmetic, comparisons, abs, min, max and the math module; no imports. Reply with the function in a single ```python code block.")


def evidence_compact(X, Rc, FILE, acc_files, per_call=8):
    lines_sum, lines_ex = [], []
    allrows = np.where(np.isin(FILE, acc_files))[0]; eps = 1e-9 + 1e-6 * Rc[allrows].min(1).mean()
    for k, f in enumerate(acc_files, 1):
        rows = np.where(FILE == f)[0]; best = Rc[rows].min(1); wins = np.bincount(Rc[rows].argmin(1), minlength=5); tot = (Rc[rows].sum(0) + eps) / (best.sum() + eps)
        lines_sum.append(f"call {k} ({len(rows)} blocks): most accurate count " + " ".join(f"{L[j]}={wins[j]}" for j in range(5)) + "; total error relative to best " + " ".join(f"{L[j]}={tot[j]:.3g}" for j in range(5)))
        for r in rows[np.unique(np.linspace(0, len(rows) - 1, per_call).round().astype(int))]:
            rel = (Rc[r] + eps) / (Rc[r].min() + eps)
            lines_ex.append(f"call {k}: " + " ".join(f"{n}={ZP.fmt(v)}" for n, v in zip(ZP.NAMES, X[r])) + " | error relative to best: " + " ".join(f"{L[j]}={rel[j]:.3g}" for j in range(5)) + f" | best: {L[int(Rc[r].argmin())]}")
    return (f"Evidence from the first {len(acc_files)} calls of this new deployment (true bandwidth measured afterwards).\nPer-call summary (an expert's error in a block is its squared error over the next 3 seconds; "
            "relative to best = divided by the error of the most accurate expert in that block):\n" + "\n".join(lines_sum) +
            f"\n\nExample blocks ({per_call} per call, evenly spaced): the statistics of the block, each expert's error relative to the best over the next 3 seconds, and the most accurate expert.\n" + "\n".join(lines_ex))


def prompt(X, Rc, FILE, acc_files):
    return TASK + "\n\n" + ZP.DEFS + "\n\n" + evidence_compact(X, Rc, FILE, acc_files) + "\n\n" + ASK_SIMPLE


def ask(text, max_tokens=64000):
    body = {"model": "deepseek-flash", "messages": [{"role": "user", "content": text}], "temperature": 0, "max_tokens": max_tokens}
    for k in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(body).encode(),
                             headers={"Authorization": f"Bearer {AR.KEY.read_text().strip()}", "Content-Type": "application/json"}), timeout=1800))
        except Exception as e:
            err = e; time.sleep(15 * (k + 1))
    raise err


def run_rule(text, Xrows, default):
    """Run the model's choose() on each block in a restricted namespace; return (choices, code, bad block count, error), with the default expert everywhere if the code fails to compile."""
    m = re.findall(r"```python\s*(.*?)```", text, re.S); code = m[-1] if m else text
    ns = {"__builtins__": {"abs": abs, "min": min, "max": max, "float": float, "int": int, "len": len, "range": range, "sum": sum, "round": round, "sorted": sorted, "any": any, "all": all}, "math": math}
    out = np.full(len(Xrows), default); bad = 0
    try:
        exec(compile(code, "<rule>", "exec"), ns); f = ns["choose"]
    except Exception as e:
        return out, code, len(Xrows), repr(e)[:200]
    for k, x in enumerate(Xrows):
        try:
            v = f({n: float(a) for n, a in zip(ZP.NAMES, x)}); out[k] = L.index(v) if v in L else default; bad += v not in L
        except Exception: bad += 1
    return out, code, bad, None


ASK_ADAPT = ("Write a short Python function `choose(s)` where `s` is a dict mapping each statistic name to its value for the current block; it must return one of 'A', 'B', 'C', 'D', 'E'. "
             "The function may return a fixed expert, or compute the choice from the current block's statistics, for example the expert with the smallest X_dev, or the expert whose X_ratio is closest to 1, "
             "or combine the two with conditions. Use at most four if-conditions. "
             "Base it on the evidence above and on what the statistics mean, so that it works on future calls of this deployment, which may contain situations not seen in these first calls. "
             "Squared errors summed over calls are dominated by rare blocks where an expert is far off, so prefer choices that are never very wrong. "
             "Keep your reasoning brief. Use only arithmetic, comparisons, abs, min, max and the math module; no imports. Reply with the function in a single ```python code block.")


def evidence_source(X, Rc, FILE, dirs_of_file, src_rows, per_expert=6):
    """Format the earlier-deployment evidence: per-scenario win shares and total relative error of each expert, plus the blocks where each expert erred most."""
    eps = 1e-9 + 1e-6 * Rc[src_rows].min(1).mean(); lines = []; D = np.asarray(dirs_of_file)
    for sc in sorted(set(D[FILE[src_rows]])):
        rows = src_rows[D[FILE[src_rows]] == sc]; best = Rc[rows].min(1); wins = np.bincount(Rc[rows].argmin(1), minlength=5); tot = (Rc[rows].sum(0) + eps) / (best.sum() + eps)
        lines.append(f"earlier deployment {len(lines) + 1} ({len(set(FILE[rows]))} calls, {len(rows)} blocks): most accurate share " + " ".join(f"{L[j]}={100 * wins[j] / len(rows):.0f}%" for j in range(5)) +
                     "; total error relative to best " + " ".join(f"{L[j]}={tot[j]:.3g}" for j in range(5)))
    rel = (Rc[src_rows] + eps) / (Rc[src_rows].min(1, keepdims=True) + eps); ex = []
    for j in range(5):
        for r in src_rows[np.argsort(-rel[:, j] * Rc[src_rows, j])[:per_expert]]:
            rr = (Rc[r] + eps) / (Rc[r].min() + eps)
            ex.append(f"expert {L[j]} very wrong: " + " ".join(f"{n}={ZP.fmt(v)}" for n, v in zip(ZP.NAMES, X[r])) + " | error relative to best: " + " ".join(f"{L[k]}={rr[k]:.3g}" for k in range(5)) + f" | best: {L[int(Rc[r].argmin())]}")
    return ("Experience from earlier deployments on other networks (the same five experts; this is the data the lightweight selector was trained on):\n" + "\n".join(lines) +
            f"\nFor each expert, the {per_expert} blocks of the earlier deployments where it contributed the largest error (statistics, each expert's error relative to the best, most accurate expert):\n" + "\n".join(ex))


def prompt_v4(Xn, Rcn, Fn, acc_files, source):
    """Build the frozen selector prompt: task, statistic definitions, earlier-deployment evidence, labeled evidence from the new deployment's first calls and the rule request."""
    return TASK + "\n\n" + ZP.DEFS + "\n\n" + evidence_source(*source) + "\n\n" + evidence_compact(Xn, Rcn, Fn, acc_files) + "\n\n" + ASK_ADAPT


# Unlabeled cold start: the new deployment contributes receiver statistics only, no ground truth.
ASK_UNLAB = ("Write a short Python function `choose(s)` where `s` is a dict mapping each statistic name to its value for the current block; it must return one of 'A', 'B', 'C', 'D', 'E'. "
             "In this new deployment the true bandwidth is not known, so no expert's error can be measured here: infer which expert to trust from the experience of the earlier deployments "
             "and from what the statistics of this deployment reveal about the network and about how each expert behaves in it. "
             "The function may return a fixed expert, or compute the choice from the current block's statistics, or combine the two with conditions. Use at most four if-conditions. "
             "Squared errors summed over calls are dominated by rare blocks where an expert is far off, so prefer choices that are never very wrong. "
             "Keep your reasoning brief. Use only arithmetic, comparisons, abs, min, max and the math module; no imports. Reply with the function in a single ```python code block.")


def evidence_unlabeled(X, FILE, acc_files, per_call=8):
    """Format the new deployment's first calls as receiver statistics only (percentiles and sample blocks), with no ground truth, errors or best expert."""
    nm = ZP.NAMES; idx = {n: i for i, n in enumerate(nm)}; lines_sum, lines_ex = [], []
    q = lambda v: f"{ZP.fmt(np.percentile(v, 25))}/{ZP.fmt(np.median(v))}/{ZP.fmt(np.percentile(v, 75))}"
    for k, f in enumerate(acc_files, 1):
        rows = np.where(FILE == f)[0]; R = X[rows]
        parts = [f"{n} {q(R[:, idx[n]])}" for n in ("recv_rate_mean", "qdelay_mean", "loss_mean", "delay_ratio_mean", "disagree")]
        parts += [f"{L[j]}_ratio {q(R[:, idx[L[j] + '_ratio']])}, {L[j]}_dev {q(R[:, idx[L[j] + '_dev']])}" for j in range(5)]
        lines_sum.append(f"call {k} ({len(rows)} blocks; 25th/50th/75th percentiles): " + "; ".join(parts))
        for r in rows[np.unique(np.linspace(0, len(rows) - 1, per_call).round().astype(int))]:
            lines_ex.append(f"call {k}: " + " ".join(f"{n}={ZP.fmt(v)}" for n, v in zip(nm, X[r])))
    return (f"Observations from the first {len(acc_files)} calls of this new deployment. The true bandwidth of these calls is NOT known; these are only what the receiver measures.\n"
            "Per-call summary:\n" + "\n".join(lines_sum) + f"\n\nExample blocks ({per_call} per call, evenly spaced):\n" + "\n".join(lines_ex))


def prompt_unlab(Xn, Fn, acc_files, source):
    return TASK + "\n\n" + ZP.DEFS + "\n\n" + evidence_source(*source) + "\n\n" + evidence_unlabeled(Xn, Fn, acc_files) + "\n\n" + ASK_UNLAB
