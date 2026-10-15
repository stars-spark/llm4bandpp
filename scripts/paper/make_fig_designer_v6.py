#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fig. 3 of the paper (fig_designer_three.pdf): data and gates from make_fig_designer_v4.py (bar_rows, cl_cells); only the drawing differs. Bars are told apart within one teal family:
the designer solid teal, the same hosted model used in two steps or as a generic matcher light teal, open R1 distillations hollow teal with a translucent band over three samples,
and the seven non-LLM matchers pale with fine hatching (FIG3_HATCH, default h1); values sit at bar ends. Panel (c) shows the designer's cells as filled teal points and the
comparators as hollow points. Text is typeset by pdflatex through the PGF backend with helvet and sansmath, as in Figs. 1 and 2; layout and overlap checks run under Agg first.
Redraws the v4 data and replaces the drawing of make_fig_designer_v5.py.
Usage: FIG_OUT=papers/revision-v2/figs/fig_designer_three.pdf [FIG3_H=2.00] python3 scripts/paper/make_fig_designer_v6.py (without FIG_OUT it writes to a draft path)
"""
import os, statistics as st, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/paper"))
import ieee_style as S   # noqa: E402
import make_fig_designer_v4 as V4   # noqa: E402
CL = V4.CL
OUT = Path(os.environ["FIG_OUT"]) if os.environ.get("FIG_OUT") else ROOT / "papers/revision-v2/reviews/figure-polish-20261009/fig3_v6.pdf"
TEAL = S.OURS["fc"]
TEAL_LT = "#a9d7d8"
GRAY = os.environ.get("FIG3_BASE", "#c6c6c6")
GRAY_DOT = os.environ.get("FIG3_BASE_DOT", "#9b9b9b")
HATCH = {"h1": ("#e8f3f3", "////", "#7fb3b5"), "h2": ("white", "////", "#8fbfc1"), "h3": ("#cfe3e4", "////", "white")}
HSTYLE = HATCH.get(os.environ.get("FIG3_HATCH", "h1"))
NAMES = {"Designer": "Designer", "Two-step": "Two-step", "LLM match": "LLM match", "32B": "R1-32B", "14B": "R1-14B",
         "Cupid": "Cupid", "COMA": "COMA", "TF-IDF": "TF-IDF", "mpnet": "MPNet", "bge": "BGE", "Name": "Name", "SF": "Sim. Flooding"}
PGF_RC = {"pgf.texsystem": "pdflatex", "pgf.rcfonts": False,
          "pgf.preamble": r"\usepackage[T1]{fontenc}\usepackage{helvet}\renewcommand{\familydefault}{\sfdefault}\usepackage{sansmath}\sansmath"}


def kind(r, c_host):
    return "ours" if r[3] == c_host else "same_llm" if r[3] == "LLMREF" else "base" if r[3] == "#C8C8C8" else "open"


def main():
    rows, c_host = V4.bar_rows(); D = V4.cl_cells()
    assert [r[0] for r in rows][:5] == ["Designer", "Two-step", "LLM match", "32B", "14B"] and all(r[0] in NAMES for r in rows), [r[0] for r in rows]
    S.apply()
    import matplotlib.pyplot as plt
    plt.rcParams["hatch.linewidth"] = 0.5
    fig = plt.figure(figsize=(S.TWO_COL_IN, float(os.environ.get("FIG3_H", "2.00"))))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.08, 0.86, 1.5])
    ax_a = fig.add_subplot(gs[0]); ax_b = fig.add_subplot(gs[1], sharey=ax_a); ax_c = fig.add_subplot(gs[2])
    y = [float(i) for i in range(len(rows))]
    for ax, j, title, xlab in ((ax_a, 1, "(a) 12 client stacks", S.up("Balanced accuracy")),
                               (ax_b, 2, "(b) Real software, end to end", S.up("Share of cells correct"))):
        for yi, r in zip(y, rows):
            k = kind(r, c_host); v = r[j]
            rng = r[3 + j]; xr = v
            if k == "open":
                ax.barh(yi, v, height=0.6, color="white", linewidth=0, zorder=2)
                if rng is not None:
                    ax.barh(yi, rng[1] - rng[0], left=rng[0], height=0.6, color=TEAL, alpha=0.22, linewidth=0, zorder=2.5)
                    xr = max(v, rng[1])
                ax.barh(yi, v, height=0.6, fill=False, edgecolor=TEAL, linewidth=0.8, zorder=3)
            else:
                if k == "base" and HSTYLE:
                    fc, hp, hc = HSTYLE
                    ax.barh(yi, v, height=0.6, color=fc, hatch=hp, hatchcolor=hc, edgecolor=(hc if hc != "white" else fc), linewidth=0.5, zorder=2)
                else:
                    ax.barh(yi, v, height=0.6, color={"ours": TEAL, "same_llm": TEAL_LT, "base": GRAY}[k], linewidth=0, zorder=2)
            ax.annotate(f"{v:.2f}", (xr, yi), xytext=(2.5, 0), textcoords="offset points", ha="left", va="center",
                        fontsize=S.VALUE_FS, color="0.15", gid="value")
        ax.set_xlim(0, 1.17); ax.set_xticks([0, 0.5, 1.0]); ax.set_xticklabels(["0", "0.5", "1"]); ax.spines["bottom"].set_bounds(0, 1)
        ax.grid(True, axis="x", color="0.9", lw=0.4); ax.grid(False, axis="y")
        ax.set_xlabel(xlab); S.panel_title(ax, title)
        ax.tick_params(axis="y", length=0); ax.spines["left"].set_visible(False)
    ax_a.set_yticks(y); ax_a.set_yticklabels([NAMES[r[0]] for r in rows]); ax_a.set_ylim(y[-1] + 0.6, y[0] - 0.6)
    ax_a.tick_params(axis="y", labelsize=7)
    ax_b.tick_params(axis="y", labelleft=False)
    # ---- (c) ----
    ax = ax_c
    order = [("LLM", "Designer", True), ("NAME", "Name", False), ("DIST", "Distribution", False), ("NONE", "Unadapted", False)]
    ax.axhline(0, color="0.3", lw=0.6, zorder=1)
    ax.axhline(-CL.SEVERE, color="0.3", ls=(0, (3, 2)), lw=0.6, zorder=1)
    lo = min(min(D[m]) for m, _, _ in order); hi = max(max(D[m]) for m, _, _ in order)
    ax.text(-0.45, -CL.SEVERE - 1.0, "10-point loss", ha="left", va="top", fontsize=8, color="0.35")
    ax.set_xticks(range(len(order))); ax.set_xticklabels([lab for m, lab, _ in order]); ax.tick_params(axis="x", length=0)
    print("caption values: " + "; ".join(f"{lab} |Δ| {st.mean(abs(x) for x in D[m]):.2f}, losses {sum(x < -CL.SEVERE for x in D[m])}" for m, lab, _ in order))
    y0, y1 = np.floor(lo / 5) * 5 - 1, np.ceil(hi / 5) * 5 + 1
    ax.set_xlim(-0.5, 3.5); ax.set_ylim(y0, y1)
    ax.set_yticks([t for t in range(-50, 51, 10) if y0 <= t <= y1])
    ax.set_yticklabels([str(t).replace("-", "−") for t in ax.get_yticks().astype(int)])
    ax.grid(True, axis="y", color="0.9", lw=0.4); ax.grid(False, axis="x")
    ax.set_ylabel("Utility vs. true mapping")
    S.panel_title(ax, "(c) Closed loop, synthetic schemas")
    fig.canvas.draw(); bb = ax.get_window_extent(); to_pt = 72.0 / fig.dpi
    ppy = bb.height * to_pt / (y1 - y0); ppx = bb.width * to_pt / 4.0
    SZ = 8.0; d_pt = np.sqrt(SZ) + 0.8 + 0.2; W = 0.42
    for i, (m, lab, ours) in enumerate(order):
        d = np.asarray(D[m]); k = 1.0
        off = np.asarray(S.swarm_offsets(list(d * ppy), d_pt)) / ppx
        if np.abs(off).max() > W:
            lo_k, hi_k = 0.4, 1.0
            for _ in range(30):
                k = (lo_k + hi_k) / 2; o = np.asarray(S.swarm_offsets(list(d * ppy), d_pt * k)) / ppx
                lo_k, hi_k = (k, hi_k) if np.abs(o).max() <= W else (lo_k, k)
            k = lo_k; off = np.asarray(S.swarm_offsets(list(d * ppy), d_pt * k)) / ppx
        assert np.abs(off).max() <= W + 1e-9 and k >= 0.6, (m, np.abs(off).max(), k)
        if ours or not HSTYLE:
            ax.scatter(i + off, d, s=SZ, marker="o", zorder=3, facecolor=TEAL if ours else GRAY_DOT, edgecolor="white", linewidth=0.3)
        else:
            ax.scatter(i + off, d, s=SZ, marker="o", zorder=3, facecolor="white", edgecolor="#5f9fa1", linewidth=0.6)
    hits = S.check_overlap(fig, verbose=True, ignore_ticks=False); small = S.check_font_sizes(fig, min_pt=7.0)
    assert not small, small[:6]
    assert not hits, f"{len(hits)} overlaps"
    want = S.TWO_COL_IN * 72; got = fig.get_size_inches()[0] * 72
    assert got <= want + S.TOL_PT, (got, want)
    plt.rcParams.update(PGF_RC)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUT), backend="pgf")
    fonts = subprocess.run(["pdffonts", str(OUT)], capture_output=True, text=True).stdout.splitlines()[2:]
    assert fonts and not any("Type 3" in f for f in fonts), fonts
    assert all(("NimbusSan" in f) or ("CMSY" in f) or ("CMMI" in f) or ("CMR" in f) for f in fonts), fonts
    print("Written", OUT, "fonts", sorted({f.split()[0].split("+")[-1] for f in fonts}))


if __name__ == "__main__":
    main()
