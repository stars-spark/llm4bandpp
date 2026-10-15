# Results index

One entry per table, figure and result in the text, in the order of the paper and its supplement: what is reported,
the registered experiment, and the commands, scripts, versions and data of each level.

## How to read this index

Levels are those of `README.md`: Level 1 regenerates a table or figure from the result files in this package, Level 2
recomputes a number and its interval from per-call, per-run or per-answer data, and Level 3 reruns the experiment
(training, designer calls or closed-loop calls). Commands run from the package root after the placeholder `sed` of
`docs/PACKAGE.md`, with Python 3 and `requirements-level1.txt` (training: `docs/requirements-train.txt`). Details are in
`docs/OFFLINE.md`, `docs/DESIGNER.md` and `docs/TESTBED.md`.

In the lists of inputs, `R/` is `experiments/results/`, `T/` is `external/testbed/results/` and `D/` is
`scripts/alphartc/deploy/`; `*` stands for a set of files or run directories. Commands spell paths in full.

Entries use the paper's names; `docs/GLOSSARY.md` defines every internal name that appears below: arms
(`arm_ch_x`, the deployed estimator; `gcc_pt125_c200`, the Python GCC reference), envelope versions (0, v4, v6),
collector versions, the 5 kb/s floor and the status letters R, D, N, P and – of the paper's tables. BA is balanced
accuracy. In the closed-loop
designer tests, LLM, NAME, DIST and NONE label the designer's mapping, name matching, distribution matching and no
adaptation, and CLEAN the true mapping.

Each entry cites experiment ids of `registry/registry_summary.md`, with the texts in `registry/registry_summary.jsonl`
and the pre-registration notes in `registry/preregistrations/` (`README.md`, "Registry and status letters"); their
numbers are the data events in `experiments/registry.jsonl`. A few numbers exist only in the text of our full registry
(a note or a registration text), which the package does not include;
such entries say "recorded in the registry; raw data not included" or name the result file that holds the number.
Judge commands rewrite their result file in place (with identical content unless noted), so run them on a copy.

Each closed-loop batch names its run script, `scripts/alphartc/run_staleness_once_twocontainer_midsnap_vNN.sh`, and
the component versions that run script installs into the testbed: the receiver entry point
`scripts/alphartc/BandwidthEstimator_staleness_vNN.py`, the arms
`D/online_llm_arms_v*.py` (and `D/fixed_*.py`, `D/echo_x_v2.py`), the probing envelopes `D/safety_envelope_v*.py`, the
collectors `D/spec_collector*.py` and, where a batch loads several checkpoints, the weight check
`D/seed_weight_check_vN.py`. To rerun a result, use the versions listed for it (`docs/TESTBED.md`). A run script
installs every envelope and collector version that existed when it was written (envelope v6 from run script v17 on,
collector v7 from v19 on); which one an arm uses is set per job by `STALENESS_COLLECTOR`, `STALENESS_ENVELOPE` and
`STALENESS_MIN_BPS_FLOOR` in the batch's job list (`T/<batch>/main/jobs.json` or `T/<batch>/jobs_main*.json`), and the
entries below quote those settings. `arm_ch_x` uses the weights `D/ch_estimator_v1/ckpt/ch.pt` unless
`STALENESS_CH_CHECKPOINT` names another file of that directory. The appendix at the end maps every shipped run script to
its batches and results.

The challenge baseline is `R/switch_deploy_v1/models/schaferct_public.onnx`, which the code calls `schaferct_public`
and `Schaferct(public)`; `docs/GLOSSARY.md` gives its origin.

`README.md`, "Not included", lists what the package lacks. Among those items are all checkpoints with the multi-scale
encoder (the no-LLM multi-scale variant, the LLM variants, the Mamba arm): `D/nl_estimator_v1/ckpt/` is not shipped.

## Main text: figures and tables

### Fig. 1. System overview

- Reports: no measured number. The adapter excerpt (receiving rate = `mbpsRecvRate` × 10^6, queueing missing) is the
  hosted designer's answer for SRT in `R/realtel_scale_v1/llm_deepseek.jsonl`; the grid is one real observation.
- Registry: realtel-scale-v1 (excerpt), hd720-closedloop-v1 (observation).
- Level 1: `python3 scripts/paper/make_fig1_collector_grid_v1.py --palette greys --lighten 0.4 --out papers/revision-v2/figs/src/collector_grid_greys_light.tex`,
  then `(cd papers/revision-v2/figs/src && pdflatex fig_llm_position.tex)`. Input of the grid:
  `T/hd720-closedloop-v1/main/hd_c2__johnny__pp__r1/obs_arm_llm4bandpp_x__hd_c2__d0__r1__vjohnny.jsonl.gz`.
- Limits: the batch behind the observation used a run script that is not in the package.

### Fig. 2. Probing envelope

- Reports: the three states and rules of Section III-E (growth to 1.5R + 10 kb/s, 0.9C during a 10 s hold that doubles
  up to 80 s, release after 5 s above C, at most one cut per second; † rules from a shadow GCC).
- Code: `D/safety_envelope_v6.py` (deployed, with the † rules), built on `D/safety_envelope_v4.py` (without them); the
  constants are at the top of both files. The shadow GCC is `D/gcc_pt125_c200_v1.py`.
- Registry: compete-flow-v2 and hd720-closedloop-env6-v1 (the † rules, Section S7).
- Level 1: `(cd papers/revision-v2/figs/src && pdflatex fig_envelope.tex)`.

### Table I. Offline accuracy

- Reports: MSE per scenario and macro MSE on the 870 validation calls and the 712-call subset; deployed estimator 5.795
  (seed 1 of 5.87, 5.80, 5.79), supervised MLP 2.345, receiving-rate echo 14.719 (Low BW 0.13).
- Registry: main-table-unified-v1, table1-ch-paired-v1 (deployed row), offline-trivial-baselines-v1 (echo,
  exploratory), decision-transformer-baseline-3seed-50k-gpu-server-1-v1, supervised-mlp-baseline-3seed-50k-v1,
  repro-mre4-1240000 (one-token variant).
- Level 1: `python3 scripts/paper/make_tables_v2.py`, function `table_offline` → `papers/revision-v2/tables/table_offline.tex`;
  reads `R/main_table_unified_v1/result.json`, `R/offline_trivial_baselines_v1/result.json`, `R/table1_ch_paired_v1/result.json`.
- Level 2:
  - `python3 scripts/arb/main_table_unified_v1.py`. Inputs: `R/arb_perstep_dump_v1/perstep.npz` (Pioneer, challenge baseline,
    Schaferct-R, MLP), `R/llm4bandpp_perstep_dump_v1/perstep_llm4bandpp.npz`,
    `R/llm4band_conf_perstep_dump_v1/perstep_llm4band_conf.npz`,
    `R/main_table_unified_v1/extra/Decision Transformer (average of three seeds, target p90).npz`, `R/_deleak.json`.
  - `python3 scripts/arb/offline_echo_row_v1.py`. Inputs: `perstep.npz`, `_deleak.json`.
  - `python3 scripts/paper/table1_ch_rows_v1.py`. Inputs: the three per-step exports above, `R/_deleak.json`,
    `R/nl_2x2_v1/eval/CHs0.json`, `CHs1.json`, `CHs2.json`.
- Level 3: rebuild the 870 calls and re-evaluate the deployed checkpoints and the MLP (`docs/OFFLINE.md`, re-evaluation);
  retrain cell C-H (`docs/OFFLINE.md`, retraining). Per-step exports of the other rows:
  `scripts/arb/arb_perstep_dump_v1.py` (models in `R/switch_deploy_v1/models/`, MLP checkpoints in
  `experiments/results/supervised-mlp-baseline-3seed-50k-v1/seed*/`), `scripts/baselines/train_decision_transformer.py` and
  `scripts/baselines/dt_perstep_dump_v1.py`, `scripts/baselines/train_supervised_mlp.py`.
- Limits: the LLM4Band row needs the conference checkpoint and the one-token row a multi-scale checkpoint; neither is
  distributed, so both rows can be recomputed only from their per-step exports.

### Table II. Two LLM positions

- Reports: per step, pre-trained against randomly initialized, both trained in full: +2.2% [−4.0, +8.4]. Designer, real
  against masked names: hosted 32 vs 24 of 32 (six of the eight misses cut off at the token limit), open 32B 36 vs 1 of
  40, open 14B 27 vs 1 of 40.
- Registry: llm-pretraining-fulltrain-fourth-arm-3seed; obsschema-llm-v1 (`obf_unparsed_truncated` = 6 in its data
  event); obsschema-openreason-newschema-v1.
- Level 1: `make_tables_v2.py`, function `table_position` (reads the data events).
- Level 2:
  - `python3 scripts/arb/perstep_position_ci_v1.py`. Inputs: `R/pretrained_fulltrain_fourth_arm/raw/PFs*_50000.json`,
    `RIs*_50000.json`, `R/llm_indispensability/paper_data/raw/LLMs*_50000.json`, `NLs*_50000.json`,
    `experiments/registry.jsonl`.
  - `python3 scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py old` (hosted row). Inputs:
    `R/obsschema_v1/llm_test.jsonl`, `transforms_test*.json`, `eval_test*.json`, `judge_test*.json`, `groups.json`,
    `open_qwen32b.jsonl`, `R/openreason_v1/out_r1_*.jsonl`, `parse_r1_*.json`.
  - `python3 scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py new` (open rows). Inputs:
    `R/obsschema_rt_openreason_v1/out_rt_r1_*.jsonl`, `transforms_rt_r1_*.json`, `eval_rt_r1_*.json`,
    `judge_rt_r1_*.json`, `groups.json`.
- Level 3: per step, not possible from the package (the estimator files and checkpoints of the LLM variants are not
  included). Designer: `scripts/coldstart/obsschema_llm_v1.py test` (hosted); open models with
  `scripts/arb/vllm_generate_v2.py` on `R/obsschema_rt_openreason_v1/prompts.jsonl` and `R/openreason_v1/prompts.jsonl`
  (`docs/DESIGNER.md`, part b). New mappings must be replayed on the challenge calls (`scripts/arb/obsschema_v1.py eval`,
  `scripts/arb/obsschema_rt_offline_v1.py eval`) with `schaferct_public.onnx` (the challenge baseline).

### Table III. Cost per decision

- Reports: deployed 0.68 M parameters, 0.0014 GFLOPs, CPU p50/p95 0.07/0.08 ms, GPU 0.12/0.12 ms, 0.01 GB; one-token
  LLM 465 M, 0.62 GFLOPs, 38.7/40.0 and 17.3/18.0 ms, 985 mJ, 1.8 GB; LLM4Band 32/46 and 8.4/11.1 ms, 594 mJ, 1.8 GB;
  hosted designer 58 s per stack (0.017 USD); open 32B 15 s; the adapter 0.33 µs per step.
- Registry: client-hw-ch-v1 (deployed and one-token rows), client-hw-hcq-v1 (LLM4Band row, arm `full_conf`),
  realtel-scale-v1 (`wall_median_s` 58.3, `cost_median_usd` 0.0173), designer-cost-v1 (exploratory).
- Level 1: `make_tables_v2.py`, function `table_cost` (through `make_tables_v1.table6`). Inputs:
  `R/client_hw_ch_v1/measurement.json`, `R/client_hw_ch_v1/flops.json`, `R/client_hw_hcq_v1/measurement.json`,
  `R/client_hw_hcq_v1/qwen25_0p5b_config.json`, `R/client_hw/flops.json`, `R/hcq_encoder_vectorized_v2/measurement.json`,
  `R/hcq_encoder_vectorized_v2/equivalence.json`, `R/switch_llm_latency_budget_v1/latency_result.json`.
- Level 2: `python3 scripts/paper/flops_ch_v1.py` rewrites `R/client_hw_ch_v1/flops.json` byte-identical (1 356 800
  FLOPs, 683 160 parameters; loads `D/ch_estimator_v1/ckpt/ch.pt`). Hosted wall time and cost:
  `python3 scripts/coldstart/realtel_scale_v1.py judge` prints them from `R/realtel_scale_v1/llm_deepseek.jsonl`.
  Designer cost: `R/designer_cost_v1/cost_table.md` (adapter execution 0.33 µs per step; the open 32B distillation
  handled 21 stacks in 5 min 8 s on two V100S GPUs, about 15 s per stack) and the per-call wall times and token counts of
  `R/designer_cost_v1/timed_deepseek.jsonl`.
- Level 3: `python3 scripts/measure_client_hardware_v5.py --code scripts/alphartc/deploy/nl_estimator_v1/src --stats experiments/results/client_hw_hcq_v1_public/input_stats_mre4.json --config QWEN/config.json --out OUT.json --arms ch,hcq,full_conf --devices cpu,cuda:0`,
  with `QWEN` a Qwen1.5-0.5B directory. We checked `--arms ch --devices cpu` in a copy of the package (for this arm the
  `--config` value is not read). The LLM arms use random weights of the same architecture, as in our runs. The arm `nl`
  needs the multi-scale checkpoint, which is not distributed.
- Limits: the three designer rows are entered by hand in `table_cost` from the two registry entries above: designer-cost-v1 (the
  adapter and the open 32B) and realtel-scale-v1 (hosted model: median wall time 58.3 s at six concurrent calls, 0.017
  USD at the provider's peak price). Latencies depend on the machine (ours: Core i9-13900H, RTX 4080 Laptop GPU).

### Table IV. Designer tests

Level 1 for all rows: `make_tables_v2.py`, function `table_designer`; it reads the data events and
`R/realtel_adapter_v1/revise_v3.json`, `R/realtel_scale_v1/namehide/judge.json`, `R/realtel_e2e_v1/judge.json`
(rescored on 42 cells by `e2e_v3`) and `R/hd720_designer_ch_v1/rejudge_fail0.json`. Level 2 commands are those of
`docs/DESIGNER.md`, part a; inputs in brackets (all under `R/` unless marked `T/`). Level 3 hosted calls follow
`docs/DESIGNER.md`, part b.

| Row (status) | Reported | Registry | Level 2 [inputs] | Level 3 |
|---|---|---|---|---|
| Synthetic, 4 held out (R) | 32/32; unit-aware matcher 32/32; name and distribution 0/32 | obsschema-llm-v1, obsschema-strong-baseline-v1 | `obsschema_rt_openreason_judge_offline_v1.py old` [`obsschema_v1/`]; `scripts/arb/obsschema_strong_baseline_v1.py judge` | `obsschema_llm_v1.py test`, replay on the challenge calls (challenge baseline) |
| 9 held out, open 32B (N) | 60/72 vs 71/72, −0.15 [−0.24, −0.08] | obsschema-strong-baseline-v1 | `obsschema_strong_baseline_v1.py judge` [`obsschema_strong_baseline_v1/eval_*_unitname.json`, `judge.json`, `matcher_sha256.txt`, `obsschema_v1/eval_test.json`, `eval_test_r1_32b.json`, `groups.json`, `obsschema_rt_openreason_v1/eval_rt_r1_32b.json`, `groups.json`] | matcher `scripts/arb/unitname_v1/unit_name_match.py`, replay |
| 7 specifications (P) | BA 1.000 vs 0.756 TF-IDF, +0.24 [+0.13, +0.41] | realtel-adapter-v1 (ground truth revised post hoc; +0.286 as registered) | `scripts/coldstart/realtel_revise_v1.py` [`realtel_adapter_v1/llm_test_deepseek.jsonl`, `truth_v2.json`, `baselines.json`, `strong_baselines/*`, `out_open_r1_*.jsonl`] | `realtel_adapter_v1.py llm test` |
| field names hidden (R) | 1.000 vs 0.756 | realtel-namehide-v1 | `realtel_namehide_v1.py judge` [`realtel_adapter_v1/namehide_v1/llm_hidden_deepseek.jsonl`, `truth_v3.json`, `strong_baselines/*`] | `realtel_namehide_v1.py llm` |
| 12 client stacks (R) | 0.920 vs 0.560 Cupid, +0.36 [+0.27, +0.45] | realtel-scale-v1 | `realtel_scale_v1.py judge` [`realtel_scale_v1/llm_deepseek.jsonl`, `sources.json`, `scores_*.json`, `truth_sens_round1.json`] | `realtel_scale_v1.py llm` |
| generic LLM matcher (R) | 0.920 vs 0.719, +0.20 [+0.12, +0.31] | llm-schema-match-baseline-v1 | `llm_schema_match_v1.py judge` [`llm_schema_match_v1/llm_generic.jsonl`, `realtel_scale_v1/`] | `llm_schema_match_v1.py llm` |
| fields then units, two calls (N) | 0.920 vs 0.966, −0.046 [−0.092, −0.001] | llm-twostep-match-v1 | `llm_twostep_match_v1.py judge` [`llm_twostep_match_v1/llm_twostep.jsonl`, `realtel_e2e_v1/runs/*`] | `llm_twostep_match_v1.py llm` |
| stacks, names hidden (R) | 0.947 vs 0.560, +0.39 [+0.30, +0.46] | realtel-scale-namehide-v1 | `realtel_scale_namehide_v1.py judge` [`realtel_scale_v1/namehide/llm_deepseek.jsonl`, `sources_hidden.json`] | `realtel_scale_namehide_v1.py llm` |
| real software, 42 cells (P) | 1.000 vs 0.762 Sim. Flooding, +0.24 [+0.13, +0.38] | realtel-e2e-v1 (ground truth revised post hoc; 48 cells and +0.333 as registered) | `realtel_e2e_v1.py judge`, then `make_tables_v2.py` [`realtel_e2e_v1/runs/*/cap.pcap` and telemetry of 24 runs] | `scripts/realtel_e2e/run_e2e_v1.sh` (Chrome, iperf3, tcp_info, GStreamer) |
| closed loop, challenge baseline downstream (R) | 1.16 vs 6.01 name, +4.85 [+4.11, +5.60] | obsschema-closedloop-v2 | `python3 scripts/paper/make_fig_closedloop_designer_v2.py` [`T/obsschema-closedloop-v2/`] | Fig. 3(c) |
| multi-scale variant downstream (N) | 2.55 vs 2.87 distribution, +0.32 [−0.62, +1.16] | obsschema-closedloop-nl-v1 | read `mean_dev`, `delta`, `ci90` and `severe_loss` of [`T/obsschema-closedloop-nl-v1/result_v1.json`]; its per-run files are not shipped | `D/obsschema_rt_nl_v1.py`, run script v17, `arm_nl_schema` (`D/fixed_schema_nl_v1.py`, collector v6, envelope v6); needs the multi-scale checkpoint |
| deployed system, 720p (P, N) | 69.4 vs 65.2 name, +4.17 [−0.37, +8.69]; as registered +2.26 [−2.72, +6.42] | hd720-designer-ch-v1 | snippet of "Section V-E. In closed loop" [`hd720_designer_ch_v1/runs_full.jsonl`]; `hd720_designer_ch_v1/rejudge_fail0.json` | `D/hd720_designer_ch_v1.py`, run script v25, `arm_ch_schema` (`D/fixed_schema_ch_v1.py`, collector v6, floor, envelope v6) |
| telemetry only, VMAF (N) | 76.5 vs 46.0 distribution, +30.55 [+21.72, +39.45] | hd720-designer-tel-v2 | the same snippet [`hd720_designer_tel_v2/runs_full.jsonl`] | `D/hd720_designer_tel_v2.py`, run script v27 |
| telemetry only, utility deviation (N) | 3.93 vs 24.70, +20.77 [+12.72, +27.57] | hd720-designer-tel-fid-v1 | the same snippet [`hd720_designer_tel_fid_v1/runs_full.jsonl`] | `D/hd720_designer_tel_fid_v1.py`, run script v27 |
| browser getStats only (R) | 0.197 vs 0.463 Cupid mapping, +0.27 [+0.14, +0.37] | realtel-closure-v2 | `scripts/realtel_e2e/closure_v2.py judge`, needs onnxruntime [`realtel_closure_v1/design_frozen.py`, `design_open_frozen.py`, `v2/runs/*/cap.pcap`, `stats.jsonl`, `realtel_adapter_v1/llm_test_deepseek.jsonl`, `strong_baselines/*`, `obsschema_rt_openreason_v1/evidence.json`; `data/audit_bench_v1/official_feature_spec.txt`; `R/switch_deploy_v1/models/schaferct_public.onnx`] | `closure_v1.py prompt`, `design 1`, `devcheck 1`, `freeze 1`; `scripts/realtel_e2e/run_closure_v1.sh` |

Limits: the hosted model's full answers were not stored, so every hosted row is rescored from the parsed mappings;
replays of synthetic schemas need the challenge calls; the 720p designer batches ship their per-run rows
(`runs_full.jsonl`) and judge outputs (`result_v1.json`), not their per-run logs. Telemetry-only batches run
`arm_ch_schema_tel` (`D/fixed_schema_ch_v2.py`): the deployed estimator, collector v6, 5 kb/s floor, envelope v4, no
shadow GCC.

### Fig. 3. Designer by method

- Registry: realtel-scale-v1, llm-schema-match-baseline-v1, llm-twostep-match-v1, open-sampling-variance-v1,
  realtel-e2e-v1, obsschema-closedloop-v2.
- Level 1: `FIG_OUT=$PWD/papers/revision-v2/figs/fig_designer_three.pdf python3 scripts/paper/make_fig_designer_v6.py`
  (data from `bar_rows` and `cl_cells` of `scripts/paper/make_fig_designer_v4.py`). Inputs: the data events,
  `R/open_sampling_variance_v1/summary.json`, `R/realtel_e2e_v1/judge.json`, `R/realtel_scale_v1/out_open_r1_32b.jsonl`,
  `out_open_r1_14b.jsonl`, `sources.json`, `T/obsschema-closedloop-v2/result_v1.json` and its 128 per-run files
  `T/obsschema-closedloop-v2/sd_*/arm_default_schema__*.json`.
- (a) BA on 12 stacks: designer 0.920, two-step 0.966, LLM match 0.719, R1-32B 0.89 and R1-14B 0.70 (means of three
  samples), seven matchers 0.328 to 0.560. Level 2: `realtel_scale_v1.py judge`, `llm_schema_match_v1.py judge`,
  `llm_twostep_match_v1.py judge`, `python3 scripts/coldstart/open_sampling_variance_v1.py score` (inputs
  `R/realtel_scale_v1/out_open_r1_*_sd*.jsonl` and `R/realtel_adapter_v1/out_open_r1_*.jsonl`, three seeds each).
- (b) 42 cells against packet captures: designer and two-step 42, LLM match 38, R1-32B 0.62, R1-14B 0.37, Similarity
  Flooding 32. Level 2: `realtel_e2e_v1.py judge` then `make_tables_v2.py` (`e2e_v3`); `llm_twostep_match_v1.py judge`
  (`e2e_count`); `open_sampling_variance_v1.py score` (`e2e_v3`).
- (c) Utility relative to the true mapping, 32/32/32/24 cells: mean |Δ| 1.16, 6.01, 7.62, 11.16; 10-point losses 0, 7,
  8, 8. Level 2: `python3 scripts/paper/make_fig_closedloop_designer_v2.py` recomputes the cells from the per-run
  results and checks `result_v1.json` (it also writes `fig_closedloop_designer.pdf`, which the paper does not use).
  Level 3: batch `D/obsschema_cl2_v1.py` (`evjobs OUT` and `jobs OUT`, each list run with `D/parallel_testbed_v1.py`,
  then `judge`), run script v10, entry `BandwidthEstimator_staleness_v7.py`, arm `arm_default_schema`
  (`D/fixed_schema_x_v1.py`: the challenge baseline behind envelope v4 without the † rules,
  collector v6, adapter set by `STALENESS_OBS_SCHEMA` and `STALENESS_OBS_MAP`); job lists
  `T/obsschema-closedloop-v2/jobs_main.json` and `jobs_ev.json`.

### Table V. Closed-loop VMAF

- Level 1: `make_tables_v2.py`, function `table_closedloop_v2`, readings from `closedloop_rows` grouped by
  `rows_v2` of `scripts/paper/make_fig_closedloop_forest_v2.py`. Inputs: the data events,
  `R/closedloop_steady_qoe_v1/summary.json`, `R/closedloop_steady_qoe_v1/realtrace_explore_v1.json`,
  `R/content320_ch_gcc_v1/result_v1.json`, `R/hd720_learned_baselines_v1/result_v1.json`,
  `R/hd720_learned_alone_v1/result_rejudge_env0.json` and the `runs_full.jsonl` of the GCC batches. The same function
  writes `table_closedloop.tex` (not in the paper), whose after-30-s, SSIM and freeze columns back Section V-F.
- Rows (all 720p rows: reference `gcc_pt125_c200` or a learned arm; `arm_ch_x` with collector v6 and envelope v6 unless
  noted). "Floor" is `STALENESS_MIN_BPS_FLOOR=1`.

| Row (status) | Reported | Registry | Batch script (`D/`) | Run script; arm configuration; weight check |
|---|---|---|---|---|
| First batch (R) | 4.6 [3.4, 5.7] | hd720-closedloop-ch-v1 | `hd720_ch_eval_v1.py` | v18; entry point v13, `online_llm_arms_v6.py`, no floor; none |
| Second batch (–) | 4.4 [3.5, 5.3] | hd720-echo-attr-ch-v1 | `hd720_attr_loss_v1.py` (`judge-attr`) | v20; entry point v15, `online_llm_arms_v8.py`, floor; echo arm `echo_x_v2.py`; none |
| Seeds 0 and 2 (R) | 6.1 [5.1, 7.1] | hd720-seeds-ch-v1 | `hd720_seeds_v1.py` | v21; entry point v15, floor, `ch_s0.pt`, `ch_s2.pt`; `seed_weight_check_v1.py` |
| Cellular, 7 windows (P) | 4.3 [3.2, 5.3] | hd720-realtrace-ch-v1 (revision: `R/hd720_realtrace_ch_v1/revise_both_invalid.json`) | `hd720_realtrace_v1.py` | v20; entry point v15, floor; none |
| High bandwidth (R) | 6.6 [5.9, 7.3] | hd720-highbw-ch-v1 | `hd720_highbw_v1.py` | v22; entry point v15, floor, `STALENESS_HIGH_BITRATE=1` for both arms; none |
| Random loss (R) | 8.9 [7.7, 10.2] | hd720-randloss-ch-v1 | `hd720_attr_loss_v1.py` (`judge-loss`) | v20; entry point v15, floor; none |
| 320×240 Johnny, Mobcal, Parkrun (–) | −0.2 [−0.5, 0.1]; 1.6 [1.1, 2.1]; 0.9 [0.2, 1.7] | content320-ch-gcc-v1 | `content320_ch_gcc_v1.py` | v29; entry point v17, floor; `seed_weight_check_v7.py` |
| Schaferct-R (R); Supervised MLP (–) | 0.5 [−0.3, 1.3]; 1.2 [0.3, 2.0] | hd720-learned-baselines-v1 | `hd720_learned_v1.py` | v24; entry point v16; all three arms floor and envelope v6, learned arms `fixed_x_v2.py` with `R/switch_deploy_v1/models/`; none |
| Schaferct-R, high bandwidth (R), no envelope (D) | 2.3 [1.7, 2.8]; 2.3 [2.0, 2.6] | hd720-hb-learned-env-v1, hd720-hb-learned-alone-v1 | `hd720_hb_learned_v1.py` | v24; entry point v16, floor, high bitrate, envelope v6 or envelope 0; none |
| Schaferct-R, no envelope (P) | 7.2 [5.5, 8.8] | hd720-learned-alone-v1 (pre-registration `registry/preregistrations/prereg_01.md`; revision, a no-envelope check in place of a shadow-GCC check these runs cannot pass: `R/hd720_learned_alone_v1/result_rejudge_env0.json`) | `hd720_learned_alone_v1.py` | v24; entry point v16, floor, envelope 0; none |

- Level 2: the judge functions on the shipped per-run rows. Run in a copy of the package, the snippet prints every
  Table V value above and the echo test of Section V-F. Its verdicts follow the non-inferiority rule of
  `hd720_ch_eval_v1.judge`; the registered verdicts of the cellular row (P, after revision) and of the high-bandwidth
  no-envelope row (D) follow their own criteria in the registry.

```python
import json, sys
sys.path.insert(0, "scripts/alphartc/deploy")
import hd720_ch_eval_v1 as H

def check(batch, arm, ref, arm_of=lambda r: r["arm"], keep=lambda r: r.get("valid")):
    d = "experiments/results/" + batch
    rows = [json.loads(l) for l in open(d + "/runs_full.jsonl")]
    V = {}
    for r in rows:
        if keep(r) and isinstance(r.get("vmaf"), (int, float)):
            V.setdefault((f"{r['cond']}__{r['video_id']}", arm_of(r)), []).append(r["vmaf"])
    conds = list(dict.fromkeys(r["cond"] for r in rows))
    C = json.load(open(d + "/contents.json"))["main_contents"]
    v, m = H.judge(V, [f"{c}__{x}" for c in conds for x in C], arm=arm, ref=ref)
    print(f"{batch} {arm} vs {ref}: {v}, D = {m['D']:.2f} [{m['ci90'][0]:.2f}, {m['ci90'][1]:.2f}]")

CH, GCC = "arm_ch_x", "gcc_pt125_c200"
for b in ("hd720_closedloop_ch_v1", "hd720_echo_attr_ch_v1", "hd720_seeds_ch_v1", "hd720_realtrace_ch_v1",
          "hd720_highbw_ch_v1", "hd720_randloss_ch_v1"):
    check(b, CH, GCC)
check("hd720_echo_attr_ch_v1", CH, "echo_x")
check("hd720_learned_baselines_v1", CH, "arm_schaferct_retrained_d")
check("hd720_learned_baselines_v1", CH, "arm_mlp_d")
job_arm = lambda r: r["job"].split("__")[2]
check("hd720_hb_learned_v1", "ch", "scr", arm_of=job_arm)
check("hd720_hb_learned_v1", "ch0", "scr0", arm_of=job_arm)
env0 = lambda r: all(x.startswith("Probing envelope version 6 check failed") for x in r["invalid_reasons"])
check("hd720_learned_alone_v1", CH, "arm_schaferct_retrained_d", keep=env0)
```

  Inputs: `R/<batch>/runs_full.jsonl` and `R/<batch>/contents.json` of the nine 720p batch directories. Arm names and
  the job keys of the high-bandwidth learned batch (`ch`, `scr`, `ch0`, `scr0`) are defined in `docs/GLOSSARY.md`. The
  320×240 rows: see "Low capacities" below.
- Level 3: `docs/TESTBED.md`, sections 2 to 7, with the batch script, run script and weight check of the row; profiles in
  `D/profiles/`, media recipes in `external/alphartc/LLM4Band/testmedia/`.
- Limits: the judges (`<batch>.py judge`) read per-run logs that are not shipped; the recomputation above starts from
  their per-run rows. The high-bandwidth rows need the patched sender binary (`D/patch_pcs_maxbitrate_v1.py`). The UCC 4G
  and Norwegian 3G windows must be rebuilt (`docs/TESTBED.md`, section 5).

### Fig. 4. Closed-loop dynamics

- Level 1: `python3 scripts/paper/make_fig_closedloop_v1.py` → `papers/revision-v2/figs/fig_closedloop_dynamics.pdf`
  (it also writes `fig_closedloop_forest.pdf`, which the paper does not use).
- (a) VMAF over call time, first 720p batch (hd720-closedloop-ch-v1, closedloop-steady-qoe-v1). Inputs:
  `T/hd720-closedloop-ch-v1/main/*/quality_*.json` and `decoded_timestamps_*.csv.gz` (72 and 70),
  `R/closedloop_steady_qoe_v1/summary.json` (the figure's ramp-up and steady differences must lie within 1 VMAF of it). Level 3: run script v18 (Table V, first row).
- (b) The median-VMAF cellular call of the deployed system (`arm_ch_x`) (hd720-realtrace-ch-v1). Inputs:
  `T/hd720-realtrace-ch-v1/main/hd_t7__johnny__ch__r3/control_arm_ch_x__hd_t7__d0__r3__vjohnny.log`,
  `decision_arm_ch_x__hd_t7__d0__r3__vjohnny.jsonl.gz`, `obs_arm_ch_x__hd_t7__d0__r3__vjohnny.jsonl.gz`. Level 3: run
  script v20.
- (c) Utility per capacity against LLM4Band at 100 to 400 kb/s, 320×240: behind the envelope +0.5 [−0.7, 1.7]
  (lowbw-ch-vs-conf-env6-v1), with 1% loss −1.3 [−2.4, −0.2] (lowbw-loss1-env6-v1), estimators alone −1.5 [−2.8, 0.0]
  (lowbw-chf-vs-conf-v1); the script also checks the 200 kb/s, 1% loss reading −5.5 (lowbw-loss200-ch-v1) against the registry. Inputs: `result_v1.json`
  of `R/lowbw_ch_vs_conf_v1/` (`claim2_env6`), `R/lowbw_loss1_env6_v1/`, `R/lowbw_chf_vs_conf_v1/`,
  `R/lowbw_loss200_ch_v1/`. Level 2 and 3: "Low capacities" below.

## Results in the text

### Section III-A. HCQ reward terms

- Reports: pooled correlation of the error term (uncapped) and the quality term, Pearson 0.05, Spearman 0.16; Pearson
  0.41 to 0.66 in each 1 Mb/s bin above 1 Mb/s; below 1 Mb/s Pearson −0.11, Spearman 0.14. Error term capped at 5 in
  training (0.8% of tuples).
- Registry: hcq-term-correlation-v1 (correlations; `rows_valid` 3 498 556 in its data event).
- Level 2: the correlations are in the data event only; the training pickle is not shipped. For the 0.8%, training prints the cap audit
  of `relabel_hcq_reward` (`D/nl_estimator_v1/src/IQL.py`) as a `REWARD_AUDIT` line, 26 732 capped of 3 498 556 valid
  tuples (0.76%). The count depends only on the balanced pickle and the cap of 5, so it is the same for every recipe
  trained on that pickle; the package holds the logs of the fully trained 15-token arms. The same snippet reads the
  time per update used in Table S2:

  ```python
  import datetime, glob, json, re
  for f in sorted(glob.glob("experiments/results/pretrained_fulltrain_fourth_arm/train_PFs*.log")
                  + glob.glob("experiments/results/randinit_fair/train_RIs*.log")):
      s = open(f).read()
      a = json.loads(re.search(r"REWARD_AUDIT (\{.*\})", s).group(1))
      T = {int(k): datetime.datetime.fromisoformat(t) for k, t in re.findall(r"Time steps: (\d+), Finish time: (\S+ \S+)", s)}
      print(f.split("/")[-1], a["tail_rows_capped"], a["rows_valid"], f"{a['tail_rows_capped'] / a['rows_valid']:.2%}",
            round((T[50000] - T[5000]).total_seconds() / 45000, 3), "s per update")
  ```

  Inputs: `R/pretrained_fulltrain_fourth_arm/train_PFs0.log` to `train_PFs2.log`, `R/randinit_fair/train_RIs0.log` to
  `train_RIs2.log`. Each prints 26732, 3498556 and 0.76%; the time per update is 1.415 to 1.442 s.
- Level 3: `scripts/arb/hcq_term_corr_v1.py OUT.json` on a balanced pickle built with
  `scripts/encoder/make_balanced_pickle_v1.py` (`docs/OFFLINE.md`); a rebuilt pickle holds other transitions than ours.

### Sections III, III-B and III-C. Sampling and parameter counts

- Reports: seven non-empty capacity bins hold 3.5 million tuples (the 3 to 4 Mb/s bin of our sample is empty); the deployed network has
  683 160 parameters (0.68 M against 465 M with the LLM).
- Registry: hcq-term-correlation-v1 (bin counts in its verdict), client-hw-ch-v1 (`ch_params`), client-hw-hcq-v1
  (465 029 287 parameters).
- Level 2: `python3 scripts/paper/flops_ch_v1.py` (parameter count). Split into the 150 fixed input scales, the encoder
  (0.16 M) and the head (0.53 M), checked in a copy of the package:

  ```bash
  python3 -c "import sys; sys.path.insert(0, 'scripts/alphartc/deploy/ch_estimator_v1'); import ch_estimator_v1 as C; a = C.load_agent('scripts/alphartc/deploy/ch_estimator_v1/ckpt/ch.pt', 'cpu'); print(sum(p.numel() for p in a.parameters()), {n: sum(p.numel() for p in m.parameters()) for n, m in a.named_children()})"
  ```

  It prints 683160, `stateencoder` 156672 and `bwe_head` 526337; the remaining 151 are the 150 scales and the policy's
  log standard deviation.
- Level 3: `scripts/encoder/make_balanced_pickle_v1.py --skip-bins 3-4` rebuilds the bins and the sample (`docs/OFFLINE.md`).

### Section III-E. Collector discrepancies and audio

- Reports: with loss counted over the primary and retransmission sequence spaces together, replayed estimates of 2056 to 7602 kb/s, against 192 to 239 kb/s
  once corrected; the unreported audio stream is about 41 kb/s; restoring it raised the 400 kb/s utility of the
  estimator of our earlier version from 66.1 to 81.5.
- Registry: switch-deploy-collector-v5 (`pred_kbps_median_after10s`), testbed-sender-floor-audio-audit-v1,
  llm4bandpp-online-unlock-v1.
- Level 1: `R/switch_deploy_v5/replay_result.json`, `summary` → `v3` (loss over the primary and retransmission sequence spaces) and `v5` (per
  stream) → `pred_kbps_median_after10s`; the first three entries are the three ONNX estimators of the replayed bank
  (Pioneer, the challenge baseline, Schaferct-R): 6768, 2056, 7602 against 239, 192, 211. The other two numbers:
  data events only.
- Level 3: not possible from the package (the replayed receiver logs and the run scripts of these batches are not
  shipped). Collector code: `D/spec_collector_v5.py` (per-stream loss), `D/spec_collector_v6.py` (audio constant).

### Section V-A. Statistics: the 5.27-point band

- Reports: closed-loop margins of 6 VMAF and 5.27 utility points; 5.27 is three times the largest standard deviation of
  repeated identical runs.
- Registry: switch-closedloop-noise-v1: 18 runs, six cells of three
  identical runs (arms `switch_nn`, the learned switcher of our earlier version, `arm_pioneer` and the Python GCC `gcc`,
  each at 400 and 1000 kb/s); largest within-cell standard deviation of utility 1.756 (Pioneer at 400 kb/s).
- Level 2 (`R/switch_deploy_v2/noise_v1.json`, which also stores `max_within_cell_sd` and `threshold_3x_sd`):

  ```python
  import collections, json, statistics as st
  d = json.load(open("experiments/results/switch_deploy_v2/noise_v1.json")); S = collections.defaultdict(list)
  for r in d["runs"]: S[(r["arm"], r["profile"])].append(r["utility"])
  sd = max(st.stdev(v) for v in S.values()); print(round(sd, 3), round(3 * sd, 2))   # 1.756 5.27
  ```
- Level 3: not possible from the package (the batch driver and the run-script state of this batch are not included;
  see the appendix).

### Section V-B. Offline accuracy, first paragraph

- Reports: 5.795, 16.3% (95% interval 13.4% to 19.4%) below LLM4Band, 14.1% below the one-token variant, 18.1% below
  Schaferct-R; ranking holds on the 712 calls; MLP 2.345.
- Registry: table1-ch-paired-v1, main-table-unified-v1.
- Level 2: `python3 scripts/paper/table1_ch_rows_v1.py` (inputs as in Table I) writes `R/table1_ch_paired_v1/result.json`
  (`paired`).
- Level 3: as Table I.

### Section V-B. Capacity anchor and where the gain lies

- Reports: the anchor lowers macro MSE by 8.9%, from 6.386 to 5.819 (three seeds); without it, 9.7% below Schaferct-R's
  7.074; HCQ lowers it by 4.1% without the anchor (6.659 to 6.386) and 6.9% with it (6.252 to 5.819); Schaferct's
  network with our recipe 5.83 (1.16 million parameters); High BW underestimation rate e− 0.33 against 0.36 to 0.61; echo 0.13 in Low BW
  (exploratory), where the deployed estimator ranks fifth of seven; higher Low BW and Fluctuating overestimation rate e+ (Table S4,
  Section S6).
- Registry: anchor-ablation-v1, ablation-nl-enc-hcq-2x2-v1 (cells with the anchor), schaferct-arch-recipe-v1 (parameter
  count 1 157 528 in `registry/preregistrations/prereg_11.md`), offline-trivial-baselines-v1, main-table-unified-v1.
- Level 2: `python3 scripts/encoder/anchor_ablation_v1.py summarize` (inputs `R/anchor_ablation_v1/eval/A0l00s*.json`,
  `A0l04s*.json`, `R/nl_2x2_v1/eval/CBs0.json` to `CBs2.json`, `CHs0.json` to `CHs2.json`);
  `python3 scripts/encoder/finalize_scharch_v1_offline_v1.py` (inputs `R/schaferct_arch_recipe_v1/eval/SCHs*.json`,
  `R/schaferct_arch_recipe_v1/summary.json`, `R/nl_2x2_v1/eval/CHs*.json`); e− and e+ from Table S4. The 9.7%, 4.1% and
  6.9% are ratios of these means.
- Level 3: retrain with `--capacity_aux_weight 0.0` (with or without `--reward_lambda 0.0`) and Schaferct's network
  (`scripts/encoder/make_schaferct_arm_v1.py`), seeds 0 to 2 (`docs/OFFLINE.md`). The no-anchor λ = 0.4 seed-2 checkpoint
  is `D/ch_estimator_v1/ckpt/ch_a0s2.pt` (macro 6.356; CPU re-evaluation in `D/ch_estimator_v1/equiv/CHa0s2_cpu.json`).

### Section V-B. Sensitivity to λ

- Reports: macro MSE 6.25 at λ = 0, 5.45 at 0.8, level at 1.0; Low BW overestimation rises; at 720p λ = 0.8 is
  non-inferior to 0.4; at 100 to 400 kb/s without the envelope λ = 1 costs 4.7 utility points and λ = 0 matters little;
  behind the envelope no weight differs. Details in Section S6 below.
- Registry: ch-lambda-sweep-v1, hd720-lambda-ch-v1, lowbw-lambda-seeds-v1, lowbw-lambda-env6-v1.
- Level 1 and 2: `python3 scripts/encoder/ch_lambda_sweep_v1.py summarize` (inputs `R/ch_lambda_sweep_v1/eval/CHl*s*.json`,
  `R/nl_2x2_v1/eval/CB*`, `CH*`), then `python3 scripts/paper/make_fig_lambda_supp_v2.py` (Fig. S1). Closed loop: the
  snippet of Section S6.
- Level 3: offline `--reward_lambda X` (`docs/OFFLINE.md`); checkpoints `ch_l*.pt` in `D/ch_estimator_v1/ckpt/`;
  closed loop as in Section S6.

### Section V-C. Encoder and reward ablation

- Reports: multi-scale encoder with HCQ against the conference encoder with the conference reward, −8.1% (5.76 against
  6.27, five seeds; 90% interval 6.4% to 10.2%); HCQ on Low BW −5.0% (2.5% to 8.0%); main effects, seeds 0 to 2: HCQ
  −7.7% (6.5% to 9.1%), −6.9% with the conference encoder; multi-scale encoder +0.5% (−1.6% to +2.3%), Low BW +11.8% (4.1%
  to 23.5%); 5.82 against 5.80.
- Registry: ablation-nl-enc-hcq-2x2-v1, ablation-nl-hcq-lowbw-v1.
- Level 2: `python3 scripts/encoder/nl2x2_v1/judge_nl2x2_v1.py dry`. Inputs: `R/nl_2x2_v1/eval/CBs0.json` to `CBs4.json`,
  `CHs0.json` to `CHs2.json`, `MBs0.json` to `MBs2.json`, `MHreuse_s0.json` to `MHreuse_s2.json`, `MHs3.json`, `MHs4.json`,
  `R/llm_indispensability/paper_data/per_trace.csv`. The script reports the main effects as improvements (negative of
  the change in MSE).
- Level 3: `docs/OFFLINE.md`, retraining table (cells C-H, C-B, M-H, M-B); `scripts/encoder/nl2x2_v1/run_nl2x2_v1.sh` is
  the queue script we used. C cells: checkpoints in `D/ch_estimator_v1/ckpt/` (`ch.pt`, `ch_s0.pt`, `ch_s2.pt`,
  `ch_l00s*.pt`).
- Limits: M cells need the multi-scale checkpoints, which are not distributed; they can be retrained.

### Section V-D. Per step

- Reports: LoRA against no LLM +0.1% (−4.8% to +5.0%); pre-trained against random initialization, full: +2.2%
  [−4.0, +8.4] (Table II), LoRA: +2.7% [−0.2, +5.5] (Section S4); 39 ms against 0.07 ms per decision (Table III).
- Registry: llm-indispensability-mt-anchor-3seed, llm-pretraining-fulltrain-fourth-arm-3seed,
  llm-pretraining-value-randinit-fair-3seed, client-hw-ch-v1.
- Level 2: `python3 scripts/arb/perstep_position_ci_v1.py` (inputs as in Table II); prints all three intervals.
- Level 3: not possible from the package (LLM variants not included).

### Section V-D. At deployment: name masking and model size

- Reports: masking collapses the open models but not the hosted one (Table II); Qwen1.5-0.5B-Chat as designer BA 0.50 on the
  12 stacks; R1 distillations into Qwen 0.50 at 1.5B to 0.89 at 32B.
- Registry: obsschema-llm-v1, obsschema-openreason-newschema-v1, realtel-designer-scale-v1,
  realtel-scale-r1qwen-size-v1.
- Level 2: as Table II; `python3 scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py designer-scale` (inputs
  `R/realtel_designer_scale_v1/out_ds_*.jsonl`, `eval_ds_*.json`, `transforms_ds_*.json`, `judge.json`,
  `R/realtel_scale_v1/sources.json`, `namehide/sources_hidden.json`, `scores_*.json`); `python3 scripts/coldstart/r1qwen_size_v1.py score`
  (inputs `R/realtel_scale_v1/out_open_r1_{1p5b,7b}_sd*.jsonl`, `out_open_r1_14b*.jsonl`, `out_open_r1_32b*.jsonl`).
- Level 3: vLLM generation with `R/realtel_designer_scale_v1/prompts_designer_scale.jsonl` and
  `R/realtel_scale_v1/prompts_scale.jsonl` (`docs/DESIGNER.md`, part b; models in
  `R/designer_models_v1/models.json`).

### Section V-E. Protocol and ground truth

- Reports: 70 of 105 and 131 of 180 pairs with a different definition; the engineer agrees on 68 of 84 scored pairs,
  Cohen's κ 0.22; with the engineer's labels 0.824 against 0.615 for COMA (0.15 to 0.27).
- Registry: realtel-adapter-v1, realtel-scale-v1, gt-blind-expert-v1.
- Level 2: label counts printed by `realtel_revise_v1.py` and `scripts/coldstart/gt_engineer_sens_v1.py`; agreement and κ
  by the snippet in `docs/DESIGNER.md` (input `R/gt_blind_expert_v1/result.json`); `python3 scripts/coldstart/gt_engineer_sens_v1.py`
  (inputs `R/gt_blind_expert_v1/result.json`, `R/realtel_scale_v1/llm_deepseek.jsonl`, `sources.json`, `scores_*.json`).
- Limits: the engineer's filled sheet is not released (`scripts/paper/gt_blind_compare_v1.py` cannot be rerun).

### Section V-E. Synthetic schemas, real documentation, held-out stacks

- Reports: hosted 32 of 32 groups, distribution and name matching none, unit-aware matcher as well, open 32B 36 of 40
  newer groups and behind the matcher on 72; seven specifications correct in every order (post hoc); counterfactual
  rewrite followed in 33 of 33 cells; 12 stacks: 11 with scored features, 25 mappable, 24 unmappable, BA 0.920 against
  0.560; repeats 0.94 and 0.96, 92% of cells agreeing; names hidden 1.000 and 0.947; chosen field only, COMA 0.773 against
  0.940 (0.06 to 0.28); 0 of 72 false maps.
- Registry: obsschema-llm-v1, obsschema-strong-baseline-v1, obsschema-openreason-newschema-v1, realtel-adapter-v1,
  realtel-cfdoc-v1, realtel-scale-v1, realtel-repeat-v1, realtel-namehide-v1, realtel-scale-namehide-v1.
- Level 2: Table IV rows; `python3 scripts/coldstart/realtel_cfdoc_v1.py judge` (inputs
  `R/realtel_adapter_v1/cfdoc_v1/llm_cf_deepseek.jsonl`, `judge.json`, `truth_v3.json`); `python3 scripts/coldstart/realtel_repeat_v1.py judge`
  (inputs `R/realtel_repeat_v1/llm_repeat.jsonl`, `judge.json`, `R/realtel_scale_v1/llm_deepseek.jsonl`, `sources.json`,
  `scores_*.json`); `python3 scripts/paper/make_designer_per_stack_v1.py` (scored stacks and errors).
- Level 3: `realtel_cfdoc_v1.py llm`, `realtel_repeat_v1.py llm` (`docs/DESIGNER.md`, part b).

### Section V-E. Against LLM schema matching

- Reports: LLM match 0.719 with field accuracy 0.979 against 0.940; the second call lifts it to 0.966.
- Registry: llm-schema-match-baseline-v1, llm-twostep-match-v1. Level 2 and 3: Table IV rows.

### Section V-E. End to end on real software

- Reports: 42 of 42 cells; Similarity Flooding 32; open distillations 0.62 (32B) and 0.37 (14B); generic matcher 38 of 42
  (42 with two calls); value-rule lead +0.10 (0.02 to 0.18), direction only.
- Registry: realtel-e2e-v1, open-sampling-variance-v1, llm-twostep-match-v1, realtel-e2e-valuerule-v1 (pre-registration
  `registry/preregistrations/prereg_35.md`; result `R/realtel_e2e_valuerule_v1/judge.json`).
- Level 2: Table IV row; `open_sampling_variance_v1.py score`; `python3 scripts/realtel_e2e/e2e_valuerule_v1.py` (inputs
  `R/realtel_e2e_v1/runs/*`, `R/llm_schema_match_v1/llm_generic.jsonl`, `R/realtel_adapter_v1/llm_test_deepseek.jsonl`,
  `out_open_r1_*.jsonl`, `strong_baselines/*`, `R/realtel_e2e_valuerule_v1/judge.json`).
- Level 3: `scripts/realtel_e2e/run_e2e_v1.sh` records new captures; the designer answers are reused.

### Section V-E. Single-field features and the getStats derivation

- Reports: the 12 stacks expose 0 to 4 features as single fields; keeping only those raises macro MSE from 5.80 to 9.0 to
  23.3 (Pioneer 7.37); the derivation function fills six features and keeps the estimate closest to the capture-based one
  (Table IV; Section S8: 0.197, 0.463, 0.240).
- Registry: realtel-mask-offline-v2, realtel-closure-v2.
- Level 2: `python3 scripts/coldstart/mask_offline_local_v1.py` checks `R/realtel_mask_offline_v2/summary.json` from the
  runs `R/realtel_mask_offline_v2/M*.json` and `R/realtel_scale_v1/sources.json`; `closure_v2.py judge` as in Table IV
  (needs onnxruntime).
- Level 3: masked runs: `scripts/realtel_e2e/mask_offline_v1.py --v2` on a machine with the rebuilt 870 calls and
  `ch.pt` (`docs/OFFLINE.md`); derivation: `closure_v1.py` steps as in Table IV.

### Section V-E. In closed loop

- Reports: (1) challenge baseline downstream: 1.16 (signed +0.1) against name matching 6.01 (signed −1.5), 7
  cells with a 10-point loss (Fig. 3(c)). (2) Multi-scale variant behind the deployed envelope: name matching 7 cells
  with a 10-point loss; 720p deployed system: the designer breaks no call (a call breaks when its run fails the testbed's validity check, for
  example because video stopped arriving more than 8 s before the end, or yields no VMAF), no adaptation 4 of 20, distribution matching
  3; lead 4.2 VMAF. (3) Telemetry only: three batches; the designer's mappings break 1 of 60 calls, the true mapping 1
  of 24, name matching 17, distribution matching 11, no adaptation 46; the first test holds only after broken calls
  are scored as 0; the other two crossed their safety line (two cells on window hd_t3, one on hd_t5).
- Registry: obsschema-closedloop-v2, obsschema-closedloop-nl-v1 (`severe_loss`), hd720-designer-ch-v1, the first
  telemetry-only batch hd720-designer-tel-v1 (pre-registration `registry/preregistrations/prereg_28.md`; its registered
  verdict "inconclusive" and the revision "holds" are in `registry/registry_summary.md`), hd720-designer-tel-v2,
  hd720-designer-tel-fid-v1 (`breaks`, `severe`).
- Level 1: (2) `T/obsschema-closedloop-nl-v1/result_v1.json` (`severe_loss`: NAME 7); the `result_v1.json` of each 720p
  batch below and `R/hd720_designer_ch_v1/rejudge_fail0.json` (revised readings of hd720-designer-ch-v1 and
  hd720-designer-tel-v1).
- Level 2: `make_fig_closedloop_designer_v2.py` for (1). For the 720p batches, the per-run rows with the batch judges,
  checked in a copy of the package; it prints the broken calls per mapping (CLEAN 0/8, 0/8, 1/8 and LLM 0/20, 0/20, 1/20
  in the three telemetry-only batches; NONE 4/20 and DIST 3/20 in the deployed-system batch), the registered and revised
  verdicts of the first two batches (+2.26 [−2.72, +6.42] as registered and +4.17 [−0.37, +8.69] revised; telemetry
  only, inconclusive as registered and +28.79 [+16.79, +41.65] revised) and the readings of the other two batches,
  with their safety-line cells:

  ```python
  import collections, json, sys
  sys.path.insert(0, "scripts/alphartc/deploy")
  import hd720_designer_ch_v1 as DC, hd720_designer_tel_v1 as T1, hd720_designer_tel_v2 as T2, hd720_designer_tel_fid_v1 as TF
  R = "experiments/results/"
  runs = lambda b: [json.loads(l) for l in open(R + b + "/runs_full.jsonl")]
  label = lambda r: r["job"].split("__")[2].split("-")[-1]   # LLM, NAME, DIST, NONE or CLEAN
  for b in ("hd720_designer_ch_v1", "hd720_designer_tel_v1", "hd720_designer_tel_v2", "hd720_designer_tel_fid_v1"):
      n, broken = collections.Counter(), collections.Counter()
      for r in runs(b): n[label(r)] += 1; broken[label(r)] += not r["valid"]
      print(b, {m: f"{broken[m]}/{n[m]}" for m in sorted(n)})
  def zero(rs):   # revised scoring of the first two batches: a broken call of the mapping under test scores VMAF 0
      for r in rs:
          if not r["valid"] and label(r) != "CLEAN": r["valid"], r["vmaf"] = True, 0.0
      return rs
  show = lambda v, m: (v, round(m["delta"], 2), [round(x, 2) for x in m["ci90"]], m["severe"]) if "delta" in m else v
  for M, b in ((DC, "hd720_designer_ch_v1"), (T1, "hd720_designer_tel_v1")):
      print(b, "registered:", show(*M.decide(*M.stats(runs(b)))), "revised:", show(*M.decide(*M.stats(zero(runs(b))))))
  s = T2.stats(runs("hd720_designer_tel_v2")); print("hd720_designer_tel_v2", show(*T2.decide(s[0], s[1])))
  s = TF.stats(runs("hd720_designer_tel_fid_v1")); print("hd720_designer_tel_fid_v1", show(*TF.decide(s[0], s[1])))
  ```

  Inputs: `R/hd720_designer_ch_v1/runs_full.jsonl`, `R/hd720_designer_tel_v1/runs_full.jsonl`,
  `R/hd720_designer_tel_v2/runs_full.jsonl`, `R/hd720_designer_tel_fid_v1/runs_full.jsonl`. Summed over the three
  telemetry-only batches, the broken calls are LLM 0 + 0 + 1 of 60, CLEAN 0 + 0 + 1 of 24, NAME 5 + 6 + 6, DIST 5 + 3 + 3
  and NONE 16 + 15 + 15. The later two batches score broken calls as 0, as registered (`is_break` in their scripts).
- Level 3: batch scripts `D/obsschema_cl2_v1.py` (v10), `D/obsschema_rt_nl_v1.py` (v17), `D/hd720_designer_ch_v1.py`
  (v25), `D/hd720_designer_tel_v1.py`, `D/hd720_designer_tel_v2.py`, `D/hd720_designer_tel_fid_v1.py` (v27).
- Limits: the per-run logs of the 720p batches and the per-run files of obsschema-closedloop-nl-v1 are not shipped.

### Section V-F. Collector corrections

- Reports: with loss counted per stream, all 36 calls of four learned estimators at 100 to 200 kb/s complete, against 9
  of 36 without the correction (also in Section I); three of the four then use 15% to 29% of the link.
- Registry: switch-closedloop-lowbw-v5 (`valid_runs` 36, `rate_score`); the batch without the correction is
  switch-closedloop-perf-v1, on the same three profiles. The verdict text
  and the `perf_v1_same_cells` field of switch-closedloop-lowbw-v5 say "5 of 27" fixed-arm runs; 5 counts cells, not
  runs (five of the nine fixed-arm cells have a valid run and appear in `cells` of `cells.json`). Counting runs gives 9
  of 27, as a later note of that entry records; the paper reports the runs.
- Level 2: the four learned estimators are `arm_pioneer` (Pioneer), `arm_schaferct_public` (the challenge
  baseline), `arm_schaferct_retrained` (Schaferct-R)
  and `switch_nn` (the learned switcher of our earlier version, which picks one of the other estimators); each ran three
  times on `lowbw_100`, `lowbw_156` and `paper_low_200`. `cells.json` lists the valid runs and `CELLS_FAILED.txt` the
  failed ones:

  ```python
  import collections, json, re
  R = "experiments/results/"
  P = ("lowbw_100", "lowbw_156", "paper_low_200")
  L = ("switch_nn", "arm_pioneer", "arm_schaferct_public", "arm_schaferct_retrained")
  d = json.load(open(R + "switch_closedloop_perf_v1/cells.json"))
  ok = collections.Counter(r["arm"] for r in d["runs"] if r["profile"] in P and r["arm"] in L)
  bad = collections.Counter(a for a, p in re.findall(r"arm=(\S+) profile=(\S+) rep=\d+",
                                                     open(R + "switch_closedloop_perf_v1/CELLS_FAILED.txt").read())
                            if a in L and p in P)
  print({a: f"{ok[a]}/{ok[a] + bad[a]}" for a in L}, sum(ok.values()), "of", sum(ok.values()) + sum(bad.values()))
  # switch_nn 0/9, Pioneer 3/9, challenge baseline 2/9, Schaferct-R 4/9: 9 of 36
  d = json.load(open(R + "switch_closedloop_lowbw_v5/cells.json")); U = collections.defaultdict(list)
  for r in d["runs"]: U[(r["arm"], r["profile"])].append(r["rate_score"])
  print(len(d["runs"]), {k: round(sum(v) / len(v), 2) for k, v in sorted(U.items())})
  # 36 runs; rate_score 0.15 to 0.29 for all arms but Schaferct-R, which reaches 0.46 and 0.51 at 156 and 200 kb/s
  ```

  `rate_score` is the R term of the network utility (received video rate over the smaller of capacity and video cap).
  The Python GCC, which does not read our collector, completed all 9 of its calls in the uncorrected batch.
- Level 3: not possible from the package (the batch driver and the run-script state of these batches are not included;
  see the appendix).

### Section V-F. 720p calls, ramp-up and steady state

- Reports: ramp-up lead 15 to 32 VMAF in the first 30 s across the six 720p batches; time to 80% of the link at 1 and
  2 Mb/s: Python GCC 13 and 23 s, LLM4band++ 6 and 13 s, native GCC 4 and 5 s; after 30 s −0.5 to +2.1 VMAF (cellular
  −0.5, exploratory), SSIM 0.005 to 0.010 higher, frozen time within one percentage point, mean queueing within 6 ms, at most 0.5
  more freezes per minute.
- Registry: closedloop-steady-qoe-v1, realtrace-steady-explore-v1 (exploratory), gcc-native-calib-v1, and the batches of
  Table V.
- Level 2: `python3 scripts/paper/steady_state_qoe_v1.py run` (five GCC batches; inputs `R/<batch>/runs_full.jsonl` and
  `T/<batch>/ceilings.json`, `T/<batch>/main/*/quality_*.json`, `decoded_timestamps_*.csv.gz`) and, for the cellular
  batch, `python3 -c 'import sys; sys.path.insert(0, "scripts/paper"); import steady_state_qoe_v1 as S; print(S.batch("hd720-realtrace-ch-v1"))'`
  (reproduces `R/closedloop_steady_qoe_v1/realtrace_explore_v1.json`). SSIM and freezes: columns of
  `papers/revision-v2/tables/table_closedloop.tex` written by `make_tables_v2.py`. Native GCC: `R/gcc_native_calib_v1/summary.json`
  (`t_reach80_s`); its runs are not shipped.
- Level 3: native GCC: `scripts/gcc_native/run_gcc_native_v1.sh`, `scripts/gcc_native/chain_gcc_native_v1.sh`, then
  `scripts/gcc_native/gcc_native_calib_v1.py` (headless Chrome).

### Section V-F. Cellular windows (real traces)

- Reports: the 720p batches include two cellular windows (`hd_r1`, `hd_r2`); the separate cellular batch drew eight
  windows of UCC 4G and Chorus, and the revision drops `hd_t6`, where both arms lost every call to a 45 s outage, leaving
  seven: 4.3 [3.2, 5.3] (P, Table V); after 30 s −0.5 VMAF (exploratory); Fig. 4(b) shows one of its calls.
- Registry: hd720-realtrace-ch-v1, realtrace-steady-explore-v1 (exploratory), trace-replay-shaping-diag-v2 (replay
  fidelity, `R/trace_replay_shaping_diag_v2/result.json`).
- Level 2: the Table V snippet (all 16 cells, as registered); `R/hd720_realtrace_ch_v1/revise_both_invalid.json`
  (dropped cells, registered and revised readings); the cellular command of "720p calls, ramp-up and steady state".
- Level 3: batch `D/hd720_realtrace_v1.py`, run script v20, `arm_ch_x` with collector v6, envelope v6 and floor; windows
  in `D/profiles/hd720_real8/provenance.json` (the Chorus windows `hd_t5` and `hd_t6` are shipped, the UCC 4G windows are
  rebuilt with `D/make_hd720_real8_profiles_v1.py` as in `docs/TESTBED.md`, section 5).

### Section V-F. Shared bottleneck

- Reports: share 0.050 below GCC (−0.12 to 0.02), direction only; VMAF during competition 0.3 and 9.0 lower against TCP at
  2 and 3 Mb/s, 1.5 higher against a GCC call.
- Registry: compete-flow-ch-v1.
- Level 2: share in the snippet of "Low capacities" below; VMAF during competition: `vmaf_window` in
  `R/compete_flow_ch_v1/result_v1.json` (`by_arm_cond`, arms `ch` and `gcc200`). Inputs:
  `R/compete_flow_ch_v1/runs_full.jsonl`.
- Level 3: `D/compete_flow_ch_eval_v1.py` (`jobs`, `judge`), run script v18; `arm_ch_x` collector v6, envelope v6, no
  floor; job list `T/compete-flow-ch-v1/main/jobs.json`; competitors `D/bg_tcp_flow_v1.py` and a second GCC call.

### Section V-F. Envelope rewrites, echo, no envelope

- Reports: the envelope rewrites 77% of the deployed estimator's decisions in the learned-estimator batch; the echo gains
  1.4 against 4.4 VMAF over GCC; LLM4band++ stays 3.0 VMAF above it (1.9 to 4.1); with no envelope the MLP averages 7.7
  VMAF at 720p and the deployed estimator 74.6.
- Registry: hd720-learned-baselines-v1, envelope-rewrite-by-cond-explore-v1 (exploratory), hd720-echo-attr-ch-v1,
  hd720-learned-alone-v1.
- Level 2: the Table V snippet (echo test 2.97 [1.86, 4.13]; 4.38 − 2.97 = 1.4); rewrite share and no-envelope means,
  checked in a copy of the package:

  ```python
  import json, statistics as st
  R = "experiments/results/"
  rows = [json.loads(l) for l in open(R + "hd720_learned_baselines_v1/runs_full.jsonl")]
  print(st.mean(r["envelope_rewrite_frac"] for r in rows if r["arm"] == "arm_ch_x" and r.get("valid")))    # 0.767
  rows = [json.loads(l) for l in open(R + "hd720_learned_alone_v1/runs_full.jsonl")]
  for a in ("arm_ch_x", "arm_mlp_d"):   # runs whose only invalid reason is the envelope v6 check, as in the revision
      print(a, st.mean(r["vmaf"] for r in rows if r["arm"] == a and isinstance(r.get("vmaf"), (int, float))
                       and all(x.startswith("Probing envelope version 6 check failed") for x in r["invalid_reasons"])))
  ```
- Level 3: as the rows of Table V (v20 for the echo batch, v24 for the learned batches).

### Section V-F. High bandwidth and random loss

- Reports: with the cap at 20 Mb/s the sequences reach 12 and 16 Mb/s; two UCC 4G windows (means 6.6 and 10.5 Mb/s);
  above GCC in all 12 cells, +1.3 VMAF after 30 s; without the envelope 89.7 against 83.9 VMAF; random loss: above GCC in
  all eight cells.
- Registry: hb-calib-explore-v2 (exploratory), hd720-highbw-ch-v1, hd720-hb-learned-env-v1, hd720-hb-learned-alone-v1,
  hd720-randloss-ch-v1, closedloop-steady-qoe-v1.
- Level 2: `R/hb_calib_v2/summary.json` (`median_after6s_kbps`); window means in
  `D/profiles/hd720_hb/provenance.json`; cell differences `cell_diff` of `R/hd720_highbw_ch_v1/result_v1.json` and
  `R/hd720_randloss_ch_v1/result_v1.json`, recomputed by the Table V snippet; after 30 s: `steady_state_qoe_v1.py run`;
  89.7 and 83.9: `by_armkey` `ch0` and `ch` of `R/hd720_hb_learned_v1/result_v1.json`.
- Level 3: run scripts v22 (GCC batch) and v24 (learned batch), both with the patched sender (`docs/TESTBED.md`,
  section 3).

### Section V-F. Low capacities

- Reports: non-inferior to LLM4Band at 100 to 400 kb/s behind the envelope, with 1% loss and with no envelope (Fig. 4(c));
  with no envelope it needs the 5 kb/s floor at 100 kb/s, where every call failed without it; at 200 kb/s 6.0 points behind,
  27% more video, VMAF 48.8 against 41.9, queueing 233 against 98 ms (exploratory); 200 kb/s with 1% loss 5.5 points
  behind (fails); anchor-free policy 31 kb/s of video, 5 of 8 calls broken, 14.8 behind; against GCC with 1% loss −1.4
  (−2.6 to −0.1) at VMAF 46.3 against 45.6; 200 to 1000 kb/s no broken call, Johnny level with GCC.
- Registry: lowbw-ch-vs-conf-env6-v1, lowbw-loss1-env6-v1, lowbw-chf-vs-conf-v1, lowbw-ch-vs-conf-v1,
  lowbw-loss200-ch-v1, lowbw-noanchor-200-v1, content320-ch-gcc-v1, ch-startup-guard-smoke-explore-v1 (why a zero
  estimate stops the sender).
- Level 2: per-capacity means in `by_arm_cap` and `by_arm` of each `result_v1.json`; the tests, checked in a copy of the
  package. Arm keys (`ch6`, `cf0`, `a0`, `dep`, `gcc`, ...) are defined in `docs/GLOSSARY.md`.

  ```python
  import json, sys
  sys.path.insert(0, "scripts/alphartc/deploy")
  import content320_ch_gcc_v1 as M3, lowbw_ch_vs_conf_v1 as L, lowbw_chf_vs_conf_v1 as F
  import lowbw_lambda_mid_v1 as LM, lowbw_loss_v1 as L2, lowbw_noanchor200_v1 as NA, compete_flow_ch_eval_v1 as CF
  R = "experiments/results/"
  def util(batch, key=lambda r: (r["cap"], r["arm_key"])):
      U = {}
      for l in open(R + batch + "/runs.jsonl"):
          r = json.loads(l)
          if r["valid"] and r.get("utility") is not None: U.setdefault(key(r), []).append(r["utility"])
      return U
  show = lambda name, vm: print(name, vm[0], round(vm[1]["D"], 2), [round(x, 2) for x in vm[1]["ci90"]])
  show("behind the envelope", L.judge(util("lowbw_ch_vs_conf_v1"), "ch6", "cf6"))
  show("no envelope, no floor", L.judge(util("lowbw_ch_vs_conf_v1"), "ch0", "cf0"))
  show("no envelope, floor", F.judge(util("lowbw_chf_vs_conf_v1"), "ch0", "cf0"))
  show("envelope, 1% loss", LM.judge(util("lowbw_loss1_env6_v1"), "ch6", "cf6"))
  show("no anchor", NA.judge(util("lowbw_noanchor_200_v1", key=lambda r: (r["cond"].split("__")[0], r["arm_key"])), "a0", "ch0"))
  U = util("lowbw_loss200_ch_v1", key=lambda r: r["arm_key"])
  show("200 kb/s, 1% loss", L2.decide(U)); print("  deployed system - GCC", L2.diff_ci(U["dep"], U["gcc"]))
  rows = [json.loads(l) for l in open(R + "content320_ch_gcc_v1/runs.jsonl")]
  for c in M3.CONTENTS:
      V = {}
      for r in rows:
          if r["content"] == c and r["valid"] and r.get("vmaf") is not None: V.setdefault((r["cap"], r["arm_key"]), []).append(r["vmaf"])
      d = M3.diff_ci(V, M3.CAPS); print("320x240", c, round(d["D"], 2), [round(x, 2) for x in d["ci90"]])
  Sh = {}
  for l in open(R + "compete_flow_ch_v1/runs_full.jsonl"):
      r = json.loads(l)
      if r.get("share_valid") and r.get("share") is not None: Sh.setdefault((r["ccond"], r["arm"]), []).append(r["share"])
  v, m = CF.judge(Sh, arm="arm_ch_x", ref="gcc_pt125_c200"); print("shared link", v, round(m["S"], 3), m["ci90"])
  ```

  Inputs: `runs.jsonl` of `R/lowbw_ch_vs_conf_v1/`, `R/lowbw_chf_vs_conf_v1/`, `R/lowbw_loss1_env6_v1/`,
  `R/lowbw_noanchor_200_v1/`, `R/lowbw_loss200_ch_v1/`, `R/content320_ch_gcc_v1/`, and
  `R/compete_flow_ch_v1/runs_full.jsonl`. Video rate, VMAF and queueing at 200 kb/s: `by_arm_cap` of
  `R/lowbw_chf_vs_conf_v1/result_v1.json` and `R/lowbw_ch_vs_conf_v1/result_v1.json` (`cf0`); anchor-free video and
  breaks: `by_arm_cond` and `invalid_by_arm` of `R/lowbw_noanchor_200_v1/result_v1.json`; no broken call from 200 to
  1000 kb/s: all 27 runs of each arm in `R/content320_ch_gcc_v1/runs.jsonl` are valid.
- Rounding: the deployed system against GCC at 200 kb/s with 1% loss is −1.37 with interval [−2.579, −0.146] (registry
  and the snippet), which rounds to −2.6 to −0.1.
- Level 3 (job lists in `T/<batch>/jobs_main*.json`; LLM4Band arm `arm_llm4band_conf_x` from `D/online_llm_arms_v4.py`,
  collector v6, no floor, needs the conference checkpoint):

| Batch | Batch script (`D/`) | Run script | `arm_ch_x` settings | Weight check |
|---|---|---|---|---|
| lowbw-ch-vs-conf-v1, lowbw-ch-vs-conf-env6-v1 | `lowbw_ch_vs_conf_v1.py` | v18 | entry point v13, `online_llm_arms_v6.py`, envelope 0 or envelope v6, no floor | none |
| lowbw-chf-vs-conf-v1 | `lowbw_chf_vs_conf_v1.py` | v20 | entry point v15, `online_llm_arms_v8.py`, envelope 0, floor | none |
| lowbw-loss200-ch-v1 | `lowbw_loss_v1.py` | v28 | entry point v17, envelope 0 and envelope v6, floor; GCC arm | none |
| lowbw-noanchor-200-v1 | `lowbw_noanchor200_v1.py` | v29 | entry point v17, envelope 0, floor, `ch.pt` and `ch_a0s2.pt` | `seed_weight_check_v6.py` |
| lowbw-loss1-env6-v1 | `lowbw_loss1_env6_v1.py` | v29 | entry point v17, envelope v6, floor | `seed_weight_check_v7.py` |
| content320-ch-gcc-v1 | `content320_ch_gcc_v1.py` | v29 | entry point v17, envelope v6, floor; GCC arm | `seed_weight_check_v7.py` |

### Section VI. Discussion

- Reports: three other LLM uses did no better than simple rules (numbers in Section S9); an LLM settled all 38
  disagreements with the engineer.
- Registry: switch-llm-coldstart-v3, obsrepair-closedloop-v2, obsrepair-llm-v2, gt-blind-expert-v1, and the collector
  audits of Section S9.
- Level 2: `R/gt_blind_expert_v1_public/adjudication.json` (the 38 cells and their categories); others: data events and
  Section S9.

## Supplement

### Table S1. The twelve collector discrepancies

Typeset by hand, not generated. "Original" is the collector of our earlier version; its code is not in the package. Corrected collector
versions: `D/spec_collector.py` (collectors v1 to v3) and `D/spec_collector_v4.py` to `D/spec_collector_v7.py`; the
closed-loop batches of the main text use v6. Evidence per item:

- Items 1, 2 and 4: switch-deploy-collector-v1 and b0-slot-order-audit-v1 (5397 right shifts, 41 left: data event).
  Level 1: `R/switch_deploy_v1/V2_replay.json`, the replay of 43 archived receiver logs: `n_requests` 36 426 and
  `slot_order` (newest interval in slot 4 for all of them under the original collector), `legacy_short_mi_median_packets`
  1 against `new_short_mi_median_packets` 3, and `wraps` per log (36 of the 43 logs wrap; `logs_with_wrap` in the data
  event).
- Item 3: switch-deploy-collector-v1. Level 2 from the per-step export of the 870 calls (feature 5, the minimum seen
  delay, newest short slot):

  ```python
  import numpy as np
  d = np.load("experiments/results/arb_perstep_dump_v1/perstep.npz"); F, o = d["feat_short"], d["offsets"]
  first200 = mono = 0
  for i in range(870):
      x = F[o[i]:o[i + 1]]; ne = np.nonzero(x[:, 1] > 0)[0]
      first200 += bool(len(ne)) and np.isclose(x[ne[0], 5], 200.0); mono += bool(np.all(np.diff(x[:, 5]) <= 1e-9))
  print(first200, f"{first200 / 870:.1%}", mono)   # 657 75.5% 870: non-increasing in every call
  ```
- Item 5: recorded in the registry (registration of online-state-defects-diagnosis-and-fix-v29: the original collector divided the received bits by the interval in milliseconds, so
  its online maximum, 149.733, sat three orders of magnitude below the offline median below 0.3 Mb/s, 78 120 b/s); raw
  data not included.
- Item 6: recorded in the registry (a note of switch-deploy-collector-v1: over 1.758 million non-empty offline slots,
  (1 − loss ratio) × received packets matches the field in 0.07% of slots and the lost-packet count in 87.6%; the 87.6%
  is also in its verdict text); raw data not included. The check can be repeated on the rebuilt validation calls (`scen/`
  of `docs/OFFLINE.md`, every tenth call in sorted order, all ten slots):

  ```python
  import glob, json, numpy as np
  rows = []
  for p in sorted(glob.glob("scen/*/*.json"))[::10]:
      o = np.asarray(json.load(open(p))["observations"], dtype=np.float64)
      for s in range(10):
          n, loss, f11 = o[:, 10 + s], o[:, 100 + s], o[:, 110 + s]; m = n > 0
          rows.append(np.stack([n[m], loss[m], f11[m]], 1))
  n, loss, f11 = np.concatenate(rows).T
  same = lambda v: np.mean(np.isclose(v[np.isfinite(v)], f11[np.isfinite(v)], rtol=1e-6, atol=1e-6))
  print(len(n), same((1 - loss) * n), same(np.where(loss < 1, loss / (1 - loss) * n, np.nan)))
  ```
- Item 7: recorded in the registry (a note of switch-closedloop-perf-v1: the estimator received only video packets, true
  video share 1.0 and audio 0.0); raw data not included. The packaged observation logs show the same: the collector logs
  the true shares beside the constants (`truthful_media`: ten slots each of video, audio and probing shares), and in
  every step the video share is 0 or 1 and no audio or probing packet arrives:

  ```python
  import gzip, json
  f = "external/testbed/results/hd720-realtrace-ch-v1/main/hd_t7__johnny__ch__r3/obs_arm_ch_x__hd_t7__d0__r3__vjohnny.jsonl.gz"
  video, other = set(), 0
  for l in gzip.open(f, "rt"):
      m = json.loads(l)["truthful_media"]; video |= set(m[:10]); other += sum(x != 0 for x in m[10:])
  print(sorted(video), other)   # [0.0, 1.0] 0
  ```
- Item 8: recorded in the registry (a note of switch-deploy-collector-v1: the session templates closed the call after
  55 s, which is why the longest of the 811 archived receiver logs is 57 s); raw data not included.
- Item 9: switch-deploy-collector-v1 (37 zero-overhead runs at a median of 66.2 to 66.6 ms, in its verdict text) and
  switch-deploy-collector-v2.
- Item 10: closedloop-collapse-attribution-v1 (0.36%, `offline_f8_when_1pkt` in its data event). Level 2 from
  `perstep.npz` (one-packet windows of the newest short slot):
  `python3 -c "import numpy as np; F = np.load('experiments/results/arb_perstep_dump_v1/perstep.npz')['feat_short']; one = F[:, 1] == 1; print(np.mean(F[one, 8] == 0), np.median(F[one, 8]))"`
  prints about 0.0036 (0.36%) and 72.0 (ms).
- Item 11: switch-deploy-collector-v5; Level 1 as in Section III-E.
- Item 12: testbed-sender-floor-audio-audit-v1 (about 41 kb/s and 50.8 packets/s, in its data event and verdict text).
- Level 3: not possible from the package (archived receiver logs and the original collector are not included).

### Section S2. State encoder

- Reports: 515 088 encoder parameters, 220 500 in an unused module, 872 in an unused layer, 293 716 live; the corrected
  encoder of the LLM variant has 143 718 and its ablation gives −6.4% (4.6% to 8.5%), Low BW −27.4% (18.7% to 36.5%),
  HCQ −4.7%, encoder −0.2%.
- Registry: encoder-tsc-upgrade (515 088 and 293 716 in `params`), ablation-enc-hcq-2x2-v1, ablation-hcq-lowbw-v1.
- Level 1: the 143 718 is the `encoder_params` of the multi-scale cells of that ablation (encoder `ms15`), recorded at
  training time: `python3 -c "import json; print(json.load(open('experiments/results/enc_hcq_2x2_v1/markers/EVAL_MH_s0_COMPLETE.json'))['train_done']['models'])"`.
- Level 2: `python3 scripts/finalize_enc_hcq_2x2_v1_offline_v1.py` (input `R/enc_hcq_2x2_v1/per_call_metrics.csv`; compares
  with `R/enc_hcq_2x2_v1/result.json`). Encoder code: `D/nl_estimator_v1/src/module.py`, `D/nl_estimator_v1/src/dualEncoder.py`.
- Limits: the corrected-encoder runs cannot be retrained from the package (estimator files not included).

### Table S2 and Section S3. Training configuration and cost

- Reports: 683 160 parameters (0.16 M encoder, 0.53 M head, 150 fixed); one-token variant 8.61 M of 465 M trainable,
  7.57 M in LoRA; 464.9 M for the fully trained LLM arm; time per update 1.104 s and 1.45 s; peak memory 0.4 GiB,
  21 522 MiB, 22 460 MiB; GPU hours 15.3 and 20.1; 1.36 MFLOPs per decision and the FLOPs arithmetic.
- Registry: llm-pretraining-value-randinit-fair-3seed, llm-pretraining-fulltrain-fourth-arm-3seed,
  llm-as-sole-aggregator, ablation-nl-enc-hcq-2x2-v1, repro-mre4-1240000, client-hw-ch-v1, encoder-tsc-upgrade,
  encoder-d5-multitoken-transfer, llm-indispensability-mt-anchor-3seed.
- Level 2: parameter split by the snippet of "Sections III, III-B and III-C"; 1.36 MFLOPs by `flops_ch_v1.py`.
- 8.61 M and 7.57 M: counts from the architecture. LoRA of rank 16 on every linear layer of Qwen1.5-0.5B
  (`D/nl_estimator_v1/src/estimator.py`) adds r(in + out) parameters per layer, 7 569 408 in total; with the
  multi-scale encoder (515 088, encoder-tsc-upgrade) and the head (526 338, the same head as the deployed policy,
  including its log standard deviation) the variant trains 8 610 834. With `QWEN` a Qwen1.5-0.5B directory:

  ```python
  import json
  c = json.load(open("QWEN/config.json"))
  h, f, L, r = c["hidden_size"], c["intermediate_size"], c["num_hidden_layers"], 16
  kv = h * c["num_key_value_heads"] // c["num_attention_heads"]
  lora = L * r * (2 * (h + h) + 2 * (h + kv) + 2 * (h + f) + (f + h))   # q, o; k, v; gate, up; down
  print(lora, lora + 515088 + 526338)   # 7569408 8610834
  ```
- 464.9 M: 464 914 450 trainable parameters of the randomly initialized arm, in the registered criterion of
  llm-pretraining-value-randinit-fair-3seed (`registry/registry_summary.jsonl`). The same text gives 8 496 146 for the
  15-token LoRA arm, 8.50 M in Table S2.
- Time per update, peak memory, GPU hours: logs in `R/training_cost_v1/`. Time per update from the `Finish time` lines
  between updates 5000 and 50 000: the six 15-token LoRA runs of encoder-d5-multitoken-transfer, two per server
  (`gpu-server-2/encoder_mt_*.log`), give 1.100 to 1.110 s, the source of the 1.104 s; the three LoRA runs of
  llm-indispensability-mt-anchor-3seed, the arm whose parameter count Table S2 gives, give 1.174 to 1.318 s
  (`gpu-server-2/llm_indisp_LLMs*.log`). Full training: updates 100 to 200 take 145 s in the smoke runs of
  llm-pretraining-value-randinit-fair-3seed (`gpu-server-1/randinit_fair_smoke.log`) and of the fourth arm
  (`gpu-server-1/pf_fourth_arm_smoke/checkpoint_times.txt`), 1.45 s per update; their GPU memory samples
  (`gpu-server-1/randinit_fair_mem.log`, `gpu-server-1/pf_fourth_arm_smoke/mem_samples.txt`) peak at 22 460 MiB. The 0.4 GiB is the
  smoke-run peak of the C cells, 438 MiB (`gpu-server-2/nl2x2_smoke/peak.txt`). The 21 522 MiB of the LoRA arm was read from
  nvidia-smi during the runs and is recorded only in the registry. The GPU hours are 50 000 × 1.104 s = 15.3 h and
  50 000 × 1.45 s = 20.1 h. The training logs of the fully trained arms give 1.415 to 1.442 s per update between
  updates 5000 and 50 000 (snippet of Section III-A).

### Table S3 and Section S4. Fifteen-token variants

- Reports: per-scenario MSE of the four arms and the Mamba arm (means of three seeds), seed ranges, macro e+ 0.77 to 0.94
  against 0.46 for the one-token variant, 0.67 for the deployed estimator; the no-LLM multi-scale variant 5.797
  (926 888 parameters); the four 2×2 cells 6.25, 5.82, 6.33, 5.80 and Low BW 1.06, 1.02, 1.20, 1.13 (five seeds: 6.27 and
  5.76); the three per-step contrasts; seed spread up to 0.31; Mamba 5.674 against 5.797 (−2.1%), [−0.180, −0.058],
  threshold 0.152, e+ 0.930 against 0.869.
- Registry: llm-indispensability-mt-anchor-3seed, llm-pretraining-value-randinit-fair-3seed,
  llm-pretraining-fulltrain-fourth-arm-3seed, aggregator-mamba-control-v1, ablation-nl-enc-hcq-2x2-v1, client-hw-nl-v1
  (926 888), decision-transformer-baseline-3seed-50k-gpu-server-1-v1 and supervised-mlp-baseline-3seed-50k-v1 (baseline
  settings).
- Level 1: `python3 papers/revision-v2/supplement/make_supp_tables.py` → `papers/revision-v2/supplement/generated/tab_variants.tex`.
  Inputs: `R/llm_indispensability/paper_data/raw/LLMs*_50000.json`, `NLs*_50000.json`,
  `R/pretrained_fulltrain_fourth_arm/raw/PFs*_50000.json`, `RIs*_50000.json`, `R/aggregator_mamba_control_v1/MBs*_50000.json`,
  `R/main_table_unified_v1/result.json`, `experiments/registry.jsonl`. Deployed e+: Table S4.
- Level 2: `perstep_position_ci_v1.py`; `python3 scripts/finalize_aggregator_mamba_control_v1_offline_v1.py` (inputs
  `R/aggregator_mamba_control_v1/MBs*_50000.json`, `result_main.json`, `R/llm_indispensability/paper_data/raw/NLs*_50000.json`);
  `judge_nl2x2_v1.py dry` (2×2 cells).
- Level 3: not possible for these arms (estimator files and checkpoints not included); baselines:
  `scripts/baselines/train_decision_transformer.py`, `scripts/baselines/train_supervised_mlp.py`.

### Table S4. Over- and underestimation rates

- Level 1: `make_supp_tables.py` → `papers/revision-v2/supplement/generated/tab_eplus.tex`. Inputs:
  `R/main_table_unified_v1/result.json`, `R/offline_trivial_baselines_v1/result.json`, `R/nl_2x2_v1/eval/CHs1.json`.
- Level 2: `main_table_unified_v1.py` and `offline_echo_row_v1.py` print e+ and e− per row. Registry and Level 3: as Table I.

### Fig. S1 and Section S6. Reward weight

- Reports (offline): 6.25 at λ = 0, 5.45 at 0.8, 5.48 at 1.0, 5.82 at 0.4; Low BW e+ 0.59 to 0.78; without the anchor
  6.659 and 6.386, e+ 0.67 against 0.50; r_q between about 0.4 and 4.6 (exploratory).
- Reports (closed loop, seed 1, no envelope): λ = 1.0 breaks 8 of 12 calls, λ = 0 4, λ = 0.4 none; later 0.8 breaks 7
  and 0.6 2; seeds 0 and 2: 3, 9 and 1 of 24, registered endpoint +2.0 of 24 (−0.5 to 4.5), direction only; utility −4.7 (−5.6 to
  −3.8) at λ = 1.0 and +0.7 (−1.3 to 2.5) at λ = 0; −1.2 at λ = 0 with seed 1 (−1.4 to −0.9); behind the envelope +0.5
  (−0.6 to 1.5) and −0.05, no break in 36 calls; 720p λ = 0.8 −0.4 VMAF (−1.6 to 0.7).
- Registry: ch-lambda-sweep-v1, anchor-ablation-v1, hcq-rq-range-explore-v1 (exploratory), lowbw-lambda-ch-v2
  (registered repeat), lowbw-lambda-mid-ch-v1, lowbw-lambda-seeds-v1, lowbw-lambda-env6-v1, hd720-lambda-ch-v1.
- Level 1: `python3 scripts/paper/make_fig_lambda_supp_v2.py` → `papers/revision-v2/supplement/figS_lambda.pdf` (input
  `R/ch_lambda_sweep_v1/summary.json`).
- Level 2: offline as in Section V-B; closed loop, checked in a copy of the package (break counts per arm: count
  `valid` false in each `runs.jsonl`; arm keys `l04`, `l08`, `l06`, `l10` and `l00` give λ, with the seed in the key of
  lowbw-lambda-seeds-v1):

  ```python
  import json, sys
  sys.path.insert(0, "scripts/alphartc/deploy")
  import hd720_ch_eval_v1 as H, hd720_lambda_v1 as HL, lowbw_lambda_seeds_v1 as LS, lowbw_lambda_mid_v1 as M
  R = "experiments/results/"
  runs = [json.loads(l) for l in open(R + "hd720_lambda_ch_v1/runs_full.jsonl")]
  C = json.load(open(R + "hd720_lambda_ch_v1/contents.json"))["main_contents"]
  print(H.judge(HL.build_V(runs), [f"{c}__{x}" for c in HL.CONDS for x in C], arm="l08", ref="l04")[1]["D"])
  V, U = {}, {}
  for l in open(R + "lowbw_lambda_seeds_v1/runs.jsonl"):
      r = json.loads(l); V.setdefault((r["cap"], r["arm_key"]), []).append(0 if r["valid"] else 1)
      if r["valid"]: U.setdefault((r["cap"], r["arm_key"][:3]), []).append(r["utility"])
  print(LS.brk_judge(V)[1]["B"], M.judge(U, "l10", "l04")[1]["D"], M.judge(U, "l00", "l04")[1]["D"])
  for b, a in (("lowbw_lambda_ch_v2", "l00"), ("lowbw_lambda_env6_v1", "l10"), ("lowbw_lambda_env6_v1", "l00"), ("lowbw_lambda_mid_ch_v1", "l08")):
      U = {}
      for l in open(R + b + "/runs.jsonl"):
          r = json.loads(l)
          if r["valid"] and r.get("utility") is not None: U.setdefault((r["cap"], r["arm_key"]), []).append(r["utility"])
      print(b, a, M.judge(U, a, "l04")[1]["D"])
  ```
- Rounding: λ = 0 behind the envelope is −0.0498 (lowbw-lambda-env6-v1), which rounds to −0.05.
- r_q range: recorded in the registry (hcq-rq-range-explore-v1, exploratory: per-step video and audio quality scores of
  300 random training calls; its quantiles are in `registry/registry_summary.jsonl`); raw data not included. The scores
  are the `video_quality` and `audio_quality` arrays of each public training call (as read by
  `scripts/encoder/make_balanced_pickle_v1.py`), so the reading can be repeated on the challenge data.
- Level 3:

| Batch | Batch script (`D/`) | Run script | Checkpoints of `arm_ch_x` (collector v6, floor) | Weight check |
|---|---|---|---|---|
| hd720-lambda-ch-v1 | `hd720_lambda_v1.py` | v23 | `ch.pt`, `ch_l08s1.pt`; envelope v6 | `seed_weight_check_v2.py` |
| lowbw-lambda-ch-v2 (registered repeat) | `lowbw_lambda_ch_v2.py` | v26 | `ch.pt`, `ch_l10s1.pt`, `ch_l00s1.pt`; envelope 0 | `seed_weight_check_v3.py` |
| lowbw-lambda-env6-v1 | `lowbw_lambda_env6_v1.py` | v26 | the same; envelope v6 | `seed_weight_check_v5.py` |
| lowbw-lambda-mid-ch-v1 | `lowbw_lambda_mid_v1.py` | v28 | `ch.pt`, `ch_l08s1.pt`, `ch_l06s1.pt`; envelope 0 | `seed_weight_check_v4.py` |
| lowbw-lambda-seeds-v1 | `lowbw_lambda_seeds_v1.py` | v29 | `ch_s0.pt`, `ch_s2.pt`, `ch_l00s0.pt`, `ch_l00s2.pt`, `ch_l10s0.pt`, `ch_l10s2.pt`; envelope 0 | `seed_weight_check_v6.py` |

### Section S7. Freezes and envelope versions

- Reports: no freeze in 12 720p calls at up to 16 Mb/s with a fixed estimate; without the † rules the one-token variant led
  GCC by 7.9 VMAF (7.0 to 8.7) and took 0.28 more of a shared link (0.25 to 0.31); with them, 2.1 VMAF (0.8 to 3.3) and
  share −0.03 (−0.06 to 0.00).
- Registry: hd720-freeze-floor-v1, hd720-closedloop-v1, compete-flow-v1, hd720-closedloop-env6-v1, compete-flow-v2.
- Level 2: `R/hd720_freeze_floor_v1/result_v1.json` and `runs_full.jsonl` (`file_freeze_per_min`); the other four: data
  events only.
- Level 3: freeze floor: batch script `D/hd720_freeze_floor_v1.py`, run script v24, arm `fixed_env` (a fixed receiver
  estimate of 3 Mb/s, or 18 Mb/s with the high-bitrate sender for the 20 Mb/s cells), job list
  `T/hd720-freeze-floor-v1/main/jobs.json`. The four envelope batches used a run script that is not in the package (the
  registry texts name v13) and an LLM variant checkpoint that is not distributed.
- Rounding: the registered interval of hd720-closedloop-env6-v1 is [0.845, 3.280], which rounds to 0.8 to 3.3.

### Fig. S2 and Section S8. The deployment-time designer

- Fig. S2: `make_supp_tables.py` → `papers/revision-v2/supplement/generated/prompt_template.txt`, extracted from
  `TEMPLATE` and `FEAT` of `scripts/coldstart/realtel_adapter_v1.py` and checked against the hash prefix `d2467ef5dc35`.
  Request settings: `ask` in `scripts/coldstart/coldstart_rule_v1.py`; `R/designer_models_v1/models.json`.
- Per-source results (8 of 11 stacks, 12 errors on Agora, mediasoup, ns-3; 0.938 with the ns-3 cell unscored):
  `python3 scripts/paper/make_designer_per_stack_v1.py` (writes `R/realtel_scale_v1/per_stack.csv`); the per-stack table
  "released with the code" is `papers/revision-v2/supplement/generated/tab_designer_src.tex` (from `make_supp_tables.py`).
  Registry: realtel-scale-v1 (its recorded `sources_all_correct_all_pres` is 9, see `docs/DESIGNER.md`).
- Repeats (0.94, 0.96; +0.39, 0.30 to 0.46): realtel-repeat-v1 (pre-registration
  `registry/preregistrations/prereg_55.md`), `realtel_repeat_v1.py judge`. Size (0.500, 0 of 40; 0.50,
  0.55, 0.70, 0.89; 11 to 13 of 36): realtel-designer-scale-v1, realtel-scale-r1qwen-size-v1, commands of Section V-D.
  Browser (0.197, 0.463, 0.240; challenge baseline downstream): realtel-closure-v2, Table IV row.
- The baselines' unit and differencing rule: `scripts/coldstart/realtel_baselines_v2.py`. Differencing decided from the values alone changes no end-to-end cell:
  realtel-e2e-valuerule-v1 differences every field whose values never fall in the run and rescores the 42 cells for the
  seven matchers and the generic LLM matcher; `R/realtel_e2e_valuerule_v1/judge.json` (`rate`: each method scores the
  same with its own rule and with the value rule). Level 2: `python3 scripts/realtel_e2e/e2e_valuerule_v1.py` (inputs as
  in "End to end on real software"), or count the cells in `detail`:

  ```python
  import json
  d = json.load(open("experiments/results/realtel_e2e_valuerule_v1/judge.json"))
  x = [c for f in d["detail"].values() for ms in f.values() for c in ms.values()]
  print(len(x), sum(c["orig"][1] != c["val"][1] for c in x))   # 336 0: no method-cell score changes
  ```
- First-round labels (0.962 against 0.707, +0.255, 0.145 to 0.383): `realtel_scale_v1.py judge` (`sens_round1`, input
  `R/realtel_scale_v1/truth_sens_round1.json`).
- Engineer (38 disagreements; 16 scored, 22 different-definition; categories): gt-blind-expert-v1,
  `R/gt_blind_expert_v1_public/adjudication.json`, `R/gt_blind_expert_v1/result.json`.
- Open models (59 and 29 of 75, 72 of 72, 1 and 12 of 36 unparsable): `python3 scripts/coldstart/realtel_scale_v1.py open_score`
  (inputs `R/realtel_scale_v1/out_open_r1_32b.jsonl`, `out_open_r1_14b.jsonl`); seven specifications 0.917 and 0.879:
  `realtel_revise_v1.py`.
- Different definitions scored as missing: 0.940 against 0.738, +0.201 [+0.094, +0.345], 12.1%: `realtel_revise_v1.py`
  (realtel-adapter-v1); 0.865 against 0.597, +0.268 [+0.160, +0.394], 11.0%: `python3 scripts/coldstart/realtel_scale_kindmiss_explore.py`
  (realtel-scale-kindmiss-explore, exploratory; writes `R/realtel_scale_v1/kindmiss_explore.json`).

### Section S9. How the evidence was recorded

- Exploratory readings and failed uses:
  - Browser derivation function with missing values set to 0: realtel-closure-v1, does not hold:
    Δ −0.067, 90% interval [−0.227, +0.090], best non-LLM mapping TF-IDF; Level 1: `R/realtel_closure_v1/judge.json`
    (`verdict`, `delta`, `ci90`, `mean_dev`). The exploratory reading with medians in place of zeros, which led to the
    registered successor realtel-closure-v2, is `R/realtel_closure_v1/explore_fill.json`. Rerunning
    `closure_v1.py judge` needs the eight captured runs of this test, which are not included.
  - Multi-scale variant 11.4 points behind LLM4Band at 200 to 400 kb/s: lowbw-nl-vs-conf-v1. Level 2:
    `python3 -c 'import json, sys; sys.path.insert(0, "scripts/alphartc/deploy"); import lowbw_nl_vs_conf_v1 as N; U = {}; [U.setdefault((r["cap"], r["arm_key"]), []).append(r["utility"]) for r in map(json.loads, open("experiments/results/lowbw_nl_vs_conf_v1/runs.jsonl")) if r["valid"] and r.get("utility") is not None]; print(N.judge(U, "nl0", "cf0"))'`
    prints "does not hold" and D −11.43 [−11.58, −11.28] (`nl0`: the multi-scale variant, `cf0`: LLM4Band, both with no
    envelope); also `R/lowbw_nl_vs_conf_v1/result_v1.json`. Level 3: batch script `D/lowbw_nl_vs_conf_v1.py`, run script
    v17; both arms need checkpoints that are not distributed.
  - Rules from five calls, error 0.731 against 0.691: switch-llm-coldstart-v3 (data event).
  - Unit corrections, 6.30 against 2.89: obsrepair-closedloop-v2 (and obsrepair-llm-v2; data events).
  - Collector audits, F1 0.60 and 0.72 against 0.70: coldstart-collector-audit-v2 (local model, the R1 distillation into
    Qwen 14B, does not hold) and coldstart-collector-audit-v3 (hosted model, inconclusive). Level 1: `planted_feature_f1` of `arms` and `baselines` in
    `data/audit_bench_v1/score_v2.json` (0.595; Kolmogorov–Smirnov at threshold 0.4: 0.704) and
    `data/audit_bench_v1/score_v3_flash.json` (0.720). The test set and the model answers are not included.
  - Offline GCC replay stayed at 0.3 Mb/s in 87% of steps: bob-hrcc-perstep-dump-v1 (void: faulty replay adapters). Level 2: `python3 -c "import numpy as np; p = np.load('experiments/results/bob_hrcc_perstep_dump_v1/perstep_gcc.npz')['pred']; print(np.mean(np.isclose(p, 0.3)))"`
    prints about 0.872 (GCC's per-step estimate in Mb/s on the 870 calls).
  - One-token row 6.51 (Low BW 0.78, Fluctuating 2.35) not reproduced: repro-mre4-1240000 (measured 6.743, the row of
    Table I).
- Revisions after the fact (registered and revised verdicts in `registry/registry_summary.md`): obsschema-closedloop-v1
  (confirmed by obsschema-closedloop-v2); realtel-adapter-v1 (+0.286 to +0.244, `R/realtel_adapter_v1/revise_v3.json`);
  realtel-e2e-v1 (48 cells, +0.333, to 42 cells, +0.238, `e2e_v3` in `make_tables_v2.py`); hd720-realtrace-ch-v1
  (`R/hd720_realtrace_ch_v1/revise_both_invalid.json`); hd720-learned-alone-v1
  (`R/hd720_learned_alone_v1/result_rejudge_env0.json`); hd720-designer-ch-v1 and hd720-designer-tel-v1
  (`R/hd720_designer_ch_v1/rejudge_fail0.json` and the snippet of "Section V-E. In closed loop", which reproduces both
  the registered and the revised readings).

## Appendix: run-script versions

The table lists the shipped run scripts, the receiver entry point each installs
(`scripts/alphartc/BandwidthEstimator_staleness_vNN.py`) and the batches that used them, from the batch scripts and the
shipped job lists. Run scripts v12 to v16 are not in the package; the envelope batches of Section S7 used one of them
(the registry texts name v13). The collector batches of Section V-F and the noise batch of Section V-A ran through a
batch driver that is not in the package, with an earlier state of the unnumbered
`scripts/alphartc/run_staleness_once_twocontainer.sh` than the shipped copy.

| Run script | Entry point; arm modules of the cited arms | Batch script(s) (`D/`) | Registry id(s) | Paper result(s) |
|---|---|---|---|---|
| v10 | v7; `arm_default_schema` = `fixed_schema_x_v1.py` (challenge baseline, envelope v4) | `obsschema_cl2_v1.py`, `testbed_parallel_equiv_v1.py` | obsschema-closedloop-v2 | Table IV (closed loop, challenge baseline downstream), Fig. 3(c) |
| v11 | v8; adds `arm_llm4bandpp_schema` | not in the package; one calibration job of `compete_flow_ch_eval_v1.py` | obsschema-closedloop-llm4bandpp-v1 | none |
| v17 | v12; `arm_llm4bandpp_nl_x` (`online_llm_arms_v5.py`), `arm_nl_schema` (`fixed_schema_nl_v1.py`) | `obsschema_rt_nl_v1.py`, `lowbw_nl_vs_conf_v1.py` | obsschema-closedloop-nl-v1, lowbw-nl-vs-conf-v1 | Table IV (multi-scale variant), Section S9 (11.4 points) |
| v18 | v13; `arm_ch_x` = `online_llm_arms_v6.py` (no floor), `arm_llm4band_conf_x` = `online_llm_arms_v4.py` | `hd720_ch_eval_v1.py`, `compete_flow_ch_eval_v1.py`, `lowbw_ch_vs_conf_v1.py` | hd720-closedloop-ch-v1, hd720-ch-vs-nl-v1, compete-flow-ch-v1, lowbw-ch-vs-conf-v1, lowbw-ch-vs-conf-env6-v1 | Table V (first batch), Fig. 4(a), Fig. 4(c), shared bottleneck, low capacities |
| v19 | v14; `arm_ch_x` = `online_llm_arms_v7.py` (collector v7, startup guard) | `guard_smoke_v1.py` | ch-startup-guard-smoke-explore-v1 | Section IV (a zero estimate stops the sender) |
| v20 | v15; `arm_ch_x` = `online_llm_arms_v8.py` (floor), `echo_x` = `echo_x_v2.py` | `lowbw_chf_vs_conf_v1.py`, `hd720_attr_loss_v1.py`, `hd720_realtrace_v1.py`, `floor_smoke_v1.py` | lowbw-chf-vs-conf-v1, hd720-echo-attr-ch-v1, hd720-randloss-ch-v1, hd720-realtrace-ch-v1 | Table V (second batch, cellular, random loss), Fig. 4(b), Fig. 4(c), echo test, low capacities |
| v21 | v15; installs `ch_s0.pt`, `ch_s2.pt` | `hd720_seeds_v1.py` (check v1) | hd720-seeds-ch-v1 | Table V (seeds 0 and 2) |
| v22 | v15; patched high-bitrate sender | `hd720_highbw_v1.py` | hd720-highbw-ch-v1 | Table V (high bandwidth), Section V-F |
| v23 | v15; installs `ch_l08s1.pt` | `hd720_lambda_v1.py` (check v2) | hd720-lambda-ch-v1 | Section V-B (λ), Section S6 |
| v24 | v16; `arm_schaferct_retrained_d`, `arm_mlp_d` = `fixed_x_v2.py` | `hd720_learned_v1.py`, `hd720_learned_alone_v1.py`, `hd720_hb_learned_v1.py`, `hd720_freeze_floor_v1.py` | hd720-learned-baselines-v1, hd720-learned-alone-v1, hd720-hb-learned-env-v1, hd720-hb-learned-alone-v1, hd720-freeze-floor-v1 | Table V (learned rows), Section V-F (77%, 7.7 and 74.6, 89.7 and 83.9), Section S7 |
| v25 | v17; `arm_ch_schema` = `fixed_schema_ch_v1.py` | `hd720_designer_ch_v1.py` | hd720-designer-ch-v1 | Table IV (deployed system, 720p), Section V-E |
| v26 | v17; installs `ch_l10s1.pt`, `ch_l00s1.pt` | `lowbw_lambda_env6_v1.py` (check v5); `lowbw_lambda_ch_v2.py` (check v3) | lowbw-lambda-ch-v2, lowbw-lambda-env6-v1 | Section V-B (λ behind the envelope), Section S6 |
| v27 | v18; `arm_ch_schema_tel` = `fixed_schema_ch_v2.py` (envelope v4, no shadow GCC) | `hd720_designer_tel_v1.py`, `hd720_designer_tel_v2.py`, `hd720_designer_tel_fid_v1.py` | hd720-designer-tel-v1, hd720-designer-tel-v2, hd720-designer-tel-fid-v1 | Table IV (telemetry only), Section V-E, abstract (1 of 60) |
| v28 | v17; installs `ch_l06s1.pt` | `lowbw_loss_v1.py`, `lowbw_lambda_mid_v1.py` (check v4) | lowbw-loss200-ch-v1, lowbw-lambda-mid-ch-v1 | Section V-F (5.5 points, −1.4 against GCC), Fig. 4(c), Section S6 |
| v29 | v17; adds the λ 0 and λ 1.0 checkpoints of seeds 0 and 2 and `ch_a0s2.pt` | `lowbw_lambda_seeds_v1.py`, `lowbw_noanchor200_v1.py` (check v6), `lowbw_loss1_env6_v1.py`, `content320_ch_gcc_v1.py` (check v7) | lowbw-lambda-seeds-v1, lowbw-noanchor-200-v1, lowbw-loss1-env6-v1, content320-ch-gcc-v1 | Table V (320×240), Fig. 4(c), Section V-B (4.7 points), Section V-F (anchor-free, 1% loss), Section S6 |
