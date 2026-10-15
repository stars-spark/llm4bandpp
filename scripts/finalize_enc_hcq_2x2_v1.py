#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge of ablation-enc-hcq-2x2-v1 and ablation-hcq-lowbw-v1 (16 shared runs), criteria as pre-registered. Claim 1:
(C-B - M-H) / C-B macro MSE, seeds 0 to 4, per-call seed means, 90% interval from 10000 scenario-stratified paired
bootstrap draws (seed 20260909), threshold 1.631%, safety check D (a worse scenario may raise the macro value by at most
1%). Claim 2: HCQ main effect on Low BW MSE, mean of C-B and M-B against mean of C-H and M-H, seeds 0 to 2, same
bootstrap on the 469 Low BW calls. Holds: lower bound above 0, point estimate >= 1.631%, no safety breach; direction
only: positive but not holding; void on hash, cell, checkpoint, alignment or recomputation failures. Per-call metrics come
from main_table_unified_v1.fm. Usage: --selftest | --check-dump F [--paper F] | --pull | (default) judge [--register].
finalize_enc_hcq_2x2_v1_offline_v1.py calls judge() of this module on the released per_call_metrics.csv.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "experiments/results/enc_hcq_2x2_v1"
EXP1, EXP2 = "ablation-enc-hcq-2x2-v1", "ablation-hcq-lowbw-v1"
CELLS = ("CB", "CH", "MB", "MH")
SEEDS = {"CB": (0, 1, 2, 3, 4), "MH": (0, 1, 2, 3, 4), "CH": (0, 1, 2), "MB": (0, 1, 2)}
BAL = (0, 1, 2)
ENC = {"CB": "conf15", "CH": "conf15", "MB": "ms15", "MH": "ms15"}
LAM = {"CB": "0.0", "CH": "0.4", "MB": "0.0", "MH": "0.4"}
STEP = 50000
THRESH = 1.631
SAFETY_PCT = 1.0
NBOOT, BSEED = 10000, 20260909
PAPER_REF, PAPER_TOL = 6.743, 0.005
ROWS_VALID = 3498556
HOST_OF = {("CB", 0): "gpu-server-1", ("MB", 0): "gpu-server-1", ("MH", 2): "gpu-server-1", ("CH", 2): "gpu-server-1",
           ("MH", 0): "gpu-server-1", ("CH", 0): "gpu-server-1", ("CB", 2): "gpu-server-1", ("MB", 2): "gpu-server-1",
           ("CB", 1): "gpu-server-2", ("MB", 1): "gpu-server-2", ("MH", 3): "gpu-server-2", ("CB", 4): "gpu-server-2",
           ("MH", 1): "gpu-server-2", ("CH", 1): "gpu-server-2", ("CB", 3): "gpu-server-2", ("MH", 4): "gpu-server-2"}
REMOTE_MARK = "/path/to/server/outputs/enc_hcq_2x2_v1/markers"
T90 = {2: 2.919986, 4: 2.131847}


_MT = None


def mt():
    """Import main_table_unified_v1 and take fm and the call order, ground truth and scenario labels of the reference export."""
    global _MT
    if _MT is None:
        res = ROOT / "experiments/results/main_table_unified_v1/result.json"
        before = res.read_bytes() if res.exists() else None
        sys.path.insert(0, str(ROOT / "scripts/arb"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            import main_table_unified_v1 as M
        if before is not None and res.read_bytes() != before:
            res.write_bytes(before)
            print("Note: importing main_table_unified_v1 overwrote its result.json, restored from the pre-import bytes")
        _MT = M
    return _MT


def scen_labels():
    M = mt()
    return np.asarray(M.scen), list(M.S.ORDER), np.asarray(M.clean, bool)


def align_problem(npz_path: Path):
    """Whether an evaluation export is aligned with the reference export: a description of the problem, or None if aligned."""
    M = mt()
    c = np.load(npz_path, allow_pickle=True)
    keys = [str(k) for k in c["keys"]]
    lens = np.asarray(c["lens"])
    n = len(keys)
    if n > len(M.keys):
        return f"Number of calls {n} is more than the baseline's {len(M.keys)}"
    if keys != M.keys[:n]:
        bad = next(i for i in range(n) if keys[i] != M.keys[i])
        return f"keys are inconsistent with the baseline starting from the {bad}th"
    if not np.array_equal(lens, np.diff(M.off)[:n]):
        return "lens is inconsistent with the baseline"
    if len(c["pred"]) != int(lens.sum()):
        return "pred length does not match the sum of lens"
    return None


def score_npz(npz_path: Path) -> np.ndarray:
    M = mt()
    c = np.load(npz_path, allow_pickle=True)
    if len(c["keys"]) != M.n:
        raise SystemExit(f"{npz_path} only {len(c['keys'])} calls, expected {M.n}")
    return M.fm(c["pred"].astype(np.float64))


def scen_means(X, scen, order, mask=None):
    m = np.ones(len(X), bool) if mask is None else mask
    return np.array([X[(scen == s) & m].mean() for s in order])


def macro(X, scen, order, mask=None):
    return float(scen_means(X, scen, order, mask).mean())


def boot_macro_effect(A, B, scen, order, mask=None, rng=None):
    """Stratified paired bootstrap: NBOOT resampled values of (A - B) / A * 100, with A the reference and B the candidate."""
    rng = rng or np.random.default_rng(BSEED)
    m = np.ones(len(A), bool) if mask is None else mask
    sa, sb = np.zeros(NBOOT), np.zeros(NBOOT)
    for s in order:
        idx = np.flatnonzero((scen == s) & m)
        draw = idx[rng.integers(0, len(idx), size=(NBOOT, len(idx)))]
        sa += A[draw].mean(axis=1)
        sb += B[draw].mean(axis=1)
    sa, sb = sa / len(order), sb / len(order)
    return 100.0 * (sa - sb) / sa


def boot_subset_effect(A, B, idx, rng=None):
    rng = rng or np.random.default_rng(BSEED)
    draw = idx[rng.integers(0, len(idx), size=(NBOOT, len(idx)))]
    a, b = A[draw].mean(axis=1), B[draw].mean(axis=1)
    return 100.0 * (a - b) / a


def ci90(v):
    return [float(np.percentile(v, 5)), float(np.percentile(v, 95))]


def safety(ref, cand, scen, order, mask=None):
    """Check D: where a candidate scenario is above the reference, the difference divided by 3 and by the reference macro value."""
    rs, cs = scen_means(ref, scen, order, mask), scen_means(cand, scen, order, mask)
    ref_macro = float(rs.mean())
    rises = {s: (float(c - r) / len(order) / ref_macro * 100.0 if c > r else 0.0)
             for s, r, c in zip(order, rs, cs)}
    worst = max(rises.values())
    return {"scenario_diff_cand_minus_ref": {s: float(c - r) for s, r, c in zip(order, rs, cs)},
            "macro_rise_pct_by_scenario": rises, "worst_macro_rise_pct": worst,
            "breached": worst > SAFETY_PCT}


def verdict(point, lo, breached):
    if breached or point <= 0:
        return "does not hold"
    if lo > 0 and point >= THRESH:
        return "holds"
    return "direction only"


def t90(df):
    try:
        from scipy.stats import t
        return float(t.ppf(0.95, df))
    except Exception:
        return T90[df]


def seed_interval(vals):
    v = np.asarray(vals, float)
    if len(v) < 2:
        return None
    se = v.std(ddof=1) / np.sqrt(len(v))
    q = t90(len(v) - 1)
    return [float(v.mean() - q * se), float(v.mean() + q * se)]


def void_reasons(runs: dict, arm_code: dict, align: dict, paper_macro) -> list:
    """runs[(cell, seed)] is the EVAL marker written by the watcher, or None if missing."""
    why = []
    for cell in CELLS:
        for s in SEEDS[cell]:
            r = runs.get((cell, s))
            if r is None:
                why.append(f"{cell}_s{s} missing evaluation marker")
                continue
            man = r["run_manifest"]
            if int(r["step"]) != STEP or not str(r["checkpoint"]).endswith(f"checkpoint_{STEP}.pt") \
                    or int(man["max_timesteps"]) != STEP:
                why.append(f"{cell}_s{s} missing {STEP}-step checkpoint (step {r['step']}, max_timesteps {man['max_timesteps']})")
            if (man["BWE_ENC"], man["BWE_REWARD_LAMBDA"]) != (ENC[cell], LAM[cell]) or man["cell"] != cell \
                    or int(man["seed"]) != s or r["cell"] != cell or int(r["seed"]) != s:
                why.append(f"{cell}_s{s} environment variable or cell name does not match the registration: {man['BWE_ENC']} {man['BWE_REWARD_LAMBDA']} {man['cell']} seed {man['seed']}")
            if man["code_sha256"] != arm_code or r["code_sha256_now"] != arm_code:
                why.append(f"{cell}_s{s} code hash does not match the generation manifest")
            if int(man["rows_valid"]) != ROWS_VALID:
                why.append(f"{cell}_s{s} valid rows {man['rows_valid']} is not {ROWS_VALID}")
            if align.get((cell, s)):
                why.append(f"{cell}_s{s} evaluation export misaligned: {align[(cell, s)]}")
    present = [r for r in runs.values() if r is not None]
    combos = {(r["run_manifest"]["BWE_ENC"], r["run_manifest"]["BWE_REWARD_LAMBDA"]) for r in present}
    if combos != {(ENC[c], LAM[c]) for c in CELLS}:
        why.append(f"the environment variable combinations are not exactly four: {sorted(combos)}")
    if present:
        for col in ("states", "actions", "next_states", "dones", "capacities"):
            if len({r["run_manifest"]["buffer_sha256"][col] for r in present}) != 1:
                why.append(f"replay buffer {col} columns are inconsistent across runs, which does not match \"the four cells differ only in the reward column\"")
        by_lam = {}
        for r in present:
            by_lam.setdefault(r["run_manifest"]["BWE_REWARD_LAMBDA"], set()).add(
                r["run_manifest"]["buffer_sha256"]["rewards"])
        if any(len(v) != 1 for v in by_lam.values()) or len(set().union(*by_lam.values())) != len(by_lam):
            why.append(f"The reward column hash should be the same for the same λ and different for different λ; obtained { {k: len(v) for k, v in by_lam.items()} }")
        ck = [r["dump"]["ckpt_sha256"] for r in present]
        if len(set(ck)) != len(ck):
            why.append("The same checkpoint hash appears, so the runs are not independent of each other")
    if paper_macro is None:
        why.append("Missing recomputation of the checkpoint of the earlier version")
    elif abs(paper_macro - PAPER_REF) / PAPER_REF > PAPER_TOL:
        why.append(f"Recomputed checkpoint of the earlier version macro {paper_macro:.4f} exceeds {PAPER_REF} by 0.5%")
    return why


def cell_mean(M_by_run, cell, seeds):
    return np.mean([M_by_run[(cell, s)] for s in seeds], axis=0)


def judge(M_by_run: dict, scen, order, clean) -> dict:
    out = {}
    low = order[1]
    assert low == "Low BW", order
    cb, mh = cell_mean(M_by_run, "CB", SEEDS["CB"]), cell_mean(M_by_run, "MH", SEEDS["MH"])
    A, B = cb[:, 0], mh[:, 0]
    pa, pb = macro(A, scen, order), macro(B, scen, order)
    point = 100.0 * (pa - pb) / pa
    lo, hi = ci90(boot_macro_effect(A, B, scen, order))
    sf = safety(A, B, scen, order)
    per_seed = {s: 100.0 * (macro(M_by_run[("CB", s)][:, 0], scen, order) - macro(M_by_run[("MH", s)][:, 0], scen, order))
                / macro(M_by_run[("CB", s)][:, 0], scen, order) for s in SEEDS["CB"]}
    dl = boot_macro_effect(A, B, scen, order, mask=clean)
    pa7, pb7 = macro(A, scen, order, clean), macro(B, scen, order, clean)
    out["claim1"] = {
        "experiment": EXP1, "endpoint": "(C-B - M-H)/C-B x 100, macro MSE, 870 calls, two cells seeds 0 to 4",
        "macro_CB": pa, "macro_MH": pb, "diff_cand_minus_ref": pb - pa, "point_pct": point,
        "ci90": [lo, hi], "threshold_pct": THRESH, "safety": sf,
        "verdict": verdict(point, lo, sf["breached"]),
        "report_only": {
            "per_seed_pct": per_seed,
            "per_seed_direction_all_positive": all(v > 0 for v in per_seed.values()),
            "seed_t90": seed_interval(list(per_seed.values())),
            "deleak712_point_pct": 100.0 * (pa7 - pb7) / pa7, "deleak712_ci90": ci90(dl),
            "per_call_win_fraction": float(np.mean(B < A)),
        }}
    base = (cell_mean(M_by_run, "CB", BAL) + cell_mean(M_by_run, "MB", BAL)) / 2.0
    hcq = (cell_mean(M_by_run, "CH", BAL) + cell_mean(M_by_run, "MH", BAL)) / 2.0
    li = np.flatnonzero(scen == low)
    lb, lh = float(base[li, 0].mean()), float(hcq[li, 0].mean())
    p2 = 100.0 * (lb - lh) / lb
    lo2, hi2 = ci90(boot_subset_effect(base[:, 0], hcq[:, 0], li))
    sf2 = safety(base[:, 0], hcq[:, 0], scen, order)
    li7 = np.flatnonzero((scen == low) & clean)
    per_seed2 = {}
    for s in BAL:
        bs = (M_by_run[("CB", s)][li, 0].mean() + M_by_run[("MB", s)][li, 0].mean()) / 2
        hs = (M_by_run[("CH", s)][li, 0].mean() + M_by_run[("MH", s)][li, 0].mean()) / 2
        per_seed2[s] = float(100.0 * (bs - hs) / bs)
    out["claim2"] = {
        "experiment": EXP2, "endpoint": "(base two-cell average - HCQ two-cell average)/base x 100, low bandwidth 469 calls MSE, seeds 0 to 2",
        "lowbw_base": lb, "lowbw_hcq": lh, "diff_cand_minus_ref": lh - lb, "point_pct": p2,
        "ci90": [lo2, hi2], "threshold_pct": THRESH, "safety": sf2,
        "verdict": verdict(p2, lo2, sf2["breached"]),
        "report_only": {
            "per_seed_pct": per_seed2,
            "per_seed_direction_all_positive": all(v > 0 for v in per_seed2.values()),
            "seed_t90": seed_interval(list(per_seed2.values())),
            "deleak712_point_pct": float(100.0 * (base[li7, 0].mean() - hcq[li7, 0].mean()) / base[li7, 0].mean()),
            "deleak712_ci90": ci90(boot_subset_effect(base[:, 0], hcq[:, 0], li7)),
            "per_call_win_fraction": float(np.mean(hcq[li, 0] < base[li, 0])),
        }}
    c = {k: cell_mean(M_by_run, k, BAL) for k in CELLS}
    mac = {k: macro(c[k][:, 0], scen, order) for k in CELLS}
    conf, ms = (c["CB"][:, 0] + c["CH"][:, 0]) / 2, (c["MB"][:, 0] + c["MH"][:, 0]) / 2
    bas, hq = (c["CB"][:, 0] + c["MB"][:, 0]) / 2, (c["CH"][:, 0] + c["MH"][:, 0]) / 2
    rep = {
        "encoder_main_effect_pct": {"point": 100 * (macro(conf, scen, order) - macro(ms, scen, order)) / macro(conf, scen, order),
                                    "ci90": ci90(boot_macro_effect(conf, ms, scen, order))},
        "reward_main_effect_pct": {"point": 100 * (macro(bas, scen, order) - macro(hq, scen, order)) / macro(bas, scen, order),
                                   "ci90": ci90(boot_macro_effect(bas, hq, scen, order))},
    }
    rng = np.random.default_rng(BSEED)
    inter = np.zeros(NBOOT)
    sums = {k: np.zeros(NBOOT) for k in CELLS}
    for s in order:
        idx = np.flatnonzero(scen == s)
        draw = idx[rng.integers(0, len(idx), size=(NBOOT, len(idx)))]
        for k in CELLS:
            sums[k] += c[k][draw, 0].mean(axis=1)
    for k in CELLS:
        sums[k] /= len(order)
    inter = 100 * (sums["CB"] - sums["CH"] - sums["MB"] + sums["MH"]) / sums["CB"]
    rep["interaction_pp"] = {"point": 100 * (mac["CB"] - mac["CH"] - mac["MB"] + mac["MH"]) / mac["CB"],
                             "ci90": ci90(inter), "definition": "(C-B − C-H − M-B + M-H)/C-B × 100"}
    rep["pairwise_seeds012"] = {}
    for ref, cand in (("CB", "CH"), ("CB", "MB"), ("CH", "MB"), ("CH", "MH"), ("MB", "MH"), ("CB", "MH")):
        rep["pairwise_seeds012"][f"{cand}_vs_{ref}"] = {
            "point_pct": 100 * (mac[ref] - mac[cand]) / mac[ref],
            "ci90": ci90(boot_macro_effect(c[ref][:, 0], c[cand][:, 0], scen, order))}
    names = ("mse", "e_plus", "e_minus", "err")
    rep["cells_by_scenario"] = {}
    for k in CELLS:
        X = cell_mean(M_by_run, k, SEEDS[k])
        rep["cells_by_scenario"][k] = {
            sub: {s: {names[j]: float(X[(scen == s) & mk][:, j].mean()) for j in range(4)} for s in order}
            for sub, mk in (("870", np.ones(len(X), bool)), ("712", clean))}
        rep["cells_by_scenario"][k]["macro_870"] = macro(X[:, 0], scen, order)
        rep["cells_by_scenario"][k]["seeds"] = list(SEEDS[k])
    rep["runs_macro_870"] = {f"{k}_s{s}": macro(M_by_run[(k, s)][:, 0], scen, order) for (k, s) in sorted(M_by_run)}
    out["report_only"] = rep
    return out


def synth_runs(mh_shift=None, noise=0.0, lowbw_hcq_pct=0.0, seed=0, high_extra=0.0):
    """Synthetic per-call metrics with C-B scenario means 16, 1 and 2.8, and controlled shifts, noise and HCQ effects for the self-test."""
    scen, order, _ = scen_labels()
    r = np.random.default_rng(seed)
    base = np.where(scen == "High BW", 16.0, np.where(scen == "Low BW", 1.0, 2.8)) * r.lognormal(0, 0.3, len(scen))
    for s in order:
        m = scen == s
        base[m] *= {"High BW": 16.0, "Low BW": 1.0, "Fluctuating": 2.8}[s] / base[m].mean()
    cb_macro = float(np.mean([base[scen == s].mean() for s in order]))
    runs = {}
    eps = r.normal(0, 1, len(scen))
    for s in order:
        m = scen == s
        eps[m] -= eps[m].mean()
    for cell in CELLS:
        for sd in SEEDS[cell]:
            x = base.copy()
            if cell == "MH":
                for sc, sh in (mh_shift or {}).items():
                    x[scen == sc] += sh * cb_macro
                x = x + noise * eps
            if cell in ("CH", "MH"):
                x[scen == "Low BW"] *= (1 - lowbw_hcq_pct / 100.0)
                x[scen == "High BW"] += high_extra * cb_macro
            M = np.zeros((len(scen), 4))
            M[:, 0] = x
            runs[(cell, sd)] = M
    return runs


def synth_markers(code, mutate=None):
    runs = {}
    for cell in CELLS:
        for s in SEEDS[cell]:
            man = {"cell": cell, "seed": s, "BWE_ENC": ENC[cell], "BWE_REWARD_LAMBDA": LAM[cell],
                   "max_timesteps": STEP, "code_sha256": dict(code), "rows_valid": ROWS_VALID,
                   "buffer_sha256": {"states": "S", "actions": "A", "next_states": "N", "dones": "D",
                                     "capacities": "C", "rewards": "R" + LAM[cell]}}
            runs[(cell, s)] = {"cell": cell, "seed": s, "step": STEP,
                               "checkpoint": f"/x/{cell}_s{s}/checkpoint_{STEP}.pt", "run_manifest": man,
                               "code_sha256_now": dict(code), "dump": {"ckpt_sha256": f"h{cell}{s}"}}
    if mutate:
        mutate(runs)
    return runs


def selftest() -> int:
    scen, order, clean = scen_labels()
    M = mt()
    ok_all = True

    def expect(name, got, want):
        nonlocal ok_all
        ok = got == want
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {got}, expected {want}")

    z = M.fm(M.TR)
    expect("fm comes from main_table_unified_v1, ground truth self-evaluation MSE is all 0", bool(np.nanmax(z[:, 0]) == 0.0), True)
    expect("Scenario call counts 77, 469, 324", [int((scen == s).sum()) for s in order], [77, 469, 324])

    def j(**kw):
        return judge(synth_runs(**kw), scen, order, clean)

    def even(f):
        return {"High BW": f, "Low BW": f, "Fluctuating": f}

    r = j(mh_shift=even(-0.02))
    expect("Claim one: 2.0% and interval lower bound greater than 0 is judged holds", r["claim1"]["verdict"], "holds")
    expect("Claim one point estimate is 2.0% by construction", round(r["claim1"]["point_pct"], 6), 2.0)
    r = j(mh_shift=even(-0.01))
    expect("Claim one: 1.0% and lower bound greater than 0 is judged direction only", (r["claim1"]["verdict"], r["claim1"]["ci90"][0] > 0), ("direction only", True))
    r = j(mh_shift=even(-0.02), noise=12.0)
    expect("Claim one: 2.0% but lower bound less than 0 is judged direction only",
           (r["claim1"]["verdict"], round(r["claim1"]["point_pct"], 6), r["claim1"]["ci90"][0] < 0),
           ("direction only", 2.0, True))
    r = j(mh_shift=even(0.005))
    expect("Claim one: -0.5% is judged does not hold", (r["claim1"]["verdict"], round(r["claim1"]["point_pct"], 6)), ("does not hold", -0.5))
    expect("Claim one: the difference is recorded as candidate minus reference, a positive change is worse", r["claim1"]["diff_cand_minus_ref"] > 0, True)
    r = j(mh_shift={"High BW": -0.165, "Low BW": 0.045, "Fluctuating": 0.0})
    expect("Claim one: low-bandwidth degradation raises the macro by 1.5%, triggering the safety line, judged does not hold",
           (r["claim1"]["verdict"], round(r["claim1"]["safety"]["worst_macro_rise_pct"], 6),
            round(r["claim1"]["point_pct"], 6), r["claim1"]["ci90"][0] > 0), ("does not hold", 1.5, 4.0, True))
    r = j(mh_shift={"High BW": -0.147, "Low BW": 0.027, "Fluctuating": 0.0})
    expect("Control: the same construction but with a macro increase of 0.9% does not trigger the safety line; criterion holds",
           (r["claim1"]["safety"]["breached"], r["claim1"]["verdict"]), (False, "holds"))
    runs = synth_runs(mh_shift=even(-0.02))
    sw = dict(runs)
    for s in SEEDS["CB"]:
        sw[("CB", s)], sw[("MH", s)] = runs[("MH", s)], runs[("CB", s)]
    expect("Sign negative control: after swapping C-B and M-H, the criterion does not hold", judge(sw, scen, order, clean)["claim1"]["verdict"], "does not hold")
    r = j(lowbw_hcq_pct=5.0)
    expect("Claim two: HCQ is 5% lower at low bandwidth, judged holds", (r["claim2"]["verdict"], round(r["claim2"]["point_pct"], 6)), ("holds", 5.0))
    r = j(lowbw_hcq_pct=1.0)
    expect("Claim two: 1% lower at low bandwidth, judged direction only", r["claim2"]["verdict"], "direction only")
    r = j(lowbw_hcq_pct=5.0, high_extra=0.045)
    expect("Claim two: 5% lower at low bandwidth but high-bandwidth degradation raises the macro by 1.5%, judged does not hold",
           (r["claim2"]["verdict"], round(r["claim2"]["safety"]["worst_macro_rise_pct"], 6)), ("does not hold", 1.5))
    r = j(lowbw_hcq_pct=-3.0)
    expect("Claim two: HCQ is instead 3% higher at low bandwidth, judged does not hold", r["claim2"]["verdict"], "does not hold")
    r = j(lowbw_hcq_pct=5.0)
    expect("Under the purely additive construction, the interaction term is 0", round(r["report_only"]["interaction_pp"]["point"], 9), 0.0)

    code = {"IQL.py": "x", "estimator.py": "y"}
    expect("Void: no void reason when everything is normal", void_reasons(synth_markers(code), code, {}, 6.74), [])

    def wrong_env(rs):
        rs[("CH", 1)]["run_manifest"]["BWE_REWARD_LAMBDA"] = "0.0"
    v = void_reasons(synth_markers(code, wrong_env), code, {}, 6.74)
    expect("Void: one cell had a wrong environment variable (the lambda for C-H seed 1 was written as 0.0)", any("environment variable" in x for x in v), True)

    def no_ckpt(rs):
        rs[("MH", 3)]["step"] = 40000
        rs[("MH", 3)]["checkpoint"] = "/x/MH_s3/checkpoint_40000.pt"
    v = void_reasons(synth_markers(code, no_ckpt), code, {}, 6.74)
    expect("Void: one cell is missing the 50000-step checkpoint", any("missing 50000-step checkpoint" in x for x in v), True)

    def missing(rs):
        rs[("CB", 4)] = None
    v = void_reasons(synth_markers(code, missing), code, {}, 6.74)
    expect("Void: one run is missing the evaluation marker", any("missing evaluation marker" in x for x in v), True)

    def bad_code(rs):
        rs[("MB", 2)]["run_manifest"]["code_sha256"] = {"IQL.py": "z", "estimator.py": "y"}
    v = void_reasons(synth_markers(code, bad_code), code, {}, 6.74)
    expect("Void: one run's code hash does not match the manifest", any("code hash" in x for x in v), True)

    def bad_buf(rs):
        rs[("MB", 2)]["run_manifest"]["buffer_sha256"]["states"] = "S2"
    v = void_reasons(synth_markers(code, bad_buf), code, {}, 6.74)
    expect("Void: one run's replay buffer state column differs from the rest", any("replay buffer" in x for x in v), True)
    v = void_reasons(synth_markers(code), code, {("CB", 0): "keys are inconsistent"}, 6.74)
    expect("Void: the evaluation export is misaligned", any("misaligned" in x for x in v), True)
    v = void_reasons(synth_markers(code), code, {}, 6.80)
    expect("Void: the recomputed checkpoint of the earlier version 6.80 exceeds 0.5%", any("0.5%" in x for x in v), True)
    v = void_reasons(synth_markers(code), code, {}, 6.770)
    expect("Control: recomputed 6.770 is within 0.5%, not void", v, [])

    tmp = LOCAL / "_selftest_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    good = tmp / "good.npz"
    lens = np.diff(M.off)[:20]
    np.savez_compressed(good, pred=np.zeros(int(lens.sum()), np.float32), lens=lens, keys=np.asarray(M.keys[:20]))
    keys_bad = list(M.keys[:20])
    keys_bad[3], keys_bad[4] = keys_bad[4], keys_bad[3]
    bad = tmp / "bad.npz"
    np.savez_compressed(bad, pred=np.zeros(int(lens.sum()), np.float32), lens=lens, keys=np.asarray(keys_bad))
    expect("Alignment check: exports matching the first 20 of the baseline pass", align_problem(good), None)
    expect("Alignment check negative control: swapping the exports of two calls was caught", align_problem(bad) is not None, True)
    for p in (good, bad):
        p.unlink()
    tmp.rmdir()
    print("Self-check" + ("all passed" if ok_all else "some checks failed"))
    return 0 if ok_all else 1


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pull():
    (LOCAL / "markers").mkdir(parents=True, exist_ok=True)
    (LOCAL / "eval").mkdir(parents=True, exist_ok=True)
    for (cell, s), host in sorted(HOST_OF.items()):
        tag = f"{cell}_s{s}"
        dst = LOCAL / "markers" / f"EVAL_{tag}_COMPLETE.json"
        r = subprocess.run(["scp", "-q", "-o", "ConnectTimeout=45", f"{host}:{REMOTE_MARK}/EVAL_{tag}_COMPLETE.json",
                            str(dst)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{tag} marker pull failed: {r.stderr.strip()[:200]}")
            continue
        mk = json.loads(dst.read_text(encoding="utf-8"))
        for remote in (mk["npz"], mk["npz_json"]):
            subprocess.run(["scp", "-q", "-o", "ConnectTimeout=45", f"{host}:{remote}",
                            str(LOCAL / "eval" / Path(remote).name)], check=True)
        if sha256(LOCAL / "eval" / Path(mk["npz"]).name) != mk["dump"]["npz_sha256"]:
            raise SystemExit(f"{tag} hash mismatch after export pull")
    for host in ("gpu-server-1", "gpu-server-2"):
        cm = LOCAL / "markers" / f"CURVE_{host}_DONE.json"
        r = subprocess.run(["scp", "-q", f"{host}:{REMOTE_MARK}/CURVE_{host}_DONE.json", str(cm)],
                           capture_output=True, text=True)
        if r.returncode == 0:
            (LOCAL / "eval" / "curve").mkdir(parents=True, exist_ok=True)
            for name in json.loads(cm.read_text(encoding="utf-8"))["files"]:
                subprocess.run(["scp", "-q", f"{host}:/path/to/server/outputs/enc_hcq_2x2_v1_eval/curve/{name}",
                                str(LOCAL / "eval" / "curve" / name)], check=True)
    for name in ("EVAL_PAPER_COMPLETE.json",):
        subprocess.run(["scp", "-q", f"gpu-server-1:{REMOTE_MARK}/{name}", str(LOCAL / "markers" / name)], check=True)
    pm = json.loads((LOCAL / "markers" / "EVAL_PAPER_COMPLETE.json").read_text(encoding="utf-8"))
    subprocess.run(["scp", "-q", f"gpu-server-1:{pm['npz']}", str(LOCAL / "eval" / Path(pm["npz"]).name)], check=True)
    subprocess.run(["scp", "-q", "gpu-server-2:/path/to/server/work/enc_hcq_2x2_v1/arm_manifest.json",
                    str(LOCAL / "arm_manifest.json")], check=True)


def write_outputs(res, M_by_run, scen, order, clean):
    M = mt()
    with open(LOCAL / "per_call_metrics.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cell", "seed", "encoder", "reward_lambda", "call", "scenario", "deleak712",
                    "mse", "e_plus", "e_minus", "err"])
        for (cell, s), X in sorted(M_by_run.items()):
            for i in range(len(X)):
                w.writerow([cell, s, ENC[cell], LAM[cell], M.keys[i], scen[i], int(clean[i]), *map(float, X[i])])
    (LOCAL / "data_dictionary.txt").write_text(
        "per_call_metrics.csv has one row per run and call.\ncell: CB, CH, MB, MH correspond to the cells C-B, C-H, M-B, M-H; seed: training seed; encoder: conf15 or ms15; reward_lambda: 0.0 or 0.4.\ncall: scenario directory plus file name, in the same order as arb_perstep_dump_v1; scenario: High BW, Low BW, Fluctuating; deleak712: membership of the 712-call leakage-free subset.\nmse: nanmean of the stepwise squared error, in units of Mbit/s squared; e_plus, e_minus: mean of the stepwise relative overestimation and underestimation; err: mean of the stepwise relative error truncated at 1, steps with missing ground truth are recorded as 1. The four metrics are computed by main_table_unified_v1.fm.\nresult.json: the verdict, interval, safety line and report-only items for the two claims; the macro value is the equal-weight average of the three scenarios.\n", encoding="utf-8")
    (LOCAL / "plot_enc_hcq_2x2.py").write_text(
        "# Generated by finalize_enc_hcq_2x2_v1.py. Reads result.json and plots four-cell three-scenario MSE, directly reproducible.\nimport json, matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\nfrom pathlib import Path\nH = Path(__file__).parent\nr = json.loads((H / 'result.json').read_text())['report_only']['cells_by_scenario']\nsc = ['High BW', 'Low BW', 'Fluctuating']\nfig, ax = plt.subplots(1, 3, figsize=(7.16, 2.2))\nfor k, s in enumerate(sc):\n    ax[k].bar(list(r), [r[c]['870'][s]['mse'] for c in r])\n    ax[k].set_title(s, fontsize=8)\nax[0].set_ylabel('MSE (Mbps$^2$)')\nfig.tight_layout()\nfig.savefig(H / 'cells_by_scenario.pdf')\n", encoding="utf-8")
    (LOCAL / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str) + "\n",
                                       encoding="utf-8")
    lines = [f"{sha256(p)}  {p.relative_to(LOCAL)}" for p in sorted(LOCAL.rglob("*"))
             if p.is_file() and p.name != "sha256sums.txt"]
    (LOCAL / "sha256sums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def real(register: bool) -> int:
    scen, order, clean = scen_labels()
    arm_code = json.loads((LOCAL / "arm_manifest.json").read_text(encoding="utf-8"))["code_sha256"]
    runs, align, M_by_run = {}, {}, {}
    for cell in CELLS:
        for s in SEEDS[cell]:
            p = LOCAL / "markers" / f"EVAL_{cell}_s{s}_COMPLETE.json"
            if not p.exists():
                runs[(cell, s)] = None
                continue
            mk = json.loads(p.read_text(encoding="utf-8"))
            runs[(cell, s)] = mk
            npz = LOCAL / "eval" / Path(mk["npz"]).name
            prob = align_problem(npz) if npz.exists() else "Export file is not local"
            if prob is None and len(np.load(npz, allow_pickle=True)["keys"]) != mt().n:
                prob = "The number of exported calls is not 870"
            align[(cell, s)] = prob
            if prob is None:
                M_by_run[(cell, s)] = score_npz(npz)
    paper_npz = LOCAL / "eval" / "paper_ckpt_1240000.npz"
    paper_macro = None
    if paper_npz.exists() and align_problem(paper_npz) is None:
        paper_macro = macro(score_npz(paper_npz)[:, 0], scen, order)
    why = void_reasons(runs, arm_code, align, paper_macro)
    res = {"experiments": [EXP1, EXP2], "paper_ckpt_macro": paper_macro, "void_reasons": why}
    if why:
        res["claim1"] = {"verdict": "void"}
        res["claim2"] = {"verdict": "void"}
    else:
        res.update(judge(M_by_run, scen, order, clean))
    curve = {}
    for f in sorted((LOCAL / "eval" / "curve").glob("*.npz")):
        tag, st = f.stem.rsplit("_", 1)
        if align_problem(f) is None and len(np.load(f, allow_pickle=True)["keys"]) == mt().n:
            curve.setdefault(tag, {})[int(st)] = macro(score_npz(f)[:, 0], scen, order)
    for (k, s_), X in M_by_run.items():
        if f"{k}_s{s_}" in curve:
            curve[f"{k}_s{s_}"][STEP] = macro(X[:, 0], scen, order)
    res.setdefault("report_only_curve", curve or "No intermediate checkpoints exported")
    write_outputs(res, M_by_run, scen, order, clean)
    for k in ("claim1", "claim2"):
        c = res[k]
        print(f"{k} {c.get('experiment', '')}: {c['verdict']}, point estimate {c.get('point_pct')}, 90% interval {c.get('ci90')}")
    if why:
        print("Void reason:", why)
    if register:
        sys.path.insert(0, str(ROOT / "scripts/lib"))
        from two_arm_judge import exp_cmd
        for k, exp in (("claim1", EXP1), ("claim2", EXP2)):
            c = res[k]
            v = {"holds": "holds (strong)", "direction only": "direction only (medium)", "does not hold": "does not hold", "void": "void"}[c["verdict"]]
            exp_cmd(ROOT, "data", "--id", exp, "--metrics", json.dumps({kk: c.get(kk) for kk in (
                "point_pct", "ci90", "diff_cand_minus_ref")}, ensure_ascii=False),
                    "--artifact", str(LOCAL / "result.json"), "--artifact", str(LOCAL / "per_call_metrics.csv"))
            basis = (f"Point estimate {c.get('point_pct')}%, 90% interval {c.get('ci90')}, safety line worst-case macro increase {(c.get('safety') or {}).get('worst_macro_rise_pct')}%" if c["verdict"] != "void"
                     else ";".join(why))
            exp_cmd(ROOT, "conclude", "--id", exp, "--verdict", v,
                    "--vs-criteria", "Compare item by item against the pre-registration criteria, see experiments/results/enc_hcq_2x2_v1/result.json",
                    "--basis", basis, "--limitations", "870 offline calls, fifteen-token LoRA recipe with the capacity anchor, 50k steps; the primary interval covers call sampling only, the seed-level interval is reported separately")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check-dump", help="check one per-step export against the reference export (alignment and metrics)")
    ap.add_argument("--paper", help="per-step export of the recomputed checkpoint of the earlier version")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--local", help="Results directory, default experiments/results/enc_hcq_2x2_v1; for a smoke test, point it to the draft directory")
    a = ap.parse_args()
    if a.local:
        global LOCAL
        LOCAL = Path(a.local)
        if a.register:
            raise SystemExit("--local is for smoke test only, must not be used with --register")
    if a.selftest:
        return selftest()
    if a.check_dump or a.paper:
        rc = 0
        if a.check_dump:
            prob = align_problem(Path(a.check_dump))
            print(f"Export alignment: {'Pass' if prob is None else 'did not pass,' + prob}")
            rc |= prob is not None
        if a.paper:
            scen, order, _ = scen_labels()
            prob = align_problem(Path(a.paper))
            X = score_npz(Path(a.paper))
            mac = macro(X[:, 0], scen, order)
            rel = abs(mac - PAPER_REF) / PAPER_REF
            print(f"recomputed checkpoint of the earlier version: macro MSE {mac:.6f}, per-scenario {dict(zip(order, scen_means(X[:, 0], scen, order).round(6)))}, relative difference with {PAPER_REF} {rel * 100:.4f}%, {'in' if rel <= PAPER_TOL else 'exceed'} 0.5% {'within' if rel <= PAPER_TOL else ''}; aligned with {'Pass' if prob is None else prob}")
            rc |= (rel > PAPER_TOL) or (prob is not None)
        return int(rc)
    if a.pull:
        pull()
    return real(a.register)


if __name__ == "__main__":
    sys.exit(main())
