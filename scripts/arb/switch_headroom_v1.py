#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headroom of per-step expert switching: oracle ceilings only, no selector and no model calls.
Each call's loss L (underestimation + 3 x overestimation) is split into per-step contributions, and their sum is checked against the frozen metric functions in eval_metrics (relative tolerance 1e-5, else abort).
For block sizes K = 17, 50 and 167 it reports FIXED (best single arm), the per-call oracle, the per-block oracle (BLOCK) and the one-block-late oracle (LAG), with Low BW and macro gains over FIXED and bootstrap 95% intervals.
Writes result.json with the verdict on LAG at K = 50. Usage: python switch_headroom_v1.py
"""
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/c3q"))
from eval_metrics import over as ev_over, under as ev_under  # noqa: E402

NPZ = ROOT / "experiments/results/arb_perstep_dump_v1/perstep.npz"
OUT = ROOT / "experiments/results/switch_headroom_v1"
MAIN = ["Pioneer", "Schaferct(public)", "Schaferct(retrained)", "MLP_seed0"]
SCEN = {"high_bw_call": "High BW", "low_bw_call": "Low BW",
        "high_fluctuating_bw": "Fluctuating", "low_fluctuating_bw": "Fluctuating"}
ORDER = ["High BW", "Low BW", "Fluctuating"]
KS = [17, 50, 167]
K_MAIN = 50
W = 3.0
SEED = 20260909
NBOOT = 10000
STEP_S = 0.06
TOL = 1e-5


def contributions(pred, truth):
    """Return per-step contributions c_t with file-level L = sum of c_t, reproducing the frozen metrics' asymmetric NaN handling."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (pred - truth) / truth
    o = np.where(np.isnan(r), np.nan, np.maximum(r, 0.0))
    u = np.where(-r > 0, -r, 0.0)
    n_all = len(truth)
    n_valid = int(np.sum(~np.isnan(o)))
    return u / n_all + W * np.nan_to_num(o, nan=0.0) / n_valid


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    z = np.load(NPZ, allow_pickle=True)
    off = z["offsets"]; keys = [str(k) for k in z["keys"]]; dirs = [str(d) for d in z["dirs"]]
    truth = z["truth_mbps"].astype(np.float64)
    P = {a: z[f"pred__{a}"].astype(np.float64) for a in MAIN}
    n = len(keys)
    scen = np.array([SCEN[d] for d in dirs])

    for a in MAIN:
        assert not np.isnan(P[a]).any(), f"{a} prediction contains NaN: the denominator would depend on the arm and the per-step decomposition fails"
    valid_t = truth[~np.isnan(truth)]
    assert (valid_t > 0).all(), "Ground truth contains non-positive numbers"

    C = []
    for i in range(n):
        s, e = off[i], off[i + 1]
        C.append(np.stack([contributions(P[a][s:e], truth[s:e]) for a in MAIN]))

    worst = 0.0
    for i in range(n):
        s, e = off[i], off[i + 1]
        for j, a in enumerate(MAIN):
            ref = float(ev_under(P[a][s:e], truth[s:e])) + W * float(ev_over(P[a][s:e], truth[s:e]))
            mine = float(C[i][j].sum())
            worst = max(worst, abs(mine - ref) / max(abs(ref), 1e-12))
    print(f"Consistency: maximum relative difference of the stepwise decomposition against the frozen function {worst:.3e} (threshold {TOL:.0e})", flush=True)
    if worst > TOL:
        (OUT / "ABORTED.json").write_text(json.dumps({"consistency_worst_rel": worst}))
        raise SystemExit("Consistency check failed; aborted without reporting numbers")

    fileL = np.array([[C[i][j].sum() for j in range(len(MAIN))] for i in range(n)])
    macro_arm = [np.mean([fileL[scen == s, j].mean() for s in ORDER]) for j in range(len(MAIN))]
    jfix = int(np.argmin(macro_arm))
    print("FIXED arm:", MAIN[jfix], flush=True)

    res = {"consistency_worst_rel": worst, "fixed_arm": MAIN[jfix], "K": {}}
    fixed_pf = fileL[:, jfix]
    fileoracle_pf = fileL.min(axis=1)
    rng = np.random.default_rng(SEED)
    boot_idx = {s: rng.integers(0, (scen == s).sum(), size=(NBOOT, (scen == s).sum())) for s in ORDER}

    def gain(base, new, scope):
        if scope == "Low BW":
            b, x = base[scen == scope], new[scen == scope]
            pt = (b.mean() - x.mean()) / b.mean() * 100
            I = boot_idx[scope]
            bs = (b[I].mean(1) - x[I].mean(1)) / b[I].mean(1) * 100
        else:
            bm = np.mean([base[scen == s].mean() for s in ORDER])
            xm = np.mean([new[scen == s].mean() for s in ORDER])
            pt = (bm - xm) / bm * 100
            bb = np.mean([base[scen == s][boot_idx[s]].mean(1) for s in ORDER], axis=0)
            xx = np.mean([new[scen == s][boot_idx[s]].mean(1) for s in ORDER], axis=0)
            bs = (bb - xx) / bb * 100
        lo, hi = np.percentile(bs, [2.5, 97.5])
        return {"pct": float(pt), "ci95": [float(lo), float(hi)]}

    for K in KS:
        block_pf, lag_pf = np.zeros(n), np.zeros(n)
        persist = {s: [0, 0] for s in ORDER}
        switches, minutes = {s: 0 for s in ORDER}, {s: 0.0 for s in ORDER}
        for i in range(n):
            T = C[i].shape[1]
            starts = np.arange(0, T, K)
            B = np.add.reduceat(C[i], starts, axis=1)
            best = B.argmin(axis=0)
            block_pf[i] = B.min(axis=0).sum()
            use = np.empty_like(best); use[0] = jfix; use[1:] = best[:-1]
            lag_pf[i] = B[use, np.arange(B.shape[1])].sum()
            s = scen[i]
            persist[s][0] += int((best[1:] == best[:-1]).sum()); persist[s][1] += max(len(best) - 1, 0)
            switches[s] += int((use[1:] != use[:-1]).sum()); minutes[s] += T * STEP_S / 60
        blk = {}
        for name, v in [("FIXED", fixed_pf), ("FILE_ORACLE_pos4", fileoracle_pf),
                        ("BLOCK", block_pf), ("LAG", lag_pf)]:
            blk[name] = {"macro": float(np.mean([v[scen == s].mean() for s in ORDER])),
                         **{s: float(v[scen == s].mean()) for s in ORDER}}
        blk["gain_vs_FIXED"] = {nm: {sc.replace(" ", ""): gain(fixed_pf, v, sc) for sc in ["Low BW", "macro"]}
                                for nm, v in [("BLOCK", block_pf), ("LAG", lag_pf), ("FILE_ORACLE_pos4", fileoracle_pf)]}
        blk["BLOCK_extra_vs_pos4_fileoracle_lowbw_pct"] = float(
            (fileoracle_pf[scen == "Low BW"].mean() - block_pf[scen == "Low BW"].mean())
            / fileoracle_pf[scen == "Low BW"].mean() * 100)
        blk["persistence"] = {s: persist[s][0] / max(persist[s][1], 1) for s in ORDER}
        blk["lag_switches_per_min"] = {s: switches[s] / max(minutes[s], 1e-9) for s in ORDER}
        res["K"][str(K)] = blk

    g = res["K"][str(K_MAIN)]["gain_vs_FIXED"]["LAG"]["LowBW"]
    if g["pct"] < 1.631 or g["ci95"][0] <= 0:
        verdict = "withdrawn: LAG(50) low-bandwidth improvement is below 1.631% or its interval lower bound is not above 0"
    elif g["pct"] < 3.0:
        verdict = "Direction only: 1.631% to 3%, does not enter the second stage"
    else:
        verdict = "enters the second stage: at least 3% with an interval lower bound above 0"
    res["verdict_by_criteria"] = verdict
    (OUT / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))

    for K in KS:
        b = res["K"][str(K)]
        print(f"\n===== K={K} (about {K*STEP_S:.1f} seconds per block)")
        for nm in ["FIXED", "FILE_ORACLE_pos4", "BLOCK", "LAG"]:
            print(f"  {nm:17s} low bandwidth L={b[nm]['Low BW']:.4f}  macro L={b[nm]['macro']:.4f}")
        for nm in ["BLOCK", "LAG"]:
            x = b["gain_vs_FIXED"][nm]["LowBW"]; y = b["gain_vs_FIXED"][nm]["macro"]
            print(f"  {nm:5s} versus FIXED  low bandwidth {x['pct']:+7.3f}% [{x['ci95'][0]:+.3f},{x['ci95'][1]:+.3f}]  macro {y['pct']:+7.3f}% [{y['ci95'][0]:+.3f},{y['ci95'][1]:+.3f}]")
        print(f"  BLOCK extra gain over the per-file ceiling of the four (low bandwidth) {b['BLOCK_extra_vs_pos4_fileoracle_lowbw_pct']:+.3f}%")
        print(f"  persistence rate " + "  ".join(f"{s}={v:.3f}" for s, v in b["persistence"].items()))
        print(f"  LAG switches per minute " + "  ".join(f"{s}={v:.2f}" for s, v in b["lag_switches_per_min"].items()))
    print(f"\nCriterion: {verdict}")
    (OUT / "DONE.json").write_text(json.dumps({"ok": True}))


if __name__ == "__main__":
    main()
