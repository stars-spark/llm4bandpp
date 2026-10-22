#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fig. 4 of the paper (fig_closedloop_dynamics.pdf), redrawn from the CSV files in data/ alone.
The drawing is that of dynamics() in scripts/paper/make_fig_closedloop_v1.py; only the data source differs (the CSV files
were written by scripts/paper/export_figure_data_v1.py from the same functions, which read the per-frame and per-step logs).
Usage: python3 plot_fig4.py [OUTPUT.pdf]   (default: fig_closedloop_dynamics.pdf next to this script)
"""
import csv, json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import ieee_style as S   # noqa: E402  copy of scripts/paper/ieee_style.py
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "fig_closedloop_dynamics.pdf"
C = json.loads((HERE / "data/constants.json").read_text())
T_END = 120.0; GRAY = "0.45"


def cols(name):
    """The columns of a CSV file in data/, numbers as floats."""
    rows = list(csv.DictReader(open(HERE / "data" / name)))
    def val(s):
        try: return float(s)
        except ValueError: return s
    return {k: [val(r[k]) for r in rows] for k in rows[0]}


def main():
    a = cols("panel_a_vmaf_over_time.csv"); b = cols("panel_b_call_rates.csv"); cap = cols("panel_b_capacity.csv")
    cen = np.array(a["bin_centre_s"]); ours, gcc = np.array(a["vmaf_llm4bandpp"]), np.array(a["vmaf_python_gcc"])
    tr = dict(t=np.array(b["call_time_s"]), x=np.array(b["estimate_mbps"]), a=np.array(b["announced_mbps"]), g=np.array(b["shadow_gcc_mbps"]),
              ct=np.array(cap["start_s"]), cr=np.array(cap["capacity_mbps"]))
    cc, cm = cols("panel_c_utility_cells.csv"), cols("panel_c_utility_means.csv")
    lc = [dict(label=lab, cells={int(c): v for s, c, v in zip(cc["setting"], cc["capacity_kbps"], cc["utility_difference"]) if s == lab},
               D=D, ci=(lo, hi)) for lab, D, lo, hi in zip(cm["setting"], cm["mean"], cm["ci90_low"], cm["ci90_high"])]
    S.apply()
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(S.TWO_COL_IN, 1.58))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1.05, 1.25])
    a1, a2, a3 = (fig.add_subplot(gs[i]) for i in range(3))
    # (a) VMAF over call time, 2 s bins; shaded: first 30 s
    a1.axvspan(0, 30, color=S.BAND_BG, lw=0, zorder=0)
    a1.plot(cen, gcc, color=GRAY, lw=1.0, ls=(0, (3, 1.5)), marker="s", ms=2.8, markevery=5, mfc="white", mec=GRAY, label="Python GCC")
    a1.plot(cen, ours, color=S.OURS["fc"], lw=1.3, marker="o", ms=2.8, markevery=5, mec="white", mew=0.4, label="LLM4band++")
    a1.axvline(30, color="0.3", lw=0.6, ls=":")
    a1.set_xlim(0, T_END); a1.set_xticks([0, 30, 60, 90, 120]); a1.set_xlabel("Call time (s)"); a1.set_ylabel("VMAF")
    a1.set_ylim(0, 100); a1.set_yticks([0, 20, 40, 60, 80, 100])
    a1.legend(loc="lower right", handlelength=1.5, borderaxespad=0.3)
    S.panel_title(a1, f"(a) 720p, mean of {C['cells_panel_a']} cells")
    # (b) one cellular call: capacity, estimate, announced rate, shadow GCC
    a2.fill_between(tr["ct"], tr["cr"], step="post", color="0.86", lw=0, label="Capacity", zorder=1)
    a2.plot(tr["t"], tr["x"], color="black", lw=0.5, label="Estimate $x$", zorder=2)
    a2.plot(tr["t"], tr["a"], color=S.OURS["fc"], lw=1.4, label="Announced", zorder=3)
    a2.plot(tr["t"], tr["g"], color="0.15", lw=0.6, ls=(0, (2.5, 1.5)), label="Shadow GCC", zorder=4)
    a2.set_xlim(0, T_END); a2.set_xticks([0, 30, 60, 90, 120]); a2.set_xlabel("Call time (s)"); a2.set_ylabel("Rate (Mb/s)")
    top = max(tr["cr"].max(), np.nanmax(tr["x"]), np.nanmax(tr["a"])); a2.set_ylim(0, top / 0.6); a2.set_yticks([0, 2, 4, 6])
    a2.legend(loc="upper left", ncol=2, handlelength=1.4, columnspacing=0.6)
    S.panel_title(a2, "(b) One cellular call, 720p")
    # (c) utility per capacity and mean with 90% interval; dashed: comparability margin
    caps = [100, 200, 300, 400]; xs = {c: i for i, c in enumerate(caps)}; xm = len(caps) + 0.3
    a3.axvspan(len(caps) - 0.5, xm + 0.6, color=S.BAND_BG, lw=0, zorder=0)
    a3.axhline(0, color="0.2", lw=0.6, zorder=1); a3.axhline(C["comparable_margin"], color="0.2", lw=0.7, ls=(0, (3, 2)), zorder=1)
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
    S.save_checked(fig, str(OUT), cols=2); print("Written", OUT)   # checks overlaps and width before writing


if __name__ == "__main__":
    main()
