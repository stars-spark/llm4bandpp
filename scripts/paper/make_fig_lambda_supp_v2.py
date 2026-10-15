#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fig. S1 of the supplement: HCQ weight lambda sweep of the deployed recipe (conference encoder, HCQ, no LLM), mean of three seeds with min-max bars; left: per-scenario MSE relative
to its mean at lambda = 0.4; right: overestimation e+. Data: experiments/results/ch_lambda_sweep_v1/summary.json (ch-lambda-sweep-v1, from scripts/encoder/ch_lambda_sweep_v1.py);
lambda 0 and 0.4 are cells CB and CH of ablation-nl-enc-hcq-2x2-v1. Writes figS_lambda.pdf and figS_lambda.json.
Version 2: replaces make_fig_lambda_supp.py (not in this package), which plotted one seed of the light network.
Usage: make_fig_lambda_supp_v2.py [OUT_DIR]  (default papers/revision-v2/supplement)
"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "papers/revision-v2/supplement"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ieee_style as IS  # noqa: E402
IS.apply()
T = json.loads((ROOT / "experiments/results/ch_lambda_sweep_v1/summary.json").read_text())
LAMS = ["0.0", "0.2", "0.4", "0.6", "0.8", "1.0"]
SCN = [("Low BW", "Low BW"), ("High BW", "High BW"), ("Fluctuating", "Fluctuating")]


def main():
    x = [float(l) for l in LAMS]
    fig, axes = IS.figure(cols=1, height_in=1.55, ncols=2)
    out = {}
    for i, (k, lab) in enumerate(SCN):
        ref = T["0.4"][f"{k}|mse"]["mean"]
        for ax, key, sc in ((axes[0], f"{k}|mse", ref), (axes[1], f"{k}|over", 1.0)):
            m = [T[l][key]["mean"] / sc for l in LAMS]
            IS.line(ax, x, m, label=lab if ax is axes[0] else None, idx=i)
            c = ax.get_lines()[-1].get_color()
            ax.vlines(x, [T[l][key]["min"] / sc for l in LAMS], [T[l][key]["max"] / sc for l in LAMS], color=c, lw=0.9)
        out[k] = {"mse_mean": [T[l][f"{k}|mse"]["mean"] for l in LAMS], "over_mean": [T[l][f"{k}|over"]["mean"] for l in LAMS]}
    for ax in axes:
        ax.axvline(0.4, color="0.6", lw=0.8, ls=":", zorder=0)
        ax.set_xlabel(r"Reward weight $\lambda$")
        ax.set_xticks([0, 0.4, 0.8])
    axes[0].set_ylabel(r"MSE / MSE at $\lambda$=0.4")
    axes[1].set_ylabel("Overestimation $e^{+}$")
    IS.legend_above_figure(fig, axes[0], ncol=3)
    IS.save_checked(fig, OUT / "figS_lambda.pdf", cols=1)
    (OUT / "figS_lambda.json").write_text(json.dumps({"lambda": x, "per_scenario": out, "source": "experiments/results/ch_lambda_sweep_v1/summary.json"}, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
