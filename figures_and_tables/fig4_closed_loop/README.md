# Fig. 4. Closed-loop dynamics

This folder redraws Fig. 4 without the rest of the package: the plotted values are in `data/`, and `plot_fig4.py`
draws them exactly as in the paper (the output is pixel-identical to `fig_closedloop_dynamics_paper.pdf`).

| File | Content |
|---|---|
| `plot_fig4.py` | plotting script; reads only `data/` and `ieee_style.py` |
| `ieee_style.py` | shared figure style and checks (copy of `scripts/paper/ieee_style.py`) |
| `data/panel_a_vmaf_over_time.csv` | (a) VMAF in 2 s bins over call time, first 720p batch, mean over 12 cells |
| `data/panel_b_call_rates.csv` | (b) per decision step of one cellular call: learned estimate, announced rate, shadow GCC |
| `data/panel_b_capacity.csv` | (b) the capacity trace of that call (step function, start time of each step) |
| `data/panel_c_utility_cells.csv` | (c) utility difference to LLM4Band per capacity, 320×240 |
| `data/panel_c_utility_means.csv` | (c) mean and 90% interval of each setting |
| `data/constants.json` | the selected call (job, cell, VMAF), the number of cells in (a) and the dashed margin in (c) |
| `fig_closedloop_dynamics_paper.pdf` | the figure as it appears in the paper |

```bash
pip install numpy==2.5.3 matplotlib==3.11.2      # versions used for the paper
python3 plot_fig4.py                             # writes fig_closedloop_dynamics.pdf here
```

Before writing, the script checks that no text overlaps lines or other text and that the width fits two columns.

**Units.** VMAF 0 to 100; rates in Mb/s; utility differences in points of the closed-loop utility, ours minus
LLM4Band (positive favours ours). The dashed line in (c) is the −5.27-point margin of Section V-A.

**Where the values come from.** `python3 scripts/paper/export_figure_data_v1.py` (package root, paths set as in
`docs/PACKAGE.md`) writes `data/` from `time_curve`, `trace` and `lowcap` of `scripts/paper/make_fig_closedloop_v1.py`,
the functions behind the paper's figure, including their checks: (a) agrees with the registered ramp-up and steady-state
differences within 1 VMAF, (b) the announced rates match the decision log, (c) the means equal the registry. Inputs and
commands are in [the results index](../../docs/RESULTS_INDEX.md#fig-4-closed-loop-dynamics).
