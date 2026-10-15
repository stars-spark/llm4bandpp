#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Closed-loop data figures. Sample selection was fixed before plotting.
fig_closedloop_forest.pdf (not in the paper; Table V gives the same readings): VMAF difference to the Python GCC and to learned references with 90% intervals, the same readings as make_tables_v2.closedloop_rows; dashed: non-inferiority margin -6.
fig_closedloop_dynamics.pdf (Fig. 4): (a) per-frame VMAF of all valid runs of hd720-closedloop-ch-v1 aligned to call time as in steady_state_qoe_v1, 2 s bins, mean within cells then over cells (a bin missing in every run of a cell is interpolated from its neighbours); (b) the lower-median-VMAF call of the deployed-system arm in hd720-realtrace-ch-v1: capacity, learned estimate, announced rate, shadow GCC; (c) per-capacity utility differences to LLM4Band from four registered result files, with each registered mean and 90% interval.
Gates: (a) ramp-up and steady differences within 1 VMAF of closedloop-steady-qoe-v1; (b) announced rates match the decision log; (c) means equal the registry.
Usage: python3 scripts/paper/make_fig_closedloop_v1.py [--forest|--dynamics]
"""
import gzip, json, math, statistics as st, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/paper"))
import ieee_style as S   # noqa: E402
import make_tables_v2 as T   # noqa: E402
import steady_state_qoe_v1 as SQ   # noqa: E402
R = ROOT / "experiments/results"; TB = Path("/path/to/testbed/results"); FIGS = ROOT / "papers/revision-v2/figs"
OURS, GCC = "arm_ch_x", "gcc_pt125_c200"; BIN = 2.0; T_END = 120.0
GRAY = "0.45"; MARGIN = -6.0


def forest(G):
    rows = [r for r in T.closedloop_rows(G) if isinstance(r, tuple) and "VMAF" in r[1] or isinstance(r, dict) and r["unit"] == "VMAF"]
    S.apply()
    import matplotlib.pyplot as plt
    n = len(rows); pitch = 0.125; top_in, bot_in = 0.17, 0.34
    H = top_in + bot_in + pitch * n; W = S.ONE_COL_IN
    fig = plt.figure(figsize=(W, H), layout=None)
    cols = [(0.0, 1.36), (1.36, 0.98), (2.34, 0.95), (3.29, W - 3.29)]
    axs = [fig.add_axes([x / W, bot_in / H, w / W, pitch * n / H]) for x, w in cols]
    lab, ax, num, stc = axs
    for a in (lab, num, stc):
        a.set_xlim(0, 1); a.set_ylim(n - 0.5, -0.5); a.set_xticks([]); a.set_yticks([]); a.axis("off")
    ax.set_ylim(n - 0.5, -0.5)
    gi = [i for i, r in enumerate(rows) if isinstance(r, tuple)] + [n]
    for k in range(len(gi) - 1):
        if k % 2 == 0:
            for a in axs: a.axhspan(gi[k] - 0.5, gi[k + 1] - 0.5, color=S.BAND_BG, lw=0, zorder=0)
    for y, r in enumerate(rows):
        if isinstance(r, tuple):
            hd = {"Python GCC every 200 ms (VMAF)": "vs. Python GCC", "Learned estimators (VMAF)": "vs. learned estimators"}[r[1]]
            lab.text(0.0, y, hd, ha="left", va="center", fontsize=8, fontweight="bold"); continue
        lab.text(0.09 if r["indent"] else 0.0, y, r["label"].replace("320x240", "320×240"), ha="left", va="center", fontsize=8)
        reg = r["st"] != "--"; lo, hi = r["ci"]
        ax.plot([lo, hi], [y, y], color="0.15", lw=0.8, solid_capstyle="butt", zorder=3)
        if reg: ax.scatter([r["D"]], [y], s=16, marker="o", zorder=4, **S.DOT_OURS)
        else: ax.scatter([r["D"]], [y], s=14, marker="o", zorder=4, facecolor="white", edgecolor="0.25", linewidth=0.8)
        num.text(0.04, y, f"{r['D']:.1f} [{lo:.1f}, {hi:.1f}]".replace("-", "−"), ha="left", va="center", fontsize=8, gid="value")
        stc.text(0.5, y, r["st"].replace("--", "–"), ha="center", va="center", fontsize=8, fontweight="bold" if reg else "normal")
    num.text(0.04, -0.58, "Mean [90% int.]", ha="left", va="bottom", fontsize=8)
    stc.text(0.5, -0.58, "St.", ha="center", va="bottom", fontsize=8)
    ax.axvline(0, color="0.2", lw=0.6, zorder=1)
    ax.axvline(MARGIN, color="0.2", lw=0.7, ls=(0, (3, 2)), zorder=1)
    ax.set_xlim(-8, 11); ax.set_xticks([-5, 0, 5, 10]); ax.set_xticklabels(["−5", "0", "5", "10"])
    ax.set_yticks([]); ax.grid(True, axis="x", color="0.88", lw=0.4); ax.grid(False, axis="y")
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("VMAF, ours minus reference")
    fig.canvas.draw(); rend = fig.canvas.get_renderer(); xr = lab.get_window_extent(rend).x1
    wide = [t.get_text() for t in lab.texts if t.get_window_extent(rend).x1 > xr - 2]
    assert not wide, ("label runs into the plot column", wide)
    out = FIGS / "fig_closedloop_forest.pdf"; S.save_checked(fig, str(out), cols=1); print("Written", out, n, "row")


def run_series(d):
    q = next(d.glob("quality_*.json"), None); ft = SQ.frame_times(d)
    if q is None or ft is None: return None
    Q = json.load(open(q)); step = Q["frame_step"]; acc = {}
    for idx, _, v in Q["per_frame"]:
        k = idx * step
        if k >= len(ft) or ft[k] >= T_END: continue
        acc.setdefault(int(ft[k] // BIN), []).append(v)
    return {b: st.mean(v) for b, v in acc.items()}


def time_curve():
    bid = "hd720-closedloop-ch-v1"; K = TB / bid
    rows = [json.loads(l) for l in open(R / bid.replace("-", "_") / "runs_full.jsonl")]
    per = {}   # (cell, arm) -> [series]
    for r in rows:
        if not r.get("valid") or r["arm"] not in (OURS, GCC): continue
        s = run_series(K / "main" / r["job"])
        if s: per.setdefault((f"{r['cond']}__{r['video_id']}", r["arm"]), []).append(s)
    cells = sorted({c for c, _ in per})
    nb = int(T_END // BIN); curve = {}; cen = (np.arange(nb) + 0.5) * BIN; nfill = 0
    for a in (OURS, GCC):
        cc = []
        for c in cells:
            y = np.array([st.mean(v) if (v := [s[b] for s in per.get((c, a), []) if b in s]) else np.nan for b in range(nb)])
            ok = ~np.isnan(y); nfill += int((~ok).sum()); cc.append(np.interp(cen, cen[ok], y[ok]))
        curve[a] = np.mean(cc, axis=0)
    print(f"(a) interpolated bins {nfill}, share {nfill / (2 * len(cells) * nb):.1%}")
    d = curve[OURS] - curve[GCC]
    ref = json.loads((R / "closedloop_steady_qoe_v1/summary.json").read_text())[bid]
    ramp, stdy = np.nanmean(d[cen < 30]), np.nanmean(d[cen >= 30])
    assert abs(ramp - ref["ramp"]["D"]) < 1.0 and abs(stdy - ref["steady"]["D"]) < 1.0, (ramp, ref["ramp"]["D"], stdy, ref["steady"]["D"])
    print(f"(a) cells {len(cells)}, ramp-up difference {ramp:.2f} (registered {ref['ramp']['D']:.2f}), steady difference {stdy:.2f} (registered {ref['steady']['D']:.2f})")
    return cen, curve, len(cells)


def pick_trace():
    bid = "hd720-realtrace-ch-v1"
    rows = [json.loads(l) for l in open(R / bid.replace("-", "_") / "runs_full.jsonl")]
    v = sorted([r for r in rows if r.get("valid") and r["arm"] == OURS], key=lambda r: r["vmaf"])
    r = v[math.ceil(len(v) / 2) - 1]
    return TB / bid / "main" / r["job"], r, len(v)


def trace():
    d, r, n = pick_trace()
    cap = []
    for l in open(next(d.glob("control_*.log"))):
        l = l.strip()
        if l.startswith("{"):
            e = json.loads(l)
            if e.get("event") == "apply": cap.append((float(e["wall_time_ms"]), float(e["rate_kbps"])))
    with gzip.open(next(d.glob("obs_*.jsonl.gz")), "rt") as f: steps = [json.loads(l) for l in f]
    with gzip.open(next(d.glob("decision_*.jsonl.gz")), "rt") as f: dec = [e for e in map(json.loads, f) if e.get("event") == "bwe_decision"]
    dt_ = np.array([e["applied_wall_ms"] for e in dec]); dv = np.array([e["applied_bandwidth_bps"] for e in dec], float); hit = []
    for s in steps:
        j = int(np.argmin(np.abs(dt_ - s["t_ms"])))
        if abs(dt_[j] - s["t_ms"]) <= 2.0: hit.append(abs(dv[j] - s["est_bps"]) <= 1.0)
    assert len(hit) > 0.95 * len(steps) and all(hit), (len(hit), len(steps), sum(hit))
    t0 = cap[0][0]; t = np.array([(s["t_ms"] - t0) / 1000 for s in steps]); m = (t >= 0) & (t <= T_END)
    x = np.array([s["model_bps"] for s in steps], float) / 1e6; a = np.array([s["est_bps"] for s in steps], float) / 1e6
    g = np.array([s["envelope"]["gcc_bps"] for s in steps], float) / 1e6
    ct = np.array([(tt - t0) / 1000 for tt, _ in cap] + [T_END]); cr = np.array([k for _, k in cap] + [cap[-1][1]]) / 1000
    late = m & (t >= 10)
    info = dict(job=r["job"], cond=r["cond"], vmaf=r["vmaf"], n=n, rewrite=float(np.mean(np.abs(a[late] - x[late]) > 1e-6)),
                above=float(np.mean(a[late] > x[late] + 1e-6)), follow_gcc=float(np.mean(np.abs(a[m] - g[m]) < 1e-6)))
    print("(b) selected", info)
    return dict(t=t[m], x=x[m], a=a[m], g=g[m], ct=ct, cr=cr, info=info)


LOWCAP = [("lowbw-ch-vs-conf-env6-v1", "lowbw_ch_vs_conf_v1", "claim2_env6", "Behind envelope"),
          ("lowbw-loss1-env6-v1", "lowbw_loss1_env6_v1", "primary", "Behind envelope, 1% loss"),
          ("lowbw-chf-vs-conf-v1", "lowbw_chf_vs_conf_v1", "claim1_env0", "No envelope")]


def lowcap(G):
    out = []
    for rid, d, key, lab in LOWCAP:
        m = json.loads((R / d / "result_v1.json").read_text())[key]
        assert m["D"] == G[rid][-1]["D"] and list(m["ci90"]) == list(G[rid][-1]["ci90"]), rid
        out.append(dict(label=lab, cells={int(k): v for k, v in m["cell_diff"].items()}, D=m["D"], ci=m["ci90"]))
    m = json.loads((R / "lowbw_loss200_ch_v1/result_v1.json").read_text()); assert m["D"] == G["lowbw-loss200-ch-v1"][-1]["D"]
    out.append(dict(label="No envelope, 1% loss", cells={200: m["D"]}, D=m["D"], ci=m["ci90"]))
    return out


def dynamics(G):
    cen, curve, ncell = time_curve(); tr = trace(); lc = lowcap(G)
    S.apply()
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(S.TWO_COL_IN, 1.58))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1.05, 1.25])
    a1, a2, a3 = (fig.add_subplot(gs[i]) for i in range(3))
    # (a)
    a1.axvspan(0, 30, color=S.BAND_BG, lw=0, zorder=0)
    a1.plot(cen, curve[GCC], color=GRAY, lw=1.0, ls=(0, (3, 1.5)), marker="s", ms=2.8, markevery=5, mfc="white", mec=GRAY, label="Python GCC")
    a1.plot(cen, curve[OURS], color=S.OURS["fc"], lw=1.3, marker="o", ms=2.8, markevery=5, mec="white", mew=0.4, label="LLM4band++")
    a1.axvline(30, color="0.3", lw=0.6, ls=":")
    a1.set_xlim(0, T_END); a1.set_xticks([0, 30, 60, 90, 120]); a1.set_xlabel("Call time (s)"); a1.set_ylabel("VMAF")
    a1.set_ylim(0, 100); a1.set_yticks([0, 20, 40, 60, 80, 100])
    a1.legend(loc="lower right", handlelength=1.5, borderaxespad=0.3)
    S.panel_title(a1, f"(a) 720p, mean of {ncell} cells")
    # (b)
    a2.fill_between(tr["ct"], tr["cr"], step="post", color="0.86", lw=0, label="Capacity", zorder=1)
    a2.plot(tr["t"], tr["x"], color="black", lw=0.5, label="Estimate $x$", zorder=2)
    a2.plot(tr["t"], tr["a"], color=S.OURS["fc"], lw=1.4, label="Announced", zorder=3)
    a2.plot(tr["t"], tr["g"], color="0.15", lw=0.6, ls=(0, (2.5, 1.5)), label="Shadow GCC", zorder=4)
    a2.set_xlim(0, T_END); a2.set_xticks([0, 30, 60, 90, 120]); a2.set_xlabel("Call time (s)"); a2.set_ylabel("Rate (Mb/s)")
    top = max(tr["cr"].max(), np.nanmax(tr["x"]), np.nanmax(tr["a"])); a2.set_ylim(0, top / 0.6); a2.set_yticks([0, 2, 4, 6])
    a2.legend(loc="upper left", ncol=2, handlelength=1.4, columnspacing=0.6)
    S.panel_title(a2, "(b) One cellular call, 720p")
    # (c)
    caps = [100, 200, 300, 400]; xs = {c: i for i, c in enumerate(caps)}; xm = len(caps) + 0.3
    a3.axvspan(len(caps) - 0.5, xm + 0.6, color=S.BAND_BG, lw=0, zorder=0)
    a3.axhline(0, color="0.2", lw=0.6, zorder=1); a3.axhline(-5.27, color="0.2", lw=0.7, ls=(0, (3, 2)), zorder=1)
    sty = [dict(marker="o", ls="-", color=S.OURS["fc"], mfc=S.OURS["fc"], mec="white"),
           dict(marker="s", ls="--", color="#005f73", mfc="#005f73", mec="white"),
           dict(marker="^", ls=":", color="0.25", mfc="white", mec="0.25"),
           dict(marker="D", ls="none", color="0.25", mfc="0.25", mec="white")]
    short = {"Behind envelope": "Envelope", "Behind envelope, 1% loss": "Envelope,\n1% loss", "No envelope": "No\nenvelope", "No envelope, 1% loss": "No envelope,\n1% loss"}
    off = [-0.24, -0.08, 0.08, 0.24]
    for s_, o, sy in zip(lc, off, sty):
        cx = sorted(s_["cells"]); a3.plot([xs[c] for c in cx], [s_["cells"][c] for c in cx], lw=1.0, ms=3.6, mew=0.5, label=short[s_["label"]], zorder=3, **sy)
        a3.errorbar([xm + o], [s_["D"]], yerr=[[s_["D"] - s_["ci"][0]], [s_["ci"][1] - s_["D"]]], fmt=sy["marker"], ms=3.6, mew=0.5,
                    color=sy["color"], mfc=sy["mfc"], mec=sy["mec"], ecolor=sy["color"], elinewidth=0.8, capsize=1.5, zorder=3)
    a3.set_xticks(list(range(len(caps))) + [xm]); a3.set_xticklabels([str(c) for c in caps] + ["Mean"])
    a3.set_xlim(-0.5, xm + 0.6); a3.set_xlabel("Capacity (kb/s)")
    a3.set_ylabel("Utility difference")
    a3.set_ylim(-7, 4); a3.set_yticks([-6, -3, 0, 3]); a3.set_yticklabels(["−6", "−3", "0", "3"])
    a3.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), ncol=1, handlelength=1.8, borderaxespad=0.3, labelspacing=0.6)
    S.panel_title(a3, "(c) 320×240, ours minus LLM4Band")
    out = FIGS / "fig_closedloop_dynamics.pdf"; S.save_checked(fig, str(out), cols=2); print("Written", out)
    return tr["info"]


if __name__ == "__main__":
    G = T.reg()
    if "--forest" in sys.argv or len(sys.argv) == 1: forest(G)
    if "--dynamics" in sys.argv or len(sys.argv) == 1: dynamics(G)
