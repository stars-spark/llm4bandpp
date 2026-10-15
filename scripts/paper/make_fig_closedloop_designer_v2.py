#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone closed-loop designer figure fig_closedloop_designer.pdf (not in the paper): per-cell utility of obsschema-closedloop-v2, 4 held-out schemas x 8 windows (32 cells;
24 for no adaptation); each dot is a signed deviation U(method) - U(true mapping, same window), solid line at 0, dashed line at -10 (severe loss).
Runs are read as judge() in scripts/alphartc/deploy/obsschema_cl2_v1.py reads them, and the mean deviation and severe-loss counts must equal result_v1.json, otherwise no figure is written.
make_fig_designer_v4.py reuses its load() and cells() for Fig. 3(c); DESIGNER.md uses it to recompute the closed-loop row with the challenge baseline downstream of Table IV.
Usage: python3 scripts/paper/make_fig_closedloop_designer_v2.py
"""
import json, statistics as st, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/paper")); sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy"))
import ieee_style as S   # noqa: E402
import obsschema_cl2_v1 as CL   # noqa: E402
OUT = ROOT / "papers/revision-v2/figs/fig_closedloop_designer.pdf"


def load():
    U = {}
    for dd in CL.K.glob("sd_*__*"):
        w, c = dd.name.split("__", 1); js = dd / f"{CL.ARM}__{w}__d0__r1.json"
        if js.is_file() and not list(dd.glob("invalid_*")):
            U[(w, c)] = json.load(open(js))["network"]["utility"]
    return U


def cells(U):
    D = {m: [] for m in CL.METHODS}
    for s in CL.SCHEMAS:
        for w in CL.WINS:
            # CLEAN is the run with the true mapping in the same window, the reference of every cell.
            if (w, "CLEAN") not in U: continue
            for m in CL.METHODS:
                if (w, f"{s}__{m}") in U: D[m].append(U[(w, f"{s}__{m}")] - U[(w, "CLEAN")])
    return D


def main():
    U = load(); D = cells(U); ref = json.load(open(CL.K / "result_v1.json"))
    for m in CL.METHODS:
        md = st.mean(abs(x) for x in D[m]); sev = sum(x < -CL.SEVERE for x in D[m])
        assert abs(md - ref["mean_dev"][m]) < 1e-9 and sev == ref["severe_loss"][m], (m, md, ref["mean_dev"][m], sev, ref["severe_loss"][m])
    assert [len(D[m]) for m in ("LLM", "NAME", "DIST", "NONE")] == [32, 32, 32, 24]
    order = [("LLM", "LLM\ndesigner", True), ("NAME", "Name\nmatch", False), ("DIST", "Distribution\nmatch", False), ("NONE", "No\nadaptation", False)]
    S.apply(); fig, ax = S.figure(cols=1, height_in=1.68)
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
    S.panel_title(ax, "All schema and window cells")
    S.titles_to_figure_left(fig)
    fig.canvas.draw(); bb = ax.get_window_extent(); to_pt = 72.0 / fig.dpi
    ppy = bb.height * to_pt / (y1 - y0); ppx = bb.width * to_pt / (3.55 - (-0.55))
    SZ = 8.0; d_pt = np.sqrt(SZ) + 0.8 + 0.2
    W = 0.42
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
        print(f"  {m}: half-width {np.abs(off).max():.2f}, center spacing coefficient {k:.2f}")
        ax.scatter(i + off, d, s=SZ, marker="o", zorder=3, **(S.DOT_OURS if ours else S.DOT_REF))
        mu = float(np.mean(d))
        ax.plot([i - 0.34, i + 0.34], [mu, mu], color="0.25", lw=1.2, solid_capstyle="butt", zorder=2)
    S.save_checked(fig, str(OUT), cols=1)
    print("Written", OUT, {m: (round(st.mean(abs(x) for x in D[m]), 2), round(st.mean(D[m]), 2), sum(x < -CL.SEVERE for x in D[m]), sum(x > CL.SEVERE for x in D[m]), len(D[m]), round(min(D[m]), 1), round(max(D[m]), 1)) for m in CL.METHODS})


if __name__ == "__main__":
    main()
