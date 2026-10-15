#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Causal expert switching: rule-based and learned selectors against the fixed expert, on the per-step dump of four estimators.
The choice for block b uses only steps before block b; block 0 uses FIXED (the challenge baseline). All blocks of a file share one cross-validation fold.
Rules and hyperparameters are selected on the training folds by the summed file-level loss L, the quantity used for evaluation.
Candidates: MINPSEUDO, MINPSEUDO_GATED, CONSERV, RULE1, RULE2 and a GBDT regressor, for block sizes K = 50, 17 and 167 steps; at K = 50 a shuffled-row negative control is also run.
Writes result.json with Low BW and macro gains over FIXED (bootstrap 95% intervals) and the verdict. Usage: python switch_causal_control_v1.py
"""
import json, sys, itertools
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/arb"))
from switch_headroom_v1 import contributions

NPZ = ROOT / "experiments/results/arb_perstep_dump_v1/perstep.npz"
OUT = ROOT / "experiments/results/switch_causal_control_v1"
MAIN = ["Pioneer", "Schaferct(public)", "Schaferct(retrained)", "MLP_seed0"]
JFIX = 1
SCEN = {"high_bw_call": "High BW", "low_bw_call": "Low BW",
        "high_fluctuating_bw": "Fluctuating", "low_fluctuating_bw": "Fluctuating"}
ORDER = ["High BW", "Low BW", "Fluctuating"]
KS = [50, 17, 167]
K_MAIN = 50
W = 3.0
SEED = 20260909
NBOOT = 10000
NFOLD = 5
LAG50 = 70.252
GATE_Q = [0.5, 0.75, 0.9]
RULE1_Q = [i / 10 for i in range(1, 10)]
RULE2_Q = [1 / 3, 2 / 3]
GBDT = dict(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=SEED)
NA = len(MAIN)


def load():
    z = np.load(NPZ, allow_pickle=True)
    off = z["offsets"]; dirs = [str(d) for d in z["dirs"]]
    F = z["feat_short"].astype(np.float64)
    T = z["truth_mbps"].astype(np.float64)
    P = np.stack([z[f"pred__{a}"].astype(np.float64) for a in MAIN])
    scen = np.array([SCEN[d] for d in dirs])
    files = []
    for i in range(len(dirs)):
        s, e = off[i], off[i + 1]
        p = P[:, s:e]; tr = T[s:e]
        C = np.stack([contributions(p[j], tr) for j in range(NA)])
        with np.errstate(divide="ignore", invalid="ignore"):
            r = (p - tr) / tr
        o = np.where(np.isnan(r), 0.0, np.maximum(r, 0.0)); u = np.where(-r > 0, -r, 0.0)
        ell = u + W * o
        f0 = F[s:e, 0] / 1e6
        with np.errstate(divide="ignore", invalid="ignore"):
            rp = (p - f0) / f0
        ps = np.where(f0 > 1e-6, np.maximum(-rp, 0) + W * np.maximum(rp, 0), np.nan)
        files.append(dict(C=C, ell=ell, p=p, f0=f0, f3=F[s:e, 3], f6=F[s:e, 6], f9=F[s:e, 9],
                          f10=F[s:e, 10], ps=ps))
    return files, scen


def slope(x):
    n = len(x)
    if n < 2:
        return 0.0
    t = np.arange(n) - (n - 1) / 2
    return float(np.dot(t, x - x.mean()) / np.dot(t, t))


def build_blocks(files, K):
    """Split each call into K-step blocks and build the features of block b >= 1 from block b-1; return features, (file, block) ids, block contributions, block losses and names."""
    rows, meta, Bc, Bell = [], [], [], []
    for i, f in enumerate(files):
        T = f["C"].shape[1]
        st = np.arange(0, T, K)
        Bc.append(np.add.reduceat(f["C"], st, axis=1))
        cnt = np.diff(np.append(st, T))
        Bell.append(np.add.reduceat(f["ell"], st, axis=1) / cnt)
        for b in range(1, len(st)):
            a, e = st[b - 1], st[b]
            f0 = f["f0"][a:e]; p = f["p"][:, a:e]; f3 = f["f3"][a:e]
            m0 = f0.mean(); h = len(f0) // 2
            r = [m0, f0.std() / m0 if m0 > 0 else 0.0,
                 (f0[h:].mean() / f0[:h].mean()) if h > 0 and f0[:h].mean() > 0 else 1.0,
                 f3.mean(), np.percentile(f3, 95), slope(f3),
                 f["f6"][a:e].mean(), f["f9"][a:e].mean(), f["f10"][a:e].mean()]
            for j in range(NA):
                ps = f["ps"][j, a:e]
                r += [p[j].mean() / m0 if m0 > 0 else 0.0,
                      np.nanmean(ps) if np.isfinite(ps).any() else 0.0,
                      slope(p[j])]
            mu = p.mean(axis=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                dis = np.where(mu > 0, p.std(axis=0) / mu, 0.0)
            r.append(float(dis.mean()))
            rows.append(r); meta.append((i, b))
    names = ["f0_mean", "f0_cv", "f0_trend", "f3_mean", "f3_p95", "f3_slope", "f6_mean", "f9_mean", "f10_mean"]
    for a in MAIN:
        t = a.replace("(", "_").replace(")", "")
        names += [f"{t}_ratio", f"{t}_pseudo", f"{t}_slope"]
    names.append("disagree")
    X = np.nan_to_num(np.array(rows), nan=0.0, posinf=0.0, neginf=0.0)
    return X, np.array(meta), Bc, Bell, names


def gated_pseudo(files, K, tau):
    """Return each arm's mean pseudo-loss over the previous block's steps with f3 > tau; NaN when no step qualifies, so the caller falls back to FIXED."""
    out = []
    for f in files:
        T = f["C"].shape[1]; st = np.arange(0, T, K)
        m = (f["f3"] > tau)[None, :] & np.isfinite(f["ps"])
        num = np.add.reduceat(np.where(m, f["ps"], 0.0), st, axis=1)
        den = np.add.reduceat(m.astype(float), st, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            g = np.where(den > 0, num / den, np.nan)
        out.append(g[:, :-1].T)
    return np.concatenate(out, axis=0)


def file_L(choice, meta, Bc, nfile):
    """Sum block contributions into a file-level L, with FIXED for block 0 and the chosen arm for each later block."""
    L = np.array([Bc[i][JFIX, 0] for i in range(nfile)], dtype=float)
    np.add.at(L, meta[:, 0], np.array([Bc[i][c, b] for (i, b), c in zip(meta, choice)]))
    return L


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files, scen = load()
    n = len(files)
    rng0 = np.random.default_rng(SEED)
    fold = np.zeros(n, dtype=int)
    for s in ORDER:
        idx = np.where(scen == s)[0]; perm = rng0.permutation(len(idx))
        fold[idx[perm]] = np.arange(len(idx)) % NFOLD
    step_f3 = [f["f3"] for f in files]
    rngb = np.random.default_rng(SEED)
    boot = {s: rngb.integers(0, (scen == s).sum(), size=(NBOOT, (scen == s).sum())) for s in ORDER}

    def gain(base, new, scope):
        if scope == "Low BW":
            b, x = base[scen == scope], new[scen == scope]; I = boot[scope]
            pt = (b.mean() - x.mean()) / b.mean() * 100
            bs = (b[I].mean(1) - x[I].mean(1)) / b[I].mean(1) * 100
        else:
            bm = np.mean([base[scen == s].mean() for s in ORDER]); xm = np.mean([new[scen == s].mean() for s in ORDER])
            pt = (bm - xm) / bm * 100
            bb = np.mean([base[scen == s][boot[s]].mean(1) for s in ORDER], axis=0)
            xx = np.mean([new[scen == s][boot[s]].mean(1) for s in ORDER], axis=0)
            bs = (bb - xx) / bb * 100
        lo, hi = np.percentile(bs, [2.5, 97.5])
        return {"pct": float(pt), "ci95": [float(lo), float(hi)]}

    res = {"seed": SEED, "K": {}}
    for K in KS:
        X, meta, Bc, Bell, names = build_blocks(files, K)
        rowfold = fold[meta[:, 0]]
        Rc = np.array([Bc[i][:, b] for i, b in meta])
        Rell = np.array([Bell[i][:, b] for i, b in meta])
        pidx = [names.index(f"{a.replace('(', '_').replace(')', '')}_pseudo") for a in MAIN]
        imin = [names.index(f"{a.replace('(', '_').replace(')', '')}_ratio") for a in MAIN]
        idis = names.index("disagree")
        print(f"K={K}: {len(X)} decision blocks, {len(names)} features", flush=True)

        def run(Xuse, shuffled):
            ch = {m: np.full(len(Xuse), JFIX) for m in
                  ["FIXED", "MINPSEUDO", "MINPSEUDO_GATED", "CONSERV", "RULE1", "RULE2", "GBDT_reg"]}
            ch["MINPSEUDO"] = np.argmin(Xuse[:, pidx], axis=1)
            for k in range(NFOLD):
                tr, te = rowfold != k, rowfold == k
                Ctr = Rc[tr]
                trf = np.where(fold != k)[0]
                allf3 = np.concatenate([step_f3[i] for i in trf])
                # MINPSEUDO_GATED
                best = (np.inf, None)
                for q in GATE_Q:
                    tau = np.quantile(allf3, q)
                    G = gated_pseudo(files, K, tau)
                    if shuffled:
                        G = G[perm_rows]
                    c = np.where(np.isnan(G).all(axis=1), JFIX, np.nanargmin(np.where(np.isnan(G), np.inf, G), axis=1))
                    sc = Ctr[np.arange(tr.sum()), c[tr]].sum()
                    if sc < best[0]:
                        best = (sc, c)
                ch["MINPSEUDO_GATED"][te] = best[1][te]
                # CONSERV
                d = Xuse[:, idis]; low = np.argmin(Xuse[:, imin], axis=1)
                best = (np.inf, None)
                for q in RULE1_Q:
                    td = np.quantile(d[tr], q)
                    c = np.where(d > td, low, JFIX)
                    sc = Ctr[np.arange(tr.sum()), c[tr]].sum()
                    if sc < best[0]:
                        best = (sc, c)
                ch["CONSERV"][te] = best[1][te]
                # RULE1
                Xtr = Xuse[tr]; best = (np.inf, None)
                for fi in range(Xuse.shape[1]):
                    for q in RULE1_Q:
                        t = np.quantile(Xtr[:, fi], q); lo = Xtr[:, fi] <= t
                        if lo.all() or (~lo).all():
                            continue
                        sl, sh = Ctr[lo].sum(0), Ctr[~lo].sum(0)
                        sc = sl.min() + sh.min()
                        if sc < best[0]:
                            best = (sc, (fi, t, int(sl.argmin()), int(sh.argmin())))
                fi, t, al, ah = best[1]
                ch["RULE1"][te] = np.where(Xuse[te, fi] <= t, al, ah)
                # RULE2
                qs = {fi: [np.quantile(Xtr[:, fi], q) for q in RULE2_Q] for fi in range(Xuse.shape[1])}
                best = (np.inf, None)
                for fa, fb in itertools.combinations(range(Xuse.shape[1]), 2):
                    for ta in qs[fa]:
                        ma = Xtr[:, fa] <= ta
                        for tb in qs[fb]:
                            mb = Xtr[:, fb] <= tb
                            quad = [ma & mb, ma & ~mb, ~ma & mb, ~ma & ~mb]
                            sums = [Ctr[qm].sum(0) for qm in quad]
                            sc = sum(s.min() for s in sums)
                            if sc < best[0]:
                                best = (sc, (fa, ta, fb, tb, [int(s.argmin()) for s in sums]))
                fa, ta, fb, tb, pk = best[1]
                ma, mb = Xuse[te, fa] <= ta, Xuse[te, fb] <= tb
                o = np.empty(te.sum(), dtype=int)
                o[ma & mb] = pk[0]; o[ma & ~mb] = pk[1]; o[~ma & mb] = pk[2]; o[~ma & ~mb] = pk[3]
                ch["RULE2"][te] = o
                # GBDT_reg
                from sklearn.ensemble import GradientBoostingRegressor
                pr = np.column_stack([GradientBoostingRegressor(**GBDT).fit(Xtr, Rell[tr, j]).predict(Xuse[te])
                                      for j in range(NA)])
                ch["GBDT_reg"][te] = pr.argmin(axis=1)
                print(f"  K={K} {'shuffle' if shuffled else 'Real'} fold {k} complete", flush=True)
            return {m: file_L(c, meta, Bc, n) for m, c in ch.items()}

        perm_rows = np.arange(len(X))
        real = run(X, False)
        blk = {"n_blocks": len(X), "features": names, "methods": {}}
        base = real["FIXED"]
        # FIXED must reproduce the switch_headroom_v1 Low BW loss; the 1e-12 relative tolerance only absorbs summation-order rounding.
        fx = float(base[scen == "Low BW"].mean())
        assert abs(fx - 1.4324234147085393) / 1.4324234147085393 <= 1e-12, \
            f"FIXED low bandwidth {fx!r} differs from the first-stage value 1.4324234147085393 (definition drift); abort"
        for m, Lf in real.items():
            blk["methods"][m] = {"Low BW": float(Lf[scen == "Low BW"].mean()),
                                 "macro": float(np.mean([Lf[scen == s].mean() for s in ORDER])),
                                 "gain_LowBW": gain(base, Lf, "Low BW"), "gain_macro": gain(base, Lf, "macro")}
        if K == K_MAIN:
            perm_rows = np.random.default_rng(SEED + 1).permutation(len(X))
            shuf = run(X[perm_rows], True)
            blk["SHUF_gain_LowBW_pct"] = {m: gain(base, Lf, "Low BW")["pct"] for m, Lf in shuf.items() if m != "FIXED"}
            cands = ["MINPSEUDO", "MINPSEUDO_GATED", "CONSERV", "RULE1", "RULE2", "GBDT_reg"]
            ok = [m for m in cands if blk["methods"][m]["gain_LowBW"]["ci95"][0] > 0]
            leak = {m: v for m, v in blk["SHUF_gain_LowBW_pct"].items()
                    if m in ["MINPSEUDO_GATED", "CONSERV", "RULE1", "RULE2", "GBDT_reg"] and v > 3.0}
            if leak:
                verdict = f"void, to be rerun: the shuffled negative control did not degrade {leak}"
            elif not ok:
                verdict = "Position 6 withdrawn: no candidate has an interval lower bound above 0"
            else:
                R = max(blk["methods"][m]["gain_LowBW"]["pct"] for m in ok)
                bm = max(ok, key=lambda m: blk["methods"][m]["gain_LowBW"]["pct"])
                resid = LAG50 - R
                if R < 1.631:
                    verdict = f"Position 6 withdrawn: R={R:.3f}% less than 1.631%"
                elif resid < 1.631:
                    verdict = f"Rules exhausted: strongest {bm} R={R:.3f}%, residual {resid:.3f}% is below 1.631%; the rule enters the system as is and does not count as an LLM contribution"
                elif resid >= 3.0:
                    verdict = f"An LLM selector is worth testing: strongest {bm} R={R:.3f}%, residual {resid:.3f}%; must beat {bm} by at least 1.631% with an interval lower bound above 0"
                else:
                    verdict = f"Direction: strongest {bm} R={R:.3f}%, residual {resid:.3f}% lies between 1.631% and 3%"
            blk["verdict"] = verdict
        res["K"][str(K)] = blk
        (OUT / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float))

    for K in KS:
        b = res["K"][str(K)]
        print(f"\n===== K={K} ({b['n_blocks']} decision blocks)")
        for m, v in b["methods"].items():
            g, gm = v["gain_LowBW"], v["gain_macro"]
            print(f"  {m:16s} low bandwidth L={v['Low BW']:.4f}  {g['pct']:+8.3f}% [{g['ci95'][0]:+8.3f},{g['ci95'][1]:+8.3f}]   macro {gm['pct']:+7.3f}% [{gm['ci95'][0]:+.3f},{gm['ci95'][1]:+.3f}]")
        if "SHUF_gain_LowBW_pct" in b:
            print("  shuffled negative control low bandwidth gain " + "  ".join(f"{m}={v:+.2f}%" for m, v in b["SHUF_gain_LowBW_pct"].items()))
            print(f"  Criterion: {b['verdict']}")
    (OUT / "DONE.json").write_text(json.dumps({"ok": True}))


if __name__ == "__main__":
    main()
