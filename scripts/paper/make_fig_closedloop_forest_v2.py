#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Forest plot of the closed-loop VMAF differences of LLM4band++ against each reference: the 14 VMAF rows of make_tables_v2.closedloop_rows, grouped by reference and resolution
(GROUPS), each row used once; registered rows filled, reported-only rows hollow, zero line light grey, -6 margin dashed; text typeset through the PGF backend in Helvetica.
Version 2 of the forest() drawing in make_fig_closedloop_v1.py (fig_closedloop_forest.pdf); same readings, new drawing. The paper shows these readings as Table V:
make_tables_v2.table_closedloop_v2 imports GROUPS and rows_v2 from this module.
Usage: FIG_OUT=out.pdf python3 scripts/paper/make_fig_closedloop_forest_v2.py (without FIG_OUT it writes to a draft path)
"""
import os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/paper"))
import ieee_style as S   # noqa: E402
import make_tables_v2 as T   # noqa: E402
OUT = Path(os.environ["FIG_OUT"]) if os.environ.get("FIG_OUT") else ROOT / "papers/revision-v2/reviews/figure-polish-20261009/fig4_v2.pdf"
MARGIN = -6.0
TEAL = S.OURS["fc"]; TEAL_REF = "#5f9fa1"; LINE_REF = "#9cc7c8"; MARGIN_C = "#7fb3b5"
PGF_RC = {"pgf.texsystem": "pdflatex", "pgf.rcfonts": False,
          "pgf.preamble": r"\usepackage[T1]{fontenc}\usepackage{helvet}\renewcommand{\familydefault}{\sfdefault}\usepackage{sansmath}\sansmath"}
GROUPS = [("vs. Python GCC, 720p", [("720p, first batch", "First batch", False), ("second batch", "Second batch", False), ("seeds 0 and 2", "Seeds 0 and 2", False),
                                    ("cellular, 7 windows", "Cellular, 7 windows", False), ("High bandwidth", "High bandwidth", False), ("Random loss", "Random loss", False)]),
          ("vs. Python GCC, 320$\\times$240", [("320x240 Johnny", "Johnny", False), ("Mobcal", "Mobcal", False), ("Parkrun", "Parkrun", False)]),
          ("vs. learned estimators, 720p", [("Schaferct-R", "Schaferct-R", False), ("high bandwidth", "high bandwidth", True), ("Supervised MLP", "Supervised MLP", False),
                                            ("Schaferct-R, no envelope", "Schaferct-R, no envelope", False), ("high bandwidth", "high bandwidth", True)])]


# Regroup the 14 VMAF rows of closedloop_rows into GROUPS, using each source row exactly once; returns (rows, source rows).
def rows_v2(G):
    src = [r for r in T.closedloop_rows(G) if isinstance(r, dict) and r["unit"] == "VMAF"]
    assert len(src) == 14, len(src)
    pool = list(src); out = []
    for head, items in GROUPS:
        out.append(("head", head))
        for old, new, ind in items:
            k = next(i for i, r in enumerate(pool) if r["label"] == old)
            r = pool.pop(k); out.append(("row", dict(r, label=new, indent=ind)))
    assert not pool, [r["label"] for r in pool]
    return out, src


def main():
    G = T.reg(); rows, src = rows_v2(G)
    S.apply()
    import matplotlib.pyplot as plt
    plt.rcParams["font.size"] = 7.5
    pitch, gap = 0.112, 0.45
    ys, cur = [], 0.0
    for i, (kind, _) in enumerate(rows):
        if kind == "head" and i > 0: cur += gap
        ys.append(cur); cur += 1.0
    n = cur
    top_in, bot_in = 0.04, 0.34
    W = S.ONE_COL_IN; H = top_in + bot_in + pitch * n
    fig = plt.figure(figsize=(W, H), layout=None)
    cols = [(0.0, 1.27), (1.27, 1.15), (2.46, 0.84), (3.30, W - 3.30)]
    axs = [fig.add_axes([x / W, bot_in / H, w / W, pitch * n / H]) for x, w in cols]
    lab, ax, num, stc = axs
    for a in axs: a.patch.set_visible(False)
    for a in (lab, num, stc):
        a.set_xlim(0, 1); a.set_ylim(n - 0.5, -0.5); a.set_xticks([]); a.set_yticks([]); a.axis("off")
    ax.set_ylim(n - 0.5, -0.5); ax.set_xlim(-8, 11)
    spans, start = [], None
    for (kind, _), y in zip(rows, ys):
        if kind == "head":
            if start is not None: spans.append((start, prev))
            start = None
        else:
            start = y if start is None else start; prev = y
    spans.append((start, prev))
    for y0, y1 in spans:
        for xv in (5, 10, -5): ax.plot([xv, xv], [y0 - 0.5, y1 + 0.5], color="0.92", lw=0.4, zorder=0)
        ax.plot([0, 0], [y0 - 0.5, y1 + 0.5], color="0.6", lw=0.5, zorder=1)
        ax.plot([MARGIN, MARGIN], [y0 - 0.5, y1 + 0.5], color=MARGIN_C, lw=0.7, ls=(0, (3, 2)), zorder=1)
    for (kind, r), y in zip(rows, ys):
        if kind == "head":
            lab.text(0.0, y, r, ha="left", va="center", fontsize=8, fontweight="bold", clip_on=False); continue
        lab.text(0.1 if r["indent"] else 0.0, y, r["label"], ha="left", va="center", fontsize=7.5)
        reg = r["st"] != "--"; lo, hi = r["ci"]
        ax.plot([lo, hi], [y, y], color=TEAL if reg else LINE_REF, lw=1.0, solid_capstyle="round", zorder=3)
        if reg: ax.scatter([r["D"]], [y], s=13, marker="o", zorder=4, facecolor=TEAL, edgecolor="white", linewidth=0.4)
        else: ax.scatter([r["D"]], [y], s=12, marker="o", zorder=4, facecolor="white", edgecolor=TEAL_REF, linewidth=0.7)
        num.text(1.0, y, f"{r['D']:.1f} [{lo:.1f}, {hi:.1f}]".replace("-", "−"), ha="right", va="center", fontsize=7.5, color="0.15", gid="value")
        stc.text(0.5, y, r["st"].replace("--", "–"), ha="center", va="center", fontsize=7.5, color="0.15")
    ax.set_xticks([-5, 0, 5, 10]); ax.set_xticklabels(["−5", "0", "5", "10"]); ax.set_yticks([])
    ax.grid(False); ax.spines["left"].set_visible(False); ax.tick_params(axis="x", labelsize=7.5)
    ax.set_xlabel("VMAF, ours minus reference", fontsize=7.5)
    fig.canvas.draw(); rend = fig.canvas.get_renderer(); xr = lab.get_window_extent(rend).x1
    wide = [t.get_text() for t in lab.texts if t.get_fontweight() != "bold" and t.get_window_extent(rend).x1 > xr - 2]
    assert not wide, ("row labels extend into the plot column", wide)
    nr = num.get_window_extent(rend).x0
    assert all(t.get_window_extent(rend).x0 >= nr - 1 for t in num.texts if t.get_gid() == "value"), "values extend beyond the value column"
    hits = S.check_overlap(fig, verbose=True, ignore_ticks=False); small = S.check_font_sizes(fig, min_pt=7.0)
    assert not small, small[:6]
    assert not hits, f"{len(hits)} overlaps"
    assert fig.get_size_inches()[0] * 72 <= S.ONE_COL_IN * 72 + S.TOL_PT
    used = [r for k, r in rows if k == "row"]
    assert sorted((round(r["D"], 6), tuple(round(c, 6) for c in r["ci"]), r["st"]) for r in used) == sorted((round(r["D"], 6), tuple(round(c, 6) for c in r["ci"]), r["st"]) for r in src)
    plt.rcParams.update(PGF_RC); OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUT), backend="pgf")
    fonts = subprocess.run(["pdffonts", str(OUT)], capture_output=True, text=True).stdout.splitlines()[2:]
    assert fonts and not any("Type 3" in f for f in fonts), fonts
    print("Written", OUT, f"{W*72:.1f} x {H*72:.1f} pt", "fonts", sorted({f.split()[0].split("+")[-1] for f in fonts}))


if __name__ == "__main__":
    main()
