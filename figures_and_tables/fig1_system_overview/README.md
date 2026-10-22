# Fig. 1. System overview

| File | Content |
|---|---|
| `fig_llm_position.tex` | TikZ source of the figure (standalone document) |
| `collector_grid_greys_light.tex` | the collector grid drawn inside the figure: one real 15 × 10 observation |
| `fig_llm_position.pdf` | the figure as it appears in the paper |

Rebuild here with `pdflatex fig_llm_position.tex` (TeX Live with `helvet`, `sansmath` and TikZ).

The grid is generated from the observation log
`external/testbed/results/hd720-closedloop-v1/main/hd_c2__johnny__pp__r1/obs_arm_llm4bandpp_x__hd_c2__d0__r1__vjohnny.jsonl.gz`
by `python3 scripts/paper/make_fig1_collector_grid_v1.py --palette greys --lighten 0.4 --out collector_grid_greys_light.tex`
(run from the package root). The adapter excerpt is the designer's answer for the SRT library in
`experiments/results/realtel_scale_v1/llm_deepseek.jsonl`. See also [the results index](../../docs/RESULTS_INDEX.md#fig-1-system-overview).
