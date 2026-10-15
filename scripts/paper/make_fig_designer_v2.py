#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single-column designer bar chart fig_designer_bars.pdf, an earlier form of Fig. 3(a) and (b): the deployment-time designer against seven non-LLM matchers. (a) Balanced accuracy on
the 12 new client stacks (realtel-scale-v1; open-model rows rescored from out_open_*.jsonl with the same scoring function); (b) share of the 42 end-to-end cells correct on real
software (realtel-e2e-v1 on the final ground truth, via make_tables_v2.e2e_v3). Gates: every value must equal its registered reading, otherwise the script stops.
Its figure is not in the paper; realtel_open70b_v1.py imports its open_ba(), and make_fig_designer_v3.py is a copy with three-sample open-model rows.
Usage: python3 scripts/paper/make_fig_designer_v2.py
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/paper")); sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import ieee_style as S   # noqa: E402
import realtel_adapter_v1 as M   # noqa: E402
import realtel_scale_v1 as RS   # noqa: E402
OUT = ROOT / "papers/revision-v2/figs/fig_designer_bars.pdf"
REG_OPEN = {"r1_32b": 0.893, "r1_14b": 0.693}
REG_E2E_V3 = {"DEEPSEEK": 1.000, "OPEN_r1_32b": 0.619, "OPEN_r1_14b": 0.714, "NAME": 0.476, "TFIDF": 0.571, "COMA": 0.619,
              "CUPID": 0.286, "SF": 0.762, "BGE": 0.619, "MPNET": 0.190}


def reg(i):
    m = None
    for l in open(ROOT / "experiments/registry.jsonl"):
        e = json.loads(l)
        if e.get("id") == i and e.get("event") == "data" and e.get("metrics"): m = e["metrics"]
    return m


def open_rows(tag):
    """Scored rows of open model `tag` per source and field order, parsed as open_ba does; the heatmap script calls it too."""
    Ssrc = RS.load_sources(); L = {}
    for j in map(json.loads, open(RS.OUT / f"out_open_{tag}.jsonl")):
        _, n, k = j["id"].split("|")
        try: L[(n, int(k))] = M.parse(j["text"], len(Ssrc[n]["fields"]))
        except Exception: L[(n, int(k))] = None
    for n in Ssrc:
        for k in range(M.NPRES): L.setdefault((n, k), None)
    return RS.rows(Ssrc, L)


def open_ba(tag):
    return M.ba(open_rows(tag))


def main():
    import make_tables_v2 as T2
    sc = reg("realtel-scale-v1"); e2 = T2.e2e_v3()
    base = ["COMA", "CUPID", "TFIDF", "MPNET", "BGE", "NAME", "SF"]
    nice = {"COMA": "COMA", "CUPID": "Cupid", "TFIDF": "TF-IDF", "MPNET": "mpnet", "BGE": "bge", "NAME": "Name", "SF": "SF"}
    oa = {t: open_ba(t) for t in REG_OPEN}
    for t, want in REG_OPEN.items():
        assert round(oa[t], 3) == want, (t, oa[t], want)
    for k, want in REG_E2E_V3.items():
        assert round(e2["rate"][k], 3) == want, (k, e2["rate"][k], want)
    assert e2["n"] == 42, e2["n"]
    base = sorted(base, key=lambda b: (-sc["ba_base"][b], b))
    import matplotlib
    BL = matplotlib.colormaps["Blues"]; C_HOST, C_OPEN, C_BASE = BL(0.8), BL(0.5), "#C8C8C8"
    rows = [("Hosted", sc["ba_llm"], e2["rate"]["DEEPSEEK"], C_HOST),
            ("32B", oa["r1_32b"], e2["rate"]["OPEN_r1_32b"], C_OPEN),
            ("14B", oa["r1_14b"], e2["rate"]["OPEN_r1_14b"], C_OPEN)] + \
           [(nice[b], sc["ba_base"][b], e2["rate"][b], C_BASE) for b in base]
    S.apply()
    fig, axes = S.figure(cols=1, height_in=1.9, ncols=2, sharey=True)
    y = [i if i < 3 else i + 0.5 for i in range(len(rows))]
    for ax, j, title, xlab in ((axes[0], 1, "(a) 12 client stacks", S.up("Balanced accuracy")),
                               (axes[1], 2, "(b) Real software", S.up("Share of cells correct"))):
        for yi, r in zip(y, rows):
            ax.barh(yi, r[j], height=0.64, color=r[3], edgecolor="none")
            ax.annotate(f"{r[j]:.2f}", (r[j], yi), xytext=(2.5, 0), textcoords="offset points", ha="left", va="center", fontsize=S.VALUE_FS, color="0.2", gid="value")
        ax.set_xlim(0, 1.25); ax.set_xticks([0, 0.5, 1.0]); ax.set_xticklabels(["0", "0.5", "1"])
        ax.grid(False); ax.set_xlabel(xlab); S.panel_title(ax, title)
        ax.tick_params(axis="y", length=0); ax.spines["left"].set_visible(False)
    axes[0].set_yticks(y); axes[0].set_yticklabels([r[0] for r in rows]); axes[0].invert_yaxis()
    S.save_checked(fig, str(OUT), cols=1)
    print("Written", OUT, [(r[0], round(r[1], 3), round(r[2], 3)) for r in rows])


if __name__ == "__main__":
    main()
