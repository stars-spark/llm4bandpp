# Figures and tables

One folder per figure and table of the paper and its supplement. Each folder holds the item as it appears in the paper,
its source or data, and a README that names the generator and the inputs. Figs. 3 and 4 can be redrawn from their
folders alone (plotted values in CSV files and a standalone plotting script); the other items are regenerated, with
everything else, by `python3 reproduce/verify_level1.py` from the package root.

| Paper | Folder | Redraw from the folder alone |
|---|---|---|
| Fig. 1. System overview | [`fig1_system_overview/`](fig1_system_overview/) | `pdflatex fig_llm_position.tex` |
| Fig. 2. Probing envelope | [`fig2_probing_envelope/`](fig2_probing_envelope/) | `pdflatex fig_envelope.tex` |
| Fig. 3. Designer by method | [`fig3_designer/`](fig3_designer/) | `python3 plot_fig3.py` |
| Fig. 4. Closed-loop dynamics | [`fig4_closed_loop/`](fig4_closed_loop/) | `python3 plot_fig4.py` |
| Table I. Offline accuracy | [`table1_offline_accuracy/`](table1_offline_accuracy/) | LaTeX source |
| Table II. Two LLM positions | [`table2_llm_positions/`](table2_llm_positions/) | LaTeX source |
| Table III. Cost per decision | [`table3_cost/`](table3_cost/) | LaTeX source |
| Table IV. Designer tests | [`table4_designer/`](table4_designer/) | LaTeX source |
| Table V. Closed-loop VMAF | [`table5_closed_loop/`](table5_closed_loop/) | LaTeX source |
| Fig. S1. Reward weight λ | [`figS1_reward_weight/`](figS1_reward_weight/) | plotted values in JSON |
| Fig. S2. Designer prompt | [`figS2_designer_prompt/`](figS2_designer_prompt/) | text |
| Table S3. Fifteen-token variants | [`tableS3_token_variants/`](tableS3_token_variants/) | LaTeX source |
| Table S4. Over- and underestimation | [`tableS4_over_under_estimation/`](tableS4_over_under_estimation/) | LaTeX source |
| Section S8. Designer per client stack | [`tableS8_designer_per_stack/`](tableS8_designer_per_stack/) | LaTeX source |

Tables S1 and S2 are typed in the supplement; their sources are listed in `docs/RESULTS_INDEX.md`.
The files here are copies: the generators write to `papers/revision-v2/`, and `reproduce/verify_level1.py` compares
those outputs with `expected/`. After a change to a result file, rerun the generator (and, for Figs. 3 and 4,
`scripts/paper/export_figure_data_v1.py`) before using this folder.
