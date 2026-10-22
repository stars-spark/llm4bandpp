# Figures and tables

One folder per figure and table of the paper and its supplement: the item as printed, its source or plotted data, and a
README naming the generator and inputs. Figs. 3 and 4 redraw from their folders alone.

| Paper | Open | Data or source |
|---|---|---|
| Fig. 1. System overview | [`fig_llm_position.pdf`](fig1_system_overview/fig_llm_position.pdf) | [`fig_llm_position.tex`](fig1_system_overview/fig_llm_position.tex) (TikZ) |
| Fig. 2. Probing envelope | [`fig_envelope.pdf`](fig2_probing_envelope/fig_envelope.pdf) | [`fig_envelope.tex`](fig2_probing_envelope/fig_envelope.tex) (TikZ) |
| Fig. 3. Designer by method | [`fig_designer_three_paper.pdf`](fig3_designer/fig_designer_three_paper.pdf) | [`data/`](fig3_designer/data/), [`plot_fig3.py`](fig3_designer/plot_fig3.py) |
| Fig. 4. Closed-loop dynamics | [`fig_closedloop_dynamics_paper.pdf`](fig4_closed_loop/fig_closedloop_dynamics_paper.pdf) | [`data/`](fig4_closed_loop/data/), [`plot_fig4.py`](fig4_closed_loop/plot_fig4.py) |
| Table I. Offline accuracy | [`table_offline.tex`](table1_offline_accuracy/table_offline.tex) | [README](table1_offline_accuracy/) |
| Table II. Two LLM positions | [`table_position.tex`](table2_llm_positions/table_position.tex) | [README](table2_llm_positions/) |
| Table III. Cost per decision | [`table_cost.tex`](table3_cost/table_cost.tex) | [README](table3_cost/) |
| Table IV. Designer tests | [`table_designer.tex`](table4_designer/table_designer.tex) | [README](table4_designer/) |
| Table V. Closed-loop VMAF | [`table_closedloop_v2.tex`](table5_closed_loop/table_closedloop_v2.tex) | [README](table5_closed_loop/) |
| Fig. S1. Reward weight λ | [`figS_lambda.pdf`](figS1_reward_weight/figS_lambda.pdf) | [`data/figS_lambda.json`](figS1_reward_weight/data/figS_lambda.json) |
| Fig. S2. Designer prompt | [`prompt_template.txt`](figS2_designer_prompt/prompt_template.txt) | [README](figS2_designer_prompt/) |
| Table S3. Fifteen-token variants | [`tab_variants.tex`](tableS3_token_variants/tab_variants.tex) | [README](tableS3_token_variants/) |
| Table S4. Over- and underestimation | [`tab_eplus.tex`](tableS4_over_under_estimation/tab_eplus.tex) | [README](tableS4_over_under_estimation/) |
| Section S8. Designer per client stack | [`tab_designer_src.tex`](tableS8_designer_per_stack/tab_designer_src.tex) | [README](tableS8_designer_per_stack/) |

Tables S1 and S2 are typed in the supplement; their sources are in [`docs/RESULTS_INDEX.md`](../docs/RESULTS_INDEX.md).
The tables are generated from the result files, so a number is best changed at its source; the README of each folder
names the generator.
