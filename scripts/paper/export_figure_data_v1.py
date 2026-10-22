#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write the values plotted in Figs. 3 and 4 to CSV files, so that the standalone scripts in figures_and_tables/ can redraw
the two figures without the rest of the package. The values come from the same functions the paper's generators call
(make_fig_designer_v4.bar_rows and cl_cells for Fig. 3; make_fig_closedloop_v1.time_curve, trace and lowcap for Fig. 4),
including their gates against the registry. Floats are written with repr(), so they round-trip exactly.
Needs the placeholder paths set as in docs/PACKAGE.md (Fig. 4 reads external/testbed/results).
Usage: python3 scripts/paper/export_figure_data_v1.py [OUT_ROOT]   (default: figures_and_tables)
"""
import csv, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/paper"))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "figures_and_tables"


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(header)
        for r in rows: w.writerow([repr(v) if isinstance(v, float) else v for v in r])
    print("Written", path.relative_to(OUT.parent) if OUT.parent in path.parents else path, len(rows), "rows")


def fig3():
    import make_fig_designer_v4 as V4, make_fig_designer_v6 as V6
    rows, c_host = V4.bar_rows(); D = V4.cl_cells(); d = OUT / "fig3_designer/data"
    out = []
    for r in rows:
        k = V6.kind(r, c_host); ba_rng, e2_rng = r[4], r[5]
        out.append([V6.NAMES[r[0]], k, float(r[1]), float(r[2])] +
                   ([float(ba_rng[0]), float(ba_rng[1])] if ba_rng else ["", ""]) + ([float(e2_rng[0]), float(e2_rng[1])] if e2_rng else ["", ""]))
    write(d / "panel_ab_bars.csv", ["method", "kind", "balanced_accuracy", "share_cells_correct", "ba_min", "ba_max", "share_min", "share_max"], out)
    lab = {"LLM": "Designer", "NAME": "Name", "DIST": "Distribution", "NONE": "Unadapted"}
    write(d / "panel_c_cells.csv", ["mapping", "cell", "utility_vs_true_mapping"],
          [[lab[m], i, float(v)] for m in ("LLM", "NAME", "DIST", "NONE") for i, v in enumerate(D[m])])
    (d / "constants.json").write_text(json.dumps({"severe_loss_points": V4.CL.SEVERE}, indent=1) + "\n")


def fig4():
    import make_fig_closedloop_v1 as F, make_tables_v2 as T
    G = T.reg(); cen, curve, ncell = F.time_curve(); tr = F.trace(); lc = F.lowcap(G); d = OUT / "fig4_closed_loop/data"
    write(d / "panel_a_vmaf_over_time.csv", ["bin_centre_s", "vmaf_llm4bandpp", "vmaf_python_gcc"],
          [[float(c), float(a), float(g)] for c, a, g in zip(cen, curve[F.OURS], curve[F.GCC])])
    write(d / "panel_b_call_rates.csv", ["call_time_s", "estimate_mbps", "announced_mbps", "shadow_gcc_mbps"],
          [[float(t), float(x), float(a), float(g)] for t, x, a, g in zip(tr["t"], tr["x"], tr["a"], tr["g"])])
    write(d / "panel_b_capacity.csv", ["start_s", "capacity_mbps"], [[float(t), float(c)] for t, c in zip(tr["ct"], tr["cr"])])
    write(d / "panel_c_utility_cells.csv", ["setting", "capacity_kbps", "utility_difference"],
          [[s["label"], c, float(s["cells"][c])] for s in lc for c in sorted(s["cells"])])
    write(d / "panel_c_utility_means.csv", ["setting", "mean", "ci90_low", "ci90_high"],
          [[s["label"], float(s["D"]), float(s["ci"][0]), float(s["ci"][1])] for s in lc])
    info = dict(tr["info"]); info["cells_panel_a"] = ncell; info["comparable_margin"] = -5.27
    (d / "constants.json").write_text(json.dumps(info, indent=1) + "\n")


if __name__ == "__main__":
    fig3(); fig4()
