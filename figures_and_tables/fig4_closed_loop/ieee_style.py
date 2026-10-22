#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared matplotlib style and save checks for the IEEE figures; every figure script imports it instead of setting its own rcParams.
Widths are in TeX points: one column 252 pt, two columns 516 pt (IEEEtran column and text width). In-figure text 8 pt, value labels 7.5 pt.
Fonts are TrueType (pdf.fonttype 42): IEEE PDF eXpress rejects the Type 3 fonts matplotlib writes by default.
No tight bounding box: the width is fixed by figsize and asserted on save, so LaTeX never rescales a figure and shrinks its text.
save_checked() also refuses to write a figure with overlapping text, lines or legends, or with text below the size limits.
Usage: import ieee_style as S; S.apply(); fig, ax = S.figure(cols=1); ...; S.save_checked(fig, path, cols=1). Run directly for the self-tests.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ONE_COL_IN = 252.0 / 72.27
TWO_COL_IN = 516.0 / 72.27
PT_PER_IN = 72.27
TOL_PT = 1.5

# Liberation Sans (TrueType, Helvetica metrics) for text and math, so no Type 3 or serif glyphs reach the PDF.
RC = {
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "hatch.linewidth": 0.5, "hatch.color": "black",
    "font.family": "sans-serif",
    "font.sans-serif": ["Liberation Sans", "Arial", "DejaVu Sans"],
    "mathtext.fontset": "custom", "mathtext.rm": "Liberation Sans", "mathtext.it": "Liberation Sans:italic",
    "mathtext.bf": "Liberation Sans:bold", "mathtext.sf": "Liberation Sans",
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
    "legend.fontsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.titlelocation": "left", "axes.titlepad": 3.0,
    "figure.dpi": 200,
    "savefig.bbox": None,
    "figure.constrained_layout.use": True,
    "figure.constrained_layout.h_pad": 0.02, "figure.constrained_layout.w_pad": 0.02,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y",
    "grid.alpha": 1.0, "grid.linewidth": 0.4, "grid.color": "0.85",
    "axes.axisbelow": True,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "xtick.minor.width": 0.4, "ytick.minor.width": 0.4,
    "xtick.major.pad": 2.0, "ytick.major.pad": 2.0,
    "axes.labelpad": 2.0,
    "legend.frameon": False,
    "legend.handlelength": 2.0,
    "legend.columnspacing": 1.2,
    "legend.handletextpad": 0.5,
    "lines.linewidth": 1.2,
    "lines.markeredgewidth": 0.6,
    "patch.linewidth": 0.6,
}
BAR_EDGE_LW = 0.6
HATCH_LW = RC["hatch.linewidth"]
VALUE_FS = 7.5

SERIES = [
    {"color": "#1f6fb4", "marker": "o", "ls": "-"},
    {"color": "#c0392b", "marker": "s", "ls": "--"},
    {"color": "#1e8449", "marker": "^", "ls": "-."},
    {"color": "#8e44ad", "marker": "D", "ls": ":"},
    {"color": "#000000", "marker": "v", "ls": (0, (3, 1, 1, 1, 1, 1))},
]


def legend_above_figure(fig, ax, ncol=3):
    """Place one legend above the whole figure, spanning its width, with constrained_layout's outside placement."""
    h, l = ax.get_legend_handles_labels()
    return fig.legend(h, l, loc="outside upper center", ncol=ncol, frameon=False)


def legend_above(ax, ncol=3, y=1.02):
    """Frameless horizontal legend just above the axes."""
    return ax.legend(loc="lower left", bbox_to_anchor=(0, y, 1, 0.2),
                     mode="expand", ncol=ncol, borderaxespad=0)


def apply():
    plt.rcParams.update(RC)


def figure(cols=1, height_in=2.4, nrows=1, ncols=1, **kw):
    """Create a figure one or two page columns wide; cols is the column count, nrows and ncols the subplot grid."""
    w = ONE_COL_IN if cols == 1 else TWO_COL_IN
    return plt.subplots(nrows, ncols, figsize=(w, height_in), **kw)


def save(fig, path, cols=1):
    """Assert the figure width against the column width, then save; an over-wide figure is not written."""
    want = (ONE_COL_IN if cols == 1 else TWO_COL_IN) * PT_PER_IN
    got = fig.get_size_inches()[0] * PT_PER_IN
    if got > want + TOL_PT:
        plt.close(fig)
        raise AssertionError(f"{path} actual width {got:.1f} pt exceeds {want:.1f} pt of column {cols}, not saved")
    fig.savefig(path)
    plt.close(fig)
    return path


def selftest():
    apply()
    assert plt.rcParams["pdf.fonttype"] == 42
    assert abs(ONE_COL_IN * PT_PER_IN - 252.0) < 1e-9
    assert abs(TWO_COL_IN * PT_PER_IN - 516.0) < 1e-9
    assert len(SERIES) >= 4 and all(set(d) == {"color", "marker", "ls"} for d in SERIES)
    assert len({d["marker"] for d in SERIES}) == len(SERIES), "markers must be pairwise distinct, otherwise grayscale printing cannot distinguish them"
    assert len({d["color"] for d in SERIES}) == len(SERIES), "colors must be pairwise different"
    f, a = figure(1, 2.0)
    assert abs(f.get_size_inches()[0] - ONE_COL_IN) < 1e-9
    plt.close(f)
    f4, axs = figure(cols=2, height_in=2.0, ncols=2)
    assert abs(f4.get_size_inches()[0] - TWO_COL_IN) < 1e-9 and len(axs) == 2
    plt.close(f4)
    import tempfile, os
    f2, _ = figure(2, 2.0)
    tmp = os.path.join(tempfile.gettempdir(), "_ieee_style_selftest.pdf")
    try:
        save(f2, tmp, cols=1)
        raise SystemExit("A two-column figure saved as single-column should have been blocked, but it passed")
    except AssertionError as e:
        assert "exceed" in str(e) and "not saved" in str(e), e
    assert not os.path.exists(tmp), "A blocked figure should not leave a file behind"
    f3, _ = figure(2, 2.0)
    save(f3, tmp, cols=2)
    assert os.path.exists(tmp)
    os.remove(tmp)
    x = list(range(10)); y = list(x)
    f5, a5 = figure(1, 2.0); a5.plot(x, y)
    a5.annotate("label on the line", (4.5, 4.5), ha="center", va="center")
    assert check_overlap(f5, verbose=False), "a label on the boundary should have been detected"
    plt.close(f5)
    f6, a6 = figure(1, 2.0); a6.plot(x, y, label="s"); legend_inside(a6, loc="center")
    assert check_overlap(f6, verbose=False), "Legend covering data should have been detected"
    plt.close(f6)
    f7, a7 = figure(1, 2.2); a7.plot(x, y, label="s"); headroom(a7); legend_above(a7, ncol=1)
    assert not check_overlap(f7, verbose=False), "A normally laid out figure should not be falsely reported"
    plt.close(f7)
    f8, a8 = figure(1, 2.0); a8.text(0.5, 0.5, "tiny", fontsize=6.5)
    assert check_font_sizes(f8), "6.5-point text should have been detected"
    plt.close(f8)
    f9, a9 = figure(1, 2.0); a9.bar([0], [1]); label_values(a9, [0], [1])
    assert not check_font_sizes(f9), "7.5-point numeric labels should not be falsely reported"
    plt.close(f9)
    assert plt.rcParams["font.family"] == ["sans-serif"] and plt.rcParams["axes.spines.top"] is False
    print("ieee_style self-test passed (11 cases)")



# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

FILLS = [
    {"fc": "#94d2bd", "hatch": "/////"},
    {"fc": "#0a9396", "hatch": "\\\\\\\\\\"},
    {"fc": "#005f73", "hatch": "....."},
    {"fc": "#5f0f40", "hatch": "xxx"},
]
OURS = {"fc": __import__("os").environ.get("IS_OURS_FC", "#34a0a4"), "hatch": ""}
DOT_OURS = {"facecolor": OURS["fc"], "edgecolor": "white", "linewidth": 0.4}
DOT_REF = {"facecolor": "none", "edgecolor": "0.45", "linewidth": 0.8}
BAR_LIGHT = {"edgecolor": "0.3", "linewidth": 0.35, "hatchcolor": "0.45"}


def swarm_offsets(y_pt, d_pt):
    """Deterministic beeswarm: horizontal offsets in points that keep centres at least d_pt apart, placing points by y_pt and as close to the centre line as possible."""
    import math
    order = sorted(range(len(y_pt)), key=lambda k: (y_pt[k], k)); placed = []; out = [0.0] * len(y_pt)
    for k in order:
        y = y_pt[k]; near = [(px, py) for px, py in placed if abs(py - y) < d_pt]
        cands = [0.0]
        for px, py in near:
            w = math.sqrt(max(d_pt * d_pt - (py - y) ** 2, 0.0)); cands += [px + w, px - w]
        ok = [c for c in cands if all((c - px) ** 2 + (y - py) ** 2 >= d_pt * d_pt - 1e-6 for px, py in near)]
        # Closest free position to the centre line; ties go to the positive side.
        x = min(ok, key=lambda c: (abs(c), -c)); placed.append((x, y)); out[k] = x
    return out


def knockout_selftest():
    """Self-test of the knockout rule: opaque text over a reference line passes; the same text without a box, or an opaque box over a data line, is reported."""
    apply()
    f, ax = figure(1, 1.2); ax.set_xlim(-1, 1); ax.set_ylim(0, 1)
    ax.axvline(0, color="0.5", lw=0.7, zorder=1, gid="ref")
    ax.text(0, 0.5, "+2.2 [-4.0, +8.4]", ha="center", va="center", fontsize=8, zorder=5, bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))
    assert not [h for h in check_overlap(f, verbose=False) if h[0] == "text over line"], "an intended white-box knockout was falsely reported"
    plt.close(f)
    f, ax = figure(1, 1.2); ax.set_xlim(-1, 1); ax.set_ylim(0, 1)
    ax.axvline(0, color="0.5", lw=0.7, zorder=1, gid="ref")
    ax.text(0, 0.5, "+2.2 [-4.0, +8.4]", ha="center", va="center", fontsize=8, zorder=5)
    assert [h for h in check_overlap(f, verbose=False) if h[0] == "text over line"], "The line touching the edge on a white background was not caught"
    plt.close(f)
    f, ax = figure(1, 1.2); ax.set_xlim(-1, 1); ax.set_ylim(0, 1)
    ax.plot([-0.8, 0.8], [0.5, 0.5], color="0.2", lw=1.2, zorder=2)
    ax.text(0, 0.5, "+0.1 [-4.8, +5.0]", ha="center", va="center", fontsize=8, zorder=5, bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))
    assert [h for h in check_overlap(f, verbose=False) if h[0] == "text over line"], "an opaque text box over a data line was not reported"
    plt.close(f)
    f, ax = figure(1, 1.2); ax.set_xlim(-1, 1); ax.set_ylim(0, 1)
    t_ = ax.text(0, 0.5, "+0.1 [-4.8, +5.0]", ha="center", va="bottom", fontsize=8, zorder=5, bbox=dict(boxstyle="square,pad=0.4", fc="white", ec="none"))
    f.canvas.draw(); g = t_.get_window_extent(f.canvas.get_renderer()).transformed(ax.transData.inverted())
    yl = g.y0 - 0.25 * (0.4 * 8 / 72) * f.dpi / (ax.get_window_extent().height / 1.0)
    ax.plot([-0.8, 0.8], [yl, yl], color="0.2", lw=1.2, zorder=2)
    assert [h for h in check_overlap(f, verbose=False) if h[0] == "text over line"], "An opaque white box over a data line was not detected"
    plt.close(f)
    return True


def swarm_selftest():
    import random
    rng = random.Random(7); y = [rng.gauss(0, 6) for _ in range(60)]; d = 4.0; x = swarm_offsets(y, d)
    pts = list(zip(x, y))
    assert all((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 >= d * d - 1e-6 for i, a in enumerate(pts) for b in pts[i + 1:]), "There is some overlap in the swarm"
    assert swarm_offsets(y, d) == x, "The same input gave a different arrangement"
    bad = [0.0] * len(y)
    assert not all((0 - 0) ** 2 + (a - b) ** 2 >= d * d for i, a in enumerate(y) for b in y[i + 1:])
    return True
SWITCH = {"fc": __import__("os").environ.get("IS_SWITCH_FC", "#cce3de"), "hatch": "xxx"}
OPEN_LLM = SWITCH
BAND_BG = "#f8f9fa"
assert len({f["fc"] for f in FILLS} | {OURS["fc"]}) == len(FILLS) + 1, "bar colors must be pairwise different"


def down(label):
    """Append a down arrow to the label of a lower-is-better metric."""
    return label + r" $\downarrow$"


def up(label):
    return label + r" $\uparrow$"


def bars(ax, x, values, label=None, idx=0, width=0.8, ours=False, style=None, **kw):
    """Draw a bar group in the paper palette: competitors take FILLS[idx], ours=True takes the solid OURS fill, and style overrides both."""
    f = style if style is not None else (OURS if ours else FILLS[idx % len(FILLS)])
    return ax.bar(x, values, width, label=label, facecolor=f["fc"], hatch=f["hatch"] or None,
                  edgecolor="black", linewidth=BAR_EDGE_LW, **kw)


def band_groups(ax, centers, halfwidth, every=2, start=0):
    """Shade every `every`-th group with a light band behind the data."""
    for c in list(centers)[start::every]:
        ax.axvspan(c - halfwidth, c + halfwidth, color=BAND_BG, zorder=0, lw=0)


def line(ax, x, y, label=None, idx=0, **kw):
    """Plot a line with the colour, marker and line style of SERIES[idx]."""
    d = SERIES[idx % len(SERIES)]
    return ax.plot(x, y, color=d["color"], marker=d["marker"], ls=d["ls"],
                   ms=4.5, label=label, **kw)


def label_values(ax, x, y, fmt="%.2f", dy=None, fontsize=VALUE_FS, bold=False, **kw):
    """Annotate each point or bar top with its value; dy is an offset in points, independent of the axis range and scale."""
    if dy is None:
        dy = 3.5
    out = []
    for xi, yi in zip(x, y):
        if yi is None:
            continue
        out.append(ax.annotate(fmt % yi, (xi, yi), xytext=(0, dy), textcoords="offset points",
                               ha="center", va="bottom", fontsize=fontsize,
                               fontweight="bold" if bold else "normal", gid="value", **kw))
    return out


def headroom(ax, frac=0.18):
    """Raise the upper y limit so value labels clear the legend and the frame; multiplicative on a log axis."""
    lo, hi = ax.get_ylim()
    if ax.get_yscale() == "log":
        ax.set_ylim(lo, hi * (1 + frac * 6))
    else:
        ax.set_ylim(lo, hi + frac * (hi - lo))


def legend_inside(ax, ncol=1, loc="best"):
    """Legend inside the axes with a light frame, for bar charts and multi-series line plots."""
    lg = ax.legend(ncol=ncol, loc=loc, frameon=True, framealpha=0.92,
                   edgecolor="0.75", fancybox=False)
    lg.get_frame().set_linewidth(0.6)
    return lg


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _dense(line, step=2.0):
    """Sample a line densely in display coordinates, so a text box crossed between two vertices is still caught."""
    import numpy as np
    pts = line.get_transform().transform(line.get_xydata())
    pts = np.asarray([p for p in pts if np.isfinite(p).all()])
    if len(pts) < 2:
        return pts
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        d = float(np.hypot(*(b - a)))
        n = max(2, int(d / step) + 1)
        out.append(a + (b - a) * np.linspace(0, 1, n)[:, None])
    return np.vstack(out)


def _bb(artist, rend):
    try:
        b = artist.get_window_extent(renderer=rend)
        return b if b.width > 0 and b.height > 0 else None
    except Exception:
        return None


def _knockout(t, ln):
    """True if text t intentionally masks reference line ln (gid 'ref'): an opaque bbox drawn above the line."""
    if ln.get_gid() != "ref":
        return False
    bp = t.get_bbox_patch()
    if bp is None:
        return False
    fc = bp.get_facecolor()
    return fc is not None and len(fc) == 4 and fc[3] >= 0.999 and (bp.get_alpha() in (None, 1, 1.0)) and t.get_zorder() > ln.get_zorder()


def check_overlap(fig, pad=0.5, ignore_ticks=True, verbose=True):
    """Return a list of (kind, description) overlaps: text on text, text on lines, legend on data, inside legends, and labels outside the canvas; pad is the tolerance in pixels."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    hits = []
    for ax in fig.get_axes():
        texts = [t for t in ax.texts if t.get_text().strip()]
        if not ignore_ticks:
            texts += [t for t in ax.get_xticklabels() + ax.get_yticklabels()
                      if t.get_text().strip() and abs(t.get_rotation() % 180) < 1e-6]
        boxes = [(t, _bb(t, rend)) for t in texts]
        boxes = [(t, b) for t, b in boxes if b is not None]
        from matplotlib.transforms import Bbox as _Bbox
        boxes = [(t, (_Bbox.union([b, t.get_bbox_patch().get_window_extent(rend)]) if t.get_bbox_patch() is not None else b)) for t, b in boxes]

        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                (t1, b1), (t2, b2) = boxes[i], boxes[j]
                if b1.overlaps(b2) and min(b1.x1, b2.x1) - max(b1.x0, b2.x0) < -pad:
                    continue
                if b1.overlaps(b2):
                    hits.append(("text over text", "%r and %r" % (t1.get_text()[:24], t2.get_text()[:24])))

        for t, b in boxes:
            for ln in ax.lines:
                if _knockout(t, ln):
                    continue
                pts = _dense(ln)
                inside = [(x, y) for x, y in pts
                          if b.x0 + pad < x < b.x1 - pad and b.y0 + pad < y < b.y1 - pad]
                if len(inside) >= 2:
                    hits.append(("text over line", "%r has %d line points" % (t.get_text()[:24], len(inside))))
                    break

        lg = ax.get_legend()
        if lg is not None:
            lb = _bb(lg, rend)
            if lb is not None:
                for ln in ax.lines:
                    pts = _dense(ln)
                    n = sum(1 for x, y in pts if lb.x0 < x < lb.x1 and lb.y0 < y < lb.y1)
                    if n >= 2:
                        hits.append(("Legend covers data", "Legend box contains %d data points" % n))
                        break
                for p in ax.patches:
                    pb = _bb(p, rend)
                    if pb is not None and lb.overlaps(pb):
                        hits.append(("Legend covers a bar", "Legend intersects a bar"))
                        break
    fb = fig.bbox
    for lg in [a.get_legend() for a in fig.get_axes()] + list(fig.legends):
        if lg is None:
            continue
        tx = [(t, _bb(t, rend)) for t in lg.get_texts() if t.get_text().strip()]
        tx = [(t, b) for t, b in tx if b is not None]
        hs = getattr(lg, "legend_handles", None) or getattr(lg, "legendHandles", [])
        hb = [_bb(h, rend) for h in hs]
        for i in range(len(tx)):
            for j in range(i + 1, len(tx)):
                if tx[i][1].overlaps(tx[j][1]):
                    hits.append(("Legend overlaps internally", "%r and %r" % (tx[i][0].get_text()[:20], tx[j][0].get_text()[:20])))
            for j, b in enumerate(hb):
                if j != i and b is not None and tx[i][1].overlaps(b):
                    hits.append(("Legend overlaps internally", "%r covers color block %d" % (tx[i][0].get_text()[:20], j + 1)))
        lb = _bb(lg, rend)
        if lb is not None and (lb.x0 < fb.x0 - pad or lb.x1 > fb.x1 + pad or lb.y1 > fb.y1 + pad):
            hits.append(("Legend out of bounds", "Legend extends outside the canvas"))
    for a_ in fig.get_axes():
        for t_ in (a_.xaxis.label, a_.yaxis.label, a_.title, a_._left_title, a_._right_title):
            if not t_.get_text().strip():
                continue
            b_ = _bb(t_, rend)
            if b_ is not None and (b_.x0 < fb.x0 - pad or b_.x1 > fb.x1 + pad or b_.y0 < fb.y0 - pad or b_.y1 > fb.y1 + pad):
                hits.append(("label out of bounds", "%r extends beyond the canvas" % t_.get_text()[:30]))
    if verbose and hits:
        print("Overlap detected at %d places:" % len(hits))
        for k, d in hits:
            print("   [%s] %s" % (k, d))
    return hits


def panel_title(ax, text, pad=3.0):
    """Panel label as a left-aligned 8 pt axes title, e.g. '(a) 12 client stacks'; pad is the gap to the axes top in points."""
    return ax.set_title(text, loc="left", fontsize=8, pad=pad)


def titles_to_figure_left(fig, pad_pt=1.5):
    """Move left-aligned panel titles to the left edge of the canvas, freeze the layout, and fail if a title comes within 2 pt of a y-axis label."""
    fig.canvas.draw()
    for ax in fig.get_axes():
        t = ax._left_title
        if not t.get_text().strip():
            continue
        bb = ax.get_window_extent()
        t.set_x((pad_pt * fig.dpi / 72.0 - bb.x0) / bb.width)
    fig.set_layout_engine("none")
    fig.canvas.draw(); rend = fig.canvas.get_renderer()
    for ax in fig.get_axes():
        t = ax._left_title
        if not t.get_text().strip() or not ax.yaxis.label.get_text().strip():
            continue
        tb = t.get_window_extent(rend); lb = ax.yaxis.label.get_window_extent(rend)
        gap_pt = (tb.y0 - lb.y1) * 72.0 / fig.dpi
        if gap_pt < 2.0 and lb.x1 > tb.x0:
            raise AssertionError("Panel label %r is only %.1f pt above the y-axis label" % (t.get_text()[:20], gap_pt))


def check_font_sizes(fig, min_pt=8.0, value_min=VALUE_FS):
    """Return the texts below the size limits at print size: 8 pt for general text, 7.5 pt for value labels (gid 'value')."""
    from matplotlib.text import Text
    bad = []
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip():
            continue
        lim = value_min if t.get_gid() == "value" else min_pt
        if t.get_fontsize() < lim - 1e-6:
            bad.append((t.get_text()[:30], t.get_fontsize(), lim))
    return bad


def save_checked(fig, path, cols=1, allow_overlap=False):
    """Check font sizes and overlaps, then save with the width check; a failing figure is not written and a stale file of the same name is removed."""
    hits = check_overlap(fig, verbose=not allow_overlap, ignore_ticks=False)
    small = check_font_sizes(fig)
    if small:
        plt.close(fig)
        raise AssertionError("%s has %d places where text is smaller than the lower limit, not saved: %r" % (path, len(small), small[:6]))
    if hits and not allow_overlap:
        plt.close(fig)
        import os
        try:
            os.remove(path)
        except OSError:
            pass
        raise AssertionError("%s detected %d overlaps, not saved. See above for details." % (path, len(hits)))
    return save(fig, path, cols=cols)


if __name__ == "__main__":
    selftest(); swarm_selftest(); print("Swarm arrangement self-test passed: no overlap, reproducible, the should-fail case with everything placed on the center line does have overlap"); knockout_selftest(); print("Knockout rule self-test passed (3 cases)")
