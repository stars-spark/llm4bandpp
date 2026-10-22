#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fig. 3 of the paper (fig_designer_three.pdf), redrawn from the CSV files in data/ alone.
The drawing is that of scripts/paper/make_fig_designer_v6.py; only the data source differs (the CSV files were written by
scripts/paper/export_figure_data_v1.py from the same functions). Text is typeset by pdflatex through matplotlib's PGF backend
with helvet and sansmath, as in Figs. 1 and 2, so a TeX installation with those packages is needed.
Usage: python3 plot_fig3.py [OUTPUT.pdf]   (default: fig_designer_three.pdf next to this script)
"""
import csv, json, os, statistics as st, subprocess, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import ieee_style as S   # noqa: E402  copy of scripts/paper/ieee_style.py
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "fig_designer_three.pdf"
SEVERE = json.loads((HERE / "data/constants.json").read_text())["severe_loss_points"]
TEAL = S.OURS["fc"]                 # the designer
TEAL_LT = "#a9d7d8"                 # the same hosted LLM used in two steps or as a generic matcher
GRAY = os.environ.get("FIG3_BASE", "#c6c6c6")
GRAY_DOT = os.environ.get("FIG3_BASE_DOT", "#9b9b9b")
HATCH = {"h1": ("#e8f3f3", "////", "#7fb3b5"), "h2": ("white", "////", "#8fbfc1"), "h3": ("#cfe3e4", "////", "white")}
HSTYLE = HATCH.get(os.environ.get("FIG3_HATCH", "h1"))   # non-LLM matchers: face colour, hatch, hatch colour
PGF_RC = {"pgf.texsystem": "pdflatex", "pgf.rcfonts": False,
          "pgf.preamble": r"\usepackage[T1]{fontenc}\usepackage{helvet}\renewcommand{\familydefault}{\sfdefault}\usepackage{sansmath}\sansmath"}


def load():
    """Bars of panels (a) and (b) in plotting order, and the utility deviation per cell for panel (c)."""
    num = lambda s: float(s) if s != "" else None
    rows = []
    for r in csv.DictReader(open(HERE / "data/panel_ab_bars.csv")):
        rng = lambda a, b: (num(r[a]), num(r[b])) if r[a] != "" else None
        rows.append(dict(name=r["method"], kind=r["kind"], v={1: num(r["balanced_accuracy"]), 2: num(r["share_cells_correct"])},
                         rng={1: rng("ba_min", "ba_max"), 2: rng("share_min", "share_max")}))
    cells = {}
    for r in csv.DictReader(open(HERE / "data/panel_c_cells.csv")): cells.setdefault(r["mapping"], []).append(float(r["utility_vs_true_mapping"]))
    return rows, cells


def main():
    rows, D = load()
    S.apply()
    import matplotlib.pyplot as plt
    plt.rcParams["hatch.linewidth"] = 0.5
    fig = plt.figure(figsize=(S.TWO_COL_IN, float(os.environ.get("FIG3_H", "2.00"))))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.08, 0.86, 1.5])
    ax_a = fig.add_subplot(gs[0]); ax_b = fig.add_subplot(gs[1], sharey=ax_a); ax_c = fig.add_subplot(gs[2])
    y = [float(i) for i in range(len(rows))]
    # ---- (a) balanced accuracy and (b) share of real-software cells correct ----
    for ax, j, title, xlab in ((ax_a, 1, "(a) 12 client stacks", S.up("Balanced accuracy")),
                               (ax_b, 2, "(b) Real software, end to end", S.up("Share of cells correct"))):
        for yi, r in zip(y, rows):
            k = r["kind"]; v = r["v"][j]; rng = r["rng"][j]; xr = v
            if k == "open":   # open R1 distillations: hollow bar, band over three samples
                ax.barh(yi, v, height=0.6, color="white", linewidth=0, zorder=2)
                if rng is not None:
                    ax.barh(yi, rng[1] - rng[0], left=rng[0], height=0.6, color=TEAL, alpha=0.22, linewidth=0, zorder=2.5)
                    xr = max(v, rng[1])
                ax.barh(yi, v, height=0.6, fill=False, edgecolor=TEAL, linewidth=0.8, zorder=3)
            elif k == "base" and HSTYLE:   # non-LLM matchers: pale, hatched
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
    ax_a.set_yticks(y); ax_a.set_yticklabels([r["name"] for r in rows]); ax_a.set_ylim(y[-1] + 0.6, y[0] - 0.6)
    ax_a.tick_params(axis="y", labelsize=7)
    ax_b.tick_params(axis="y", labelleft=False)
    # ---- (c) closed-loop utility relative to the true mapping, one point per cell ----
    ax = ax_c
    order = [("Designer", True), ("Name", False), ("Distribution", False), ("Unadapted", False)]
    ax.axhline(0, color="0.3", lw=0.6, zorder=1)
    ax.axhline(-SEVERE, color="0.3", ls=(0, (3, 2)), lw=0.6, zorder=1)
    lo = min(min(D[m]) for m, _ in order); hi = max(max(D[m]) for m, _ in order)
    ax.text(-0.45, -SEVERE - 1.0, "10-point loss", ha="left", va="top", fontsize=8, color="0.35")
    ax.set_xticks(range(len(order))); ax.set_xticklabels([m for m, _ in order]); ax.tick_params(axis="x", length=0)
    print("caption values: " + "; ".join(f"{m} |Δ| {st.mean(abs(x) for x in D[m]):.2f}, losses {sum(x < -SEVERE for x in D[m])}" for m, _ in order))
    y0, y1 = np.floor(lo / 5) * 5 - 1, np.ceil(hi / 5) * 5 + 1
    ax.set_xlim(-0.5, 3.5); ax.set_ylim(y0, y1)
    ax.set_yticks([t for t in range(-50, 51, 10) if y0 <= t <= y1])
    ax.set_yticklabels([str(t).replace("-", "−") for t in ax.get_yticks().astype(int)])
    ax.grid(True, axis="y", color="0.9", lw=0.4); ax.grid(False, axis="x")
    ax.set_ylabel("Utility vs. true mapping")
    S.panel_title(ax, "(c) Closed loop, synthetic schemas")
    fig.canvas.draw(); bb = ax.get_window_extent(); to_pt = 72.0 / fig.dpi
    ppy = bb.height * to_pt / (y1 - y0); ppx = bb.width * to_pt / 4.0
    SZ = 8.0; d_pt = np.sqrt(SZ) + 0.8 + 0.2; W = 0.42   # marker area, spacing in points, half-width of a swarm in x units
    for i, (m, ours) in enumerate(order):
        d = np.asarray(D[m]); k = 1.0
        off = np.asarray(S.swarm_offsets(list(d * ppy), d_pt)) / ppx
        if np.abs(off).max() > W:   # too dense: shrink the spacing until the swarm fits
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
    # checks: no text over lines or other text, no font below 7 pt, width within two columns
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
    print("Written", OUT)


if __name__ == "__main__":
    main()
