#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data and gates of Fig. 3, the two-column designer figure (fig_designer_three.pdf). bar_rows() gives (a) balanced accuracy on the 12 new client stacks and (b) the share of the 42
end-to-end cells correct on real software, with data, gates and row order from make_fig_designer_v3.py plus the same hosted model as a generic schema matcher
(llm-schema-match-baseline-v1) and as a two-step matcher (llm-twostep-match-v1); cl_cells() gives (c) the closed-loop utility deviation per schema and window cell,
data and gates from make_fig_closedloop_designer_v2.py (obsschema-closedloop-v2). Merges those two scripts; its own drawing is an earlier layout of Fig. 3.
make_fig_designer_v6.py, which draws Fig. 3 of the paper, and make_fig_designer_v5.py import bar_rows() and cl_cells().
Usage: python3 scripts/paper/make_fig_designer_v4.py (writes papers/revision-v2/figs/fig_designer_three.pdf in the earlier layout; rerun make_fig_designer_v6.py afterwards)
"""
import json, statistics as st, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/paper"))
import ieee_style as S   # noqa: E402
import make_fig_designer_v3 as D3   # noqa: E402
import make_fig_closedloop_designer_v2 as C2   # noqa: E402
CL = C2.CL
OUT = ROOT / "papers/revision-v2/figs/fig_designer_three.pdf"


def bar_rows():
    """Rows (name, BA, end-to-end rate, colour, BA range, end-to-end range) for panels (a) and (b), with the gates of make_fig_designer_v3.main."""
    import make_tables_v2 as T2, matplotlib
    sc = D3.reg("realtel-scale-v1"); e2 = T2.e2e_v3()
    base = ["COMA", "CUPID", "TFIDF", "MPNET", "BGE", "NAME", "SF"]
    nice = {"COMA": "COMA", "CUPID": "Cupid", "TFIDF": "TF-IDF", "MPNET": "mpnet", "BGE": "bge", "NAME": "Name", "SF": "SF"}
    oa = {t: D3.open_ba(t) for t in D3.REG_OPEN}
    for t, want in D3.REG_OPEN.items():
        assert round(oa[t], 3) == want, (t, oa[t], want)
    for k, want in D3.REG_E2E_V3.items():
        assert round(e2["rate"][k], 3) == want, (k, e2["rate"][k], want)
    assert e2["n"] == 42, e2["n"]
    base = sorted(base, key=lambda b: (-sc["ba_base"][b], b))
    BL = matplotlib.colormaps["Blues"]; C_HOST, C_OPEN, C_BASE = BL(0.8), BL(0.5), "#C8C8C8"
    V = json.load(open(ROOT / "experiments/results/open_sampling_variance_v1/summary.json"))
    assert all(V[m]["n_samples"] == 3 for m in ("r1_32b", "r1_14b")), "Open-source model has not completed three samples"
    rng = lambda m, k: (V[m][k]["min"], V[m][k]["max"])
    lm = D3.reg("llm-schema-match-baseline-v1")["scale12"]; ts = D3.reg("llm-twostep-match-v1")
    assert round(lm["ba_llm_match"], 3) == 0.719 and round(ts["scale12"]["ba_twostep"], 3) == 0.966, (lm["ba_llm_match"], ts["scale12"]["ba_twostep"])
    assert ts["e2e_count"] == {"DEEPSEEK": 42, "GENERIC": 38, "TWO_STEP": 42}, ts["e2e_count"]
    rows = [("Designer", sc["ba_llm"], e2["rate"]["DEEPSEEK"], C_HOST, None, None),
            ("Two-step", ts["scale12"]["ba_twostep"], 42 / 42, "LLMREF", None, None),
            ("LLM match", lm["ba_llm_match"], 38 / 42, "LLMREF", None, None)] + \
           [(lab, V[m]["ba12"]["mean"], V[m]["e2e_v3"]["mean"], C_OPEN, rng(m, "ba12"), rng(m, "e2e_v3")) for lab, m in (("32B", "r1_32b"), ("14B", "r1_14b"))] + \
           [(nice[b], sc["ba_base"][b], e2["rate"][b], C_BASE, None, None) for b in base]
    return rows, C_HOST


def cl_cells():
    """Signed utility deviations per method for panel (c), with the gates of make_fig_closedloop_designer_v2.main."""
    U = C2.load(); D = C2.cells(U); ref = json.load(open(CL.K / "result_v1.json"))
    for m in CL.METHODS:
        md = st.mean(abs(x) for x in D[m]); sev = sum(x < -CL.SEVERE for x in D[m])
        assert abs(md - ref["mean_dev"][m]) < 1e-9 and sev == ref["severe_loss"][m], (m, md, ref["mean_dev"][m], sev, ref["severe_loss"][m])
    assert [len(D[m]) for m in ("LLM", "NAME", "DIST", "NONE")] == [32, 32, 32, 24]
    return D


def main():
    rows, C_HOST = bar_rows(); D = cl_cells()
    S.apply()
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(S.TWO_COL_IN, 2.1))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.5])
    ax_a = fig.add_subplot(gs[0]); ax_b = fig.add_subplot(gs[1], sharey=ax_a); ax_c = fig.add_subplot(gs[2])
    y = [i if i < 5 else i + 0.5 for i in range(len(rows))]
    for ax, j, title, xlab in ((ax_a, 1, "(a) 12 client stacks", S.up("Balanced accuracy")),
                               (ax_b, 2, "(b) Real software, end to end", S.up("Share of cells correct"))):
        for yi, r in zip(y, rows):
            if r[3] == "LLMREF":
                ax.barh(yi, r[j], height=0.64, color="white", edgecolor=C_HOST, linewidth=0.9)
            else:
                ax.barh(yi, r[j], height=0.64, color=r[3], edgecolor="none")
            lo_hi = r[3 + j]; xr = r[j]
            if lo_hi is not None:
                ax.errorbar(r[j], yi, xerr=[[r[j] - lo_hi[0]], [lo_hi[1] - r[j]]], fmt="none", ecolor="0.25", elinewidth=0.6, capsize=1.5, zorder=3); xr = lo_hi[1]
            ax.annotate(f"{r[j]:.2f}", (xr, yi), xytext=(2.5, 0), textcoords="offset points", ha="left", va="center", fontsize=S.VALUE_FS, color="0.2", gid="value")
        ax.set_xlim(0, 1.25); ax.set_xticks([0, 0.5, 1.0]); ax.set_xticklabels(["0", "0.5", "1"])
        ax.grid(False); ax.set_xlabel(xlab); S.panel_title(ax, title)
        ax.tick_params(axis="y", length=0); ax.spines["left"].set_visible(False)
    ax_a.set_yticks(y); ax_a.set_yticklabels([r[0] for r in rows]); ax_a.invert_yaxis()
    ax_b.tick_params(axis="y", labelleft=False)
    ax = ax_c
    order = [("LLM", "LLM\ndesigner", True), ("NAME", "Name\nmatch", False), ("DIST", "Distrib.\nmatch", False), ("NONE", "No\nadaptation", False)]
    ax.axhline(0, color="0.2", lw=0.7, zorder=1)
    ax.axhline(-CL.SEVERE, color="0.2", ls=(0, (3, 2)), lw=0.7, zorder=1)
    lo = min(min(D[m]) for m, _, _ in order); hi = max(max(D[m]) for m, _, _ in order)
    ax.text(-0.5, -CL.SEVERE - 1.0, "10-point loss", ha="left", va="top", fontsize=8)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([f"{lab}\n|Δ| {st.mean(abs(x) for x in D[m]):.2f}\n{sum(x < -CL.SEVERE for x in D[m])} losses" for m, lab, _ in order])
    ax.tick_params(axis="x", length=0)
    y0, y1 = np.floor(lo / 5) * 5 - 1, np.ceil(hi / 5) * 5 + 1
    ax.set_xlim(-0.55, 3.55); ax.set_ylim(y0, y1)
    ax.set_yticks([t for t in range(-50, 51, 10) if y0 <= t <= y1])
    ax.set_yticklabels([str(t).replace("-", "−") for t in ax.get_yticks().astype(int)])
    ax.set_ylabel("Utility minus correct\ninterface (points)")
    S.panel_title(ax, "(c) Closed loop, synthetic schemas")
    fig.canvas.draw(); bb = ax.get_window_extent(); to_pt = 72.0 / fig.dpi
    ppy = bb.height * to_pt / (y1 - y0); ppx = bb.width * to_pt / (3.55 - (-0.55))
    SZ = 8.0; d_pt = np.sqrt(SZ) + 0.8 + 0.2; W = 0.42
    dot_ours = dict(S.DOT_OURS, facecolor=C_HOST)
    for i, (m, lab, ours) in enumerate(order):
        d = np.asarray(D[m]); k = 1.0
        off = np.asarray(S.swarm_offsets(list(d * ppy), d_pt)) / ppx
        if np.abs(off).max() > W:
            lo_k, hi_k = 0.4, 1.0
            # Bisect a spacing factor so the swarm fits within W; dots may then overlap by up to 40% of a diameter.
            for _ in range(30):
                k = (lo_k + hi_k) / 2; o = np.asarray(S.swarm_offsets(list(d * ppy), d_pt * k)) / ppx
                lo_k, hi_k = (k, hi_k) if np.abs(o).max() <= W else (lo_k, k)
            k = lo_k; off = np.asarray(S.swarm_offsets(list(d * ppy), d_pt * k)) / ppx
        assert np.abs(off).max() <= W + 1e-9 and k >= 0.6, (m, np.abs(off).max(), k)
        ax.scatter(i + off, d, s=SZ, marker="o", zorder=3, **(dot_ours if ours else S.DOT_REF))
        mu = float(np.mean(d))
        ax.plot([i - 0.34, i + 0.34], [mu, mu], color="0.25", lw=1.2, solid_capstyle="butt", zorder=2)
    S.save_checked(fig, str(OUT), cols=2)
    print("Written", OUT, [(r[0], round(r[1], 3), round(r[2], 3)) for r in rows],
          {m: (round(st.mean(abs(x) for x in D[m]), 2), sum(x < -CL.SEVERE for x in D[m]), len(D[m])) for m in CL.METHODS})


if __name__ == "__main__":
    main()
