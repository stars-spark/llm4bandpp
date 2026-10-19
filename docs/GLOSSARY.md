# Glossary of names used in the package

File names, script names, arm names and printed labels were chosen while the experiments ran and often differ from the
paper's terms. Each name below is mapped to its meaning and to the paper (Sections I to VII) or its supplement
(Sections S1 to S9).

## Estimators, training cells and checkpoints

| Name in package | Meaning | Paper term / section |
|---|---|---|
| C-H | Conference encoder trained with the HCQ reward (λ = 0.4), with the capacity anchor, no LLM. Seed 1 is the deployed estimator. | "LLM4band++, deployed" (Table I); deployed recipe, Sections III-C, V-C, S4 |
| C-B | Conference encoder with the conference reward (λ = 0), with the anchor, no LLM | "conference encoder with the conference reward", Section V-C |
| M-H | Multi-scale encoder with HCQ, with the anchor, no LLM | Section V-C; "No LLM" row of Table S3 (seeds 0 to 2) |
| M-B | Multi-scale encoder with the conference reward, with the anchor, no LLM | Section V-C |
| `ch` | C-H, in arm names, file names and printed labels | deployed estimator |
| `nl`, `NL` | "No LLM": the multi-scale encoder without the LLM (M-H) | "No LLM" (Table S3), multi-scale variant (Sections V-C, V-D) |
| `nl2x2` | The 2×2 ablation without the LLM: encoder (conference or multi-scale) × reward (λ = 0 or 0.4) | Section V-C |
| `nl_estimator_v1/` | Code of the multi-scale estimators and the training code (`IQL.py`, `module.py`, ...), shared by all cells | Sections III-C, III-D, IV |
| `conf`, `cf`, `full_conf`, `llm4band_conf` | The conference version LLM4Band (its LoRA model with Qwen1.5-0.5B) | "LLM4Band" (Tables I, III; Fig. 4(c)) |
| `llm4bandpp`, `pp`, `LLM4band++ (Qwen)` | The one-token LLM variant of our earlier version, **not** the deployed system | "LLM variant, 1 token" (Tables I, III, S3, S4) |
| `hcq` (in `measure_client_hardware_v5.py`, `client_hw_hcq_v1`) | The one-token LLM variant (a model trained with the HCQ reward). Elsewhere `hcq` means the reward itself. | "LLM, 1 tok." (Table III) |
| HCQ | Holistic Communication Quality reward, Eq. (1) | Section III-A |
| `MRE_4.pickle`, `mre4` | Our balanced training pickle: 3,500,000 transitions, rewards stored with λ = 0.4. Ids such as `repro-mre4-1240000` and files such as `input_stats_mre4.json` refer to it. | Section III-B |
| `ch.pt` | C-H seed 1, the deployed checkpoint | Table I footnote c |
| `ch_s0.pt`, `ch_s2.pt` | C-H seeds 0 and 2 | Table V, "Seeds 0 and 2" |
| `ch_l00s0.pt` to `ch_l00s2.pt` | C-B (λ = 0), seeds 0 to 2 | Section V-C, Fig. S1 |
| `ch_lXXsN.pt` | C-H recipe with HCQ weight λ = XX/10 (`l06` = 0.6, `l10` = 1.0), seed N | Fig. S1, Section S6 |
| `ch_a0s2.pt` | C-H recipe without the capacity anchor, λ = 0.4, seed 2 | "anchor-free policy", Section V-F |
| `CHsN`, `CBsN`, `MHsN`, `MBsN` (files in `nl_2x2_v1/eval/`) | Per-call results of cell C-H, C-B, M-H or M-B, seed N | Section V-C |
| `MHreuse_sN` | M-H seeds 0 to 2 are the runs `NLs0` to `NLs2`; the ablation uses their registered per-call results, and these files are re-evaluations used only as a check | Section V-C |
| `CHlXXsN` | λ sweep, as for the checkpoints above | Fig. S1 |
| `A0l00sN`, `A0l04sN` | Capacity anchor removed (`--capacity_aux_weight 0.0`), λ = 0 or 0.4, seed N | Section V-B, "capacity anchor" |
| `SCHsN` | Schaferct's network trained with our recipe, seed N | Section V-B (5.83) |
| `LLMsN`, `NLsN` | Fifteen-token LLM variant pre-trained and tuned with LoRA, and the arm without the LLM, seed N | Table S3 rows "Pre-trained, LoRA" and "No LLM" |
| `PFsN`, `RIsN` | Pre-trained and fully trained; randomly initialized and fully trained | Table S3, Table II per-step row |
| `MBsN` (files in `aggregator_mamba_control_v1/`) | The arm with the Mamba-style aggregator. In `nl_2x2_v1/eval/` the same prefix means cell M-B. | Table S3, "No LLM, Mamba agg." |
| `enc_hcq_2x2` | Encoder × reward ablation repeated on the LLM variant with the corrected encoder | Section S2, "Corrected encoder" |
| `Schaferct(public)`, `schaferct_public.onnx`, `schaf` | The challenge baseline: the offline RL baseline model released by the challenge organisers (`onnx_models/Offline_RL_baseline_bandwidth_estimator_model.onnx`, Microsoft, MIT license), at `experiments/results/switch_deploy_v1/models/schaferct_public.onnx` (sha256 `54e3113e1d0682a2...`). We took it from the Schaferct repository, where the byte-identical file is `onnx_model_for_evaluation/baseline.onnx` of the Schaferct repository, hence the name in the code; see `NOTICE`. | Challenge baseline (Table I); "challenge baseline downstream" (Table IV, Fig. 3(c)) |
| `Schaferct(retrained)`, `schaferct_retrained.onnx`, `scr` | Schaferct's architecture retrained on our split with its own recipe | Schaferct-R |
| `MLP_seed0`, `mlp` | Supervised MLP regressor, seed 0 | Supervised MLP |
| `LLM4Band conference version online weights (Qwen)` | LLM4Band, as printed by `main_table_unified_v1.py` | LLM4Band (Qwen) |
| `_deleak.json` | The 712-call leakage-free subset of the 870 validation calls | Table I, right half |
| `perstep.npz`, `*_perstep_dump_v1` | Per-step predictions, ground-truth capacity and short-window features on the 870 validation calls | Table I, Level 2 input |
| `conf15`, `ms15` (cells `CB`, `CH`, `MB`, `MH` of `enc_hcq_2x2_v1`) | Encoder of a cell of the corrected-encoder ablation on the LLM variant: `conf15` the conference encoder, `ms15` the corrected multi-scale encoder (143 718 parameters) | Section S2, "Corrected encoder" |
| `MT`, `mt_anchor` | The fifteen-token LLM arm (pre-trained, LoRA) with the capacity anchor of llm-indispensability-mt-anchor-3seed, and its training directory | Table S3, "Pre-trained, LoRA" |
| `E0` to `E3`, `TSC-Enc`, `D5` | Encoder candidates of the earlier encoder studies encoder-tsc-upgrade and encoder-d5-multitoken-transfer: E0 the conference `StateEncoder`, E1 and E2 control encoders, E3 `TSCEncoder` ("TSC-Enc"); D5 a later candidate with a shrinkage gate | Section S2 (encoder audit); Table S2 (time per update) |

## Testbed arms and short keys

| Name in package | Meaning | Paper term / section |
|---|---|---|
| `arm_ch_x` | The deployed estimator in the testbed (C-H, weights `ch.pt` unless `STALENESS_CH_CHECKPOINT` names another file) | LLM4band++ in closed loop, Section V-F |
| `dep` | The deployed system (C-H with the 5 kb/s floor and envelope v6), in `content320_ch_gcc_v1` and `lowbw_loss200_ch_v1` | "deployed system" |
| `gcc_pt125_c200`, `gcc200`, `gcc` | The Python GCC of the conference code with its loss branch reading RTP payload type 125 (`pt125`), called every 200 ms (`c200`) | "Python GCC called every 200 ms", Section V-A |
| `echo_x`, `echo` | Receiving-rate echo behind envelope v6 | Section V-F, echo test |
| `arm_llm4band_conf_x` | LLM4Band (conference checkpoint) | Fig. 4(c), Section V-F, low capacities |
| `arm_llm4bandpp_x` | One-token LLM variant | Section S7; the observation grid of Fig. 1 |
| `arm_llm4bandpp_nl_x` | Multi-scale variant without the LLM | Section S9; behind an adapter it is `arm_nl_schema` (Table IV) |
| `arm_schaferct_retrained_d`, `arm_mlp_d` | Schaferct-R and the supervised MLP with the settings of the deployed system (collector v6, floor, envelope v6) | Table V, learned estimators |
| `arm_default_schema` | The challenge baseline behind an adapter, envelope v4 | Table IV "Closed loop, challenge baseline downstream", Fig. 3(c) |
| `arm_ch_schema` | The deployed system behind an adapter | Table IV "deployed system, 720p" |
| `arm_ch_schema_tel` | The deployed estimator behind an adapter, envelope v4, no shadow GCC | Table IV "telemetry only" |
| `arm_nl_schema` | Multi-scale variant behind an adapter, envelope v6 | Table IV "our multi-scale variant, deployed envelope" |
| `arm_lambda` | No-LLM estimators of an earlier λ study; no paper result uses them | none |
| `fixed_env` | A fixed estimate, used to measure the freezes the testbed itself causes on an uncongested link (freeze floor) | Section S7 |
| `ch0`, `ch6`, `cf0`, `cf6`, `nl0`, `nl6`, `scr0` | Arm key followed by the envelope version: 0 = no envelope, 6 = envelope v6. In `hd720_hb_learned_v1`, `ch` and `scr` are behind envelope v6 and `ch0`, `scr0` have none. | "no envelope" / "behind the envelope" |
| `l00`, `l04`, `l06`, `l08`, `l10`, `l00s0`, ... | C-H recipe at λ = 0, 0.4, 0.6, 0.8, 1.0; a suffix `sN` gives the seed | Section S6 |
| `a0` | Anchor-free C-H recipe (`ch_a0s2.pt`) | Section V-F |
| `s0`, `s2` | C-H seeds 0 and 2 | Table V |
| floor | `STALENESS_MIN_BPS_FLOOR=1` (`BWE_MIN_BPS_FLOOR=1`): estimates are kept at or above 5 kb/s | Section IV |
| `arm_pioneer`, `arm_schaferct_public`, `arm_schaferct_retrained`, `arm_mlp`; with `_x`, the same behind the probing envelope | Fixed arms over the switcher's model bank: Pioneer, the challenge baseline, Schaferct-R or the supervised MLP alone | Section V-F, "Collector corrections" |
| expert, four-expert bank, default expert (switcher family) | A member of the switcher's model bank (Pioneer, the challenge baseline, Schaferct-R, the supervised MLP); the default expert, used before the first switch, is the challenge baseline. The "adapted expert" is `adapt_x`. | Sections VI, S9 |
| `switch_nn_x`, `adapt_x`, `echo_x_v1`; keys `switch_env`, `adapt_env`, `echo_env`, `gcc_c200` | Arms of earlier 320×240 batches (closedloop-envelope-echo-v1, closedloop-adapt-v1, -v2): the learned switcher, an MLP trained on testbed logs (the adapted expert) and the receiving-rate echo, each with collector v6 and envelope v4; `gcc_c200` is `gcc_pt125_c200` without an envelope | none |
| `arm_llm4bandpp_schema`, `c3_v6_env4` | The one-token LLM variant behind an adapter, with collector v6 and envelope v4 (obsschema-closedloop-llm4bandpp-v1); `c3_v6_env4` names that configuration of the variant (llm4bandpp-online-unlock-v1) | none |
| `T2`, `T3`, `G2` | Shared-bottleneck conditions: 2 or 3 Mb/s shared with one TCP CUBIC flow; 2 Mb/s shared with a second GCC call | Section V-F, shared bottleneck |
| `D`, `D_A`, `D_E`, `D_H`, `D_L`, `D_S`, `D_T`, `S`, `B` | Name a batch judge gives its primary endpoint: a mean over cells of arm minus reference (`S` a difference in bottleneck share, `B` in broken calls). The letter is local to the batch (`D_A` is the designer contrast in hd720-designer-* and the no-envelope contrast in hd720-hb-learned-alone-v1), so read it with its registry entry | Tables IV and V |

## Components and their versions

A higher version number marks a later batch, not a fix of an earlier one; each result uses the versions listed for it in
`docs/RESULTS_INDEX.md`.

| Name in package | Meaning | Paper term / section |
|---|---|---|
| envelope 0 | No probing envelope | "no envelope" |
| envelope v4 (`safety_envelope_v4.py`) | The probing envelope without the shadow-GCC rules | Fig. 2 without †; Table IV rows "Closed loop, challenge baseline downstream" and "telemetry only" |
| envelope v6 (`safety_envelope_v6.py`) | The deployed envelope: v4 plus the two shadow-GCC rules | Fig. 2 with †, Section III-E |
| envelope v2, v3, v5 (`safety_envelope.py`, `_v3`, `_v5`) | Earlier or tuning variants; no paper result uses them | none |
| shadow GCC | `gcc_pt125_c200` run inside envelope v6 on the native packet reports | Section III-E |
| collector (`spec_collector*.py`) | Code that turns packet reports into the 150-value observation | Section III-E, Table S1 |
| collector v1 (`spec_collector.py`) | The original collector | "Original" in Table S1 |
| collector v5 | Loss counted per stream (per SSRC) | Table S1 item 11; Section V-F, "Collector corrections" |
| collector v6 | v5 plus the constant for the unreported 41 kb/s audio stream; the collector of every closed-loop batch | "corrected collector", Section III-E |
| collector v7 | v6 with the audio constant only in windows that received packets; used only in one exploratory smoke batch | none |
| entry point v7 to v18 (`BandwidthEstimator_staleness_vNN.py`) | The receiver-side estimator entry point installed in the container; it selects the arm. Not every version number is shipped. | Section IV |
| run script v10, v11, v17 to v29 (`run_staleness_once_twocontainer_midsnap_vNN.sh`) | The script that runs one call on the testbed and installs the components; these are the shipped versions | Section V-A, closed-loop testbed |
| weight check v1 to v7 (`seed_weight_check_vN.py`) | For a batch that loads several C-H checkpoints: names the checkpoint each run used (`docs/TESTBED.md`, section 7) | none (run validity) |
| `staleness` (in script names) | The entry point can delay the estimate it returns (`BWE_DELAY_MS`) and logs the age of every applied estimate. Every shipped run uses 0 ms, marked `d0` in run file names. | none |
| `twocontainer` | Sender and receiver run in separate containers on separate container networks | Section V-A |
| `midsnap` | The run script records the shaping state at the end of the network profile, before the extra seconds that the call runs after the profile ends | none |
| freeze proxy (`proxy_*` columns, `frame_gap_proxy_v1.py`) | Freezes estimated on the network side from frame arrival gaps in the receiver's log; used by earlier 320×240 batches and kept as columns of the 720p rows | none (the paper's freezes use decoded-frame times, Section S7) |
| startup guard | An option of the arm modules from `online_llm_arms_v7.py` on (`BWE_STARTUP_GUARD=1`) that caps the estimate at 300 kb/s, the libwebrtc default start rate, until all five 600 ms windows have seen packets; off in the deployed system and tested only in an exploratory smoke batch | none |

## Network conditions, trace windows and videos

| Name in package | Meaning | Paper term / section |
|---|---|---|
| `hd_c1`, `hd_c2`, `hd_c3`, `hd_c8` | 720p, constant 1, 2, 3 and 8 Mb/s, 50 ms one-way delay | Section V-F, "720p calls" |
| `hd_r1`, `hd_r2` | The two cellular windows of the 720p batches: Chorus high-speed rail (mean 1726 kb/s) and UCC 4G train (mean 2539 kb/s) | "two cellular windows", Section V-F |
| `hd_t1` to `hd_t8` | The eight windows of the cellular batch (UCC 4G and Chorus); `hd_t6` is the window the post hoc revision drops (45 s outage) | Table V, "Cellular, 7 windows" |
| `hb_c3`, `hb_c6`, `hb_c10`, `hb_c15`, `hb_t1`, `hb_t2` | High-bandwidth batches: constant 3, 6, 10, 15 Mb/s and two UCC 4G windows from a train (mean 6.6 Mb/s) and a bus (10.5 Mb/s) | Section V-F, "High bandwidth" |
| `hd_l2p1`, `hd_l2p5`, `hd_l8p1`, `hd_l8p5` | 2 or 8 Mb/s with 1% or 5% random loss | Section V-F, "random loss" |
| `hd_cal20` | Constant 20 Mb/s, freeze-floor calibration | Section S7 |
| `c100` to `c400`, `c1000` | 320×240, constant capacity in kb/s | Fig. 4(c); Table V 320×240 rows |
| `c200l1` | 200 kb/s with 1% random loss | Section V-F, "Low capacities" |
| `low`, `medium`, `high` (320×240 sequence labels, the `content` field) | Johnny, Mobcal and Parkrun, ordered by mean temporal information (ITU-T P.910) | Table V 320×240 rows; Section V-A |
| `paper_720p_low.yuv` etc. | The 1280×720, 15 fps sources from which the 320×240 sequences are scaled (`qoe_labeled_*_320x240.yuv`) | Section V-A |
| `johnny`, `fourpeople` | The two 720p sequences | Section V-A |
| job directory `<cond>__<content>__<arm>__r<N>` | One run: condition, sequence (`content`), arm key, repetition | none |
| run file `<kind>_<arm>__<cond>__d0__r<N>__v<content>` | A per-run file (observations `obs_`, decisions `decision_`, quality `quality_`, decoded-frame times `decoded_timestamps_`) | none |
| `C1`, `C2`, `C3`, `C8`, `R1`, `R2` (hd720-closedloop-v1 and its note) | Earlier names of `hd_c1`, `hd_c2`, `hd_c3`, `hd_c8`, `hd_r1`, `hd_r2` | Section S7 |
| `hd_dev15` | Development profile, constant 1.5 Mb/s (`profiles/hd720_dev/`), used only in smoke runs | none |
| `lowbw_<kb/s>`, `paper_low_<kb/s>`, `paper_high_<kb/s>`, `paper_fluct_400_1200`, `fast_alt_400_1200_p*`, `lowbw_trap_300_1000` (`profiles/lowbw/`) | 320×240 profiles of earlier batches: constant capacity in kb/s, or alternating between the two rates in the name; `lowbw_100`, `lowbw_156` and `paper_low_200` are the profiles of the collector-correction batches | Section V-F, "Collector corrections" |
| `real_lowbw_01` to `real_lowbw_12` | Twelve 120 s cellular windows below 1 Mb/s from the public trace corpus, four per mean-rate band (below 300, 300 to 600, 600 to 1000 kb/s), used by earlier 320×240 batches | none |
| `coldstart_real/` profiles (`4g_car_NN`, `4g_ped_NN`, `3g_tram_NN`, `3g_metro_NN`, ...); scenarios `medium_bw_call`, `4g_car`, `4g_ped`, `3g_tram`, `3g_metro` | Real-trace windows and evaluation scenarios of the switcher's LLM rule study (switch-llm-coldstart-v3) and of the unit-correction study | Sections VI, S9 |
| `es_1` to `es_3`, `sd_1` to `sd_8`, `sc_1` to `sc_8`, `rt_1` to `rt_8` | Cellular windows of the synthetic-schema closed-loop batches: evidence and held-out windows of obsschema-closedloop-v2 (`es`, `sd`), windows of the first batch (`sc`, ferry and bus), windows of obsschema-closedloop-nl-v1 (`rt`) | Fig. 3(c); Table IV |
| `test_c` to `test_j`, `rt_getstats` and the other `rt_*` schemas; cell key `<schema>\|<window>` | Synthetic schemas (field names, order and units in `scripts/arb/obsschema_v1.py`; the closed-loop batches use `test_g` to `test_j`) and the five newer ones; a designer closed-loop cell is written schema\|window, e.g. `test_j\|hd_r1` | Section V-E, "Synthetic schemas"; Table IV |
| `f0` to `f14`, "feature N" | The 15 interface features by 0-based index: 0 receiving rate, 1 received packets, 2 received bytes, 3 queueing delay, 4 delay, 5 minimum seen delay, 6 delay ratio, 7 delay minus minimum, 8 inter-arrival time, 9 jitter, 10 loss ratio, 11 lost packets, 12 to 14 video, audio and probing packet shares; feature i fills the observation values 10i to 10i + 9 | Section III-A; Table S1 |
| `S01` to `S19` | Source ids of the blind-labeling sheet: S01 to S07 the seven specifications, S08 to S19 the 12 client stacks | Section V-E, "Protocol" |

## Experiment and script families

| Name in package | Meaning | Paper term / section |
|---|---|---|
| `coldstart` | Designer side: calls to the hosted and open models for a new client stack, the baseline matchers and their judges | Sections V-D, V-E, S8 |
| `realtel` | Designer tests on real telemetry: the seven specifications (`realtel_adapter_v1`), the 12 client stacks (`realtel_scale_v1`) and their variants | Section V-E, Table IV |
| `realtel_e2e` | End to end on real software (Chrome, iperf3, `tcp_info`, GStreamer) against packet captures; also the browser derivation function and the single-field masking runs | Section V-E, Fig. 3(b) |
| `closure` | The browser `getStats()` derivation function written by a third prompt | Table IV "Browser getStats only", Section S8 |
| `mask_offline` | The deployed estimator with only the features a stack exposes as single fields | Section V-E (5.80 rises to 9.0 to 23.3) |
| `obsschema` | Synthetic schemas that rename, reorder and rescale the 15 features; `_cl` and `_cl2` are their closed-loop batches, `_rt` the five newer schemas (one, `rt_getstats`, follows getStats naming) | Section V-E "Synthetic schemas"; Table II; Fig. 3(c) |
| `openreason` | Open reasoning models (DeepSeek-R1 distillations) on the synthetic schemas | Table II |
| `strong_baseline`, `unitname` | The unit-aware matcher we wrote, a non-LLM baseline that reads names and values | Table IV, "unit-aware matcher" |
| `namehide` | Each field's own name masked | Table IV "field names hidden" |
| `cfdoc` | Counterfactual documentation: units and counting rules rewritten to contradict the public text | Section V-E (33 of 33 cells) |
| `repeat` | Repeated hosted calls | Section V-E, S8 |
| `llm_schema_match` | The same LLM used as a generic schema matcher | "LLM match" (Fig. 3), Table IV |
| `twostep` | Fields, then units and counting rules, in two calls | "Two-step" (Fig. 3), Table IV |
| `designer_scale` | Qwen1.5-0.5B-Chat as designer | Sections V-D, S8 |
| `r1qwen_size` | R1 distillations into Qwen at 1.5B, 7B, 14B, 32B | Section V-D, S8 |
| `open_sampling_variance` | Three samples of each open model | Fig. 3 (means of three samples) |
| `open70b` | A 70B distillation, scored but not used in the paper | none |
| `kindmiss` | Different-definition pairs scored as features to be declared missing | Section S8 |
| `gt_blind_expert`, `gt_engineer_sens` | The engineer's blind labels, and the rescoring with them | Section V-E, S8 |
| `obsrepair` | The LLM corrects unit and collection errors from value statistics | Sections VI, S9 ("unit corrections inferred from value statistics") |
| `switch`, `switcher`, `switch_nn` | A switching estimator that picks one of four learned estimators every 3 s. It is not part of LLM4band++; the LLM use "picking among estimators" of Sections VI and S9 (registry entry switch-llm-coldstart-v3) belongs to this family. `switch_deploy_v1/models/` holds the baseline models (Pioneer, challenge baseline, Schaferct-R, MLP), and the Schaferct-R and MLP arms run through its model bank. | Sections VI, S9 |
| `arb` | Offline analyses on the per-step exports and replays of the challenge calls (Table I rows, synthetic-schema replays, HCQ term correlation, vLLM generation) | Sections III-A, V-B, V-E |
| `c3q` | Per-call metric functions shared by the evaluators | Section V-A, metrics |
| `lib/encoder0.py` | The fixed input scale vector c of the 150 observation values | Section S2, "Input scaling" |
| `llm_kp` | Builder of the public cellular-trace corpus from which the UCC 4G and Norwegian 3G windows are cut; named after an earlier study for which the corpus was built and which the paper does not report | Section V-A (traces) |
| `gcc_native` | Chrome's native GCC in headless loopback calls | Sections V-F, S7 |
| `hd720_*`, `lowbw_*`, `content320_*` | 720p batches; 320×240 batches at 100 to 400 kb/s (Mobcal); the 320×240 batch with three sequences | Section V-F |
| `compete_flow` | Shared bottleneck with a TCP CUBIC flow or a second GCC call | Section V-F |
| `realtrace` | The cellular batch | Table V |
| `highbw`, `hb` | High bandwidth, libwebrtc's 720p cap raised to 20 Mb/s | Section V-F |
| `attr` (`hd720_attr_loss_v1.py`) | One batch script for two batches: hd720-echo-attr-ch-v1, which attributes part of the lead to the envelope with the echo arm and is the "Second batch" of Table V, and hd720-randloss-ch-v1 (random loss) | Table V, Section V-F |
| `learned_alone` | Learned estimators without the envelope | Table V "no envelope" |
| `chf` | C-H with the 5 kb/s floor | Section V-F, "Low capacities" |
| `steady_qoe` | Split of the VMAF difference into the first 30 s and the rest | Section V-F |
| `client_hw` | Latency and energy measurements | Table III |
| `llm_indispensability`, `pretrained_fulltrain_fourth_arm` | Per-step LLM position study: LoRA against no LLM; pre-trained against randomly initialized, both fully trained | Table II, Table S3, Section V-D |
| `NAME`, `TFIDF`, `CUPID`, `COMA`, `SF`, `MPNET`, `BGE`; `MAP_CUPID` | The seven non-LLM matchers in judge files and registry texts: name similarity, name and documentation TF-IDF, Cupid, COMA, Similarity Flooding, and the all-mpnet and bge-large embedding retrievers; `MAP_CUPID` is Cupid's mapping in the getStats derivation test | Fig. 3; Table IV |
| `LLM`, `NAME`, `DIST`, `NONE`, `CLEAN` (mapping labels in job names and judge output) | The designer's mapping, name matching, distribution matching, no adaptation, and the true mapping | Fig. 3(c); Table IV |
| `LLM_OBF`, `OBF`, `NAMED`, `field_01` to `field_15` | The designer with each field's own name replaced by a placeholder `field_NN`, against the same prompt with the real names | Table II, masked names |
| `r1_32b`, `r1_14b`, `r1_7b`, `r1_1p5b` (suffix `_sdNNNNNNNN`), `ds_q15_05b`, `ds_q25_15b`, `ds_q25_7b` | Open designer models: R1 distillations into Qwen 32B (4-bit), 14B, 7B and 1.5B; Qwen1.5-0.5B-Chat, Qwen2.5-1.5B-Instruct and Qwen2.5-7B-Instruct | Sections V-D, S8 |
| `SNAP1000`, `SNAPALL`, `HAND` | Non-LLM baselines of the unit-correction study: snapping each scale to the unit factors 10^±3 and 10^±6 (`SNAP1000`), also 8, 1/8, 100 and 1/100 (`SNAPALL`), and our rule-based consistency check designed on the two error types of the development groups (`HAND`) | Section S9, unit corrections |
| `KS_0.2`, `KS_0.4`, `RATIO`, `PRIV_KS_VS_C` | Non-LLM controls of the collector-code audits: Kolmogorov–Smirnov tests at thresholds 0.2 and 0.4, a ratio test and a fourth KS variant, scored in `data/audit_bench_v1/score_v2.json` and `score_v3_flash.json` | Section S9 (0.70) |
| `MINPSEUDO`, `MAJ5`, `NN0`, `GBDT0`, `NN5`, `GBDT5`, `DT5` | Deployable controls of the switcher's LLM rule study: a zero-parameter rule, the estimator most often best on the first five calls, and selectors trained on the 870 calls (`0`) or also on the first five calls (`5`; `DT5` a depth-3 tree on those five calls only) | Section S9 (0.691) |
| `BM25`, `J01` to `J60`, `deployable`, `no_patch` | The lexical retrieval baseline, the injected incident cases and the patch outcomes of the coldstart-incident-* entries (LLM fault localization in collector code) | none |

## Ground truth, scoring and status

| Name in package | Meaning | Paper term / section |
|---|---|---|
| `same`, `kind`, `none` | Ground-truth labels: the same quantity, a different definition, no counterpart | Section V-E, "Protocol" |
| first ground truth | The labels fixed at registration. `realtel_e2e_v1.py judge`, run alone, scores against it (48 cells). | Section S9, "Revisions after the fact" |
| `truth_v2.json`, `truth_v3.json` | Second and third versions of the labels of the seven specifications, each listing its changes and reasons; the third ground truth is the one the revised readings use | Table IV status P; Section S9 |
| `revise_v3.json` | The seven-specification readings under the third ground truth | Table IV "7 real telemetry specs" (P) |
| `e2e_v3` (function in `make_tables_v2.py`) | The end-to-end rates rescored on the 42 cells scored under the third ground truth | Table IV "Real software end to end, 42 cells" (P) |
| `truth_sens_round1.json`, `sens_round1` | The 12-stack labels of the first round of the two LLM checks, before the cells were relabeled to follow the precedents fixed at registration | Section S8, "first-round labels" |
| development and test sources (`*_dev`, `*_test`) | The two sources the prompt was frozen on, and the held-out sources | Section V-E |
| `sdNNNNNNNN` in file names | Sampling seed of an open-model run | Section S8 |
| R, D, N, P, "P, N", – | Verdict letters of the registry, used in `docs/RESULTS_INDEX.md` (the paper's tables do not print them; footnotes of Tables IV and V mark the revised criteria): R holds as registered; D registered direction only; N fails; P holds only after a post hoc revision of criterion, scoring or ground truth; "P, N" fails even after it; – reported only | Supplement S9; Tables IV, V |
| `holds` | Verdict string: the registered criterion is met | R (P when only a revision meets it) |
| `direction only` | The registered direction is met but not the size | D |
| `does not hold` | The criterion is not met, or the safety line is crossed | N |
| `inconclusive` | The criterion's undecided outcome, defined per entry (for example, a difference inside the registered noise threshold); not counted as holding | described in the text, or P after a revision |
| `void` | A batch voided by its own validity rules and rerun under a new id (for example `lowbw-lambda-ch-v1`, rerun as `-v2`) | none |
| `exploratory` | An analysis chosen after the data were seen; no verdict | "exploratory" in the paper |
| data event | A numeric result in `experiments/registry.jsonl` | Section S9 |
| `scripts/exp.py`, `registry_local.jsonl` | A minimal logger with the interface of our registry tool; judges call it, and it appends to `experiments/registry_local.jsonl` | none |
| BA | Balanced accuracy: the mean of the share of mappable features mapped with the right field, differencing and scale (within 2%) and the share of unmappable features declared missing | Section III-F, "Output" |
| tier: `confirmatory`, `exploratory` | Registry field: a confirmatory entry was registered with its criterion before it ran; an exploratory entry records an analysis of registered runs | Section V-A, "Statistics" |
| `Report only:` | Label in registry verdict texts and judge output before readings recorded without a criterion; they are not judged | "reported only" |
| Group A to D; Group D safety line | Decision groups of the offline pre-registrations; group D is the safety line: no scenario's worsening may raise macro MSE by more than 1% | Section V-C |
| `utility`, `rate_score`, `delay_score`, `loss_rate`, `queue_delay_mean_ms`, `video_kbps`, `file_freeze_per_min`, `envelope_rewrite_frac`, `webrtc_*`, `*_cpu_pct` | Columns of the per-run rows and result files: utility = 100 (0.4 `rate_score` + 0.4 `delay_score` + 0.2 (1 − `loss_rate`)), `delay_score` from the mean queueing delay and a 500 ms bound; the 720p columns are listed in each batch's `data_dictionary.json` | Section V-A, network utility |
| `runs_full.jsonl`, `runs_tidy.csv`, `runs.jsonl`, `result_v1.json`, `contents.json`, `ceilings.json`, `layout.json`, `jobs*.json`, `run_meta.json`, `QUEUE_COMPLETE`, `code_*.sha256` | Files of a closed-loop batch: per-run rows (720p; 320×240), judge output, the sequence list, per-sequence video-rate ceilings, the frame-number layout, job lists, per-run metadata, the scheduler's completion marker, per-run code hashes | none (`docs/TESTBED.md`, sections 1 and 7) |
| `llm_*.jsonl`, `out_*.jsonl`, `prompts*.jsonl`, `transforms_*.json`, `eval_*.json`, `judge*.json`, `parse_r1_*.json`, `scores_*.json`, `sources*.json`, `groups.json`, `maps.json` | Designer files: hosted-model records (also the call cache), open-model answers, prompts, parsed mappings, replay ratios per call, judge output, reparsed R1 answers, baseline scores, transcribed sources, synthetic groups, the mappings deployed in closed loop | none (`docs/DESIGNER.md`) |
| `revise_*.json`, `rejudge_*.json`, `result_rejudge_env0.json`, `revise_both_invalid.json` | Readings under a revision registered after the result was seen; the registered reading stays in `result_v1.json` and in the registry | status P |
| `*_cpu.json`, `check_*.json` (`ch_estimator_v1/equiv/`), `checkpoint_50000.pt`, `train_*.log`, `markers/EVAL_*_COMPLETE.json` | CPU re-evaluations of the released checkpoints and their comparisons, the final checkpoint of a 50 000-update run, training logs, completion markers of an evaluation queue | Table I; Table S2 |
| `*.profile`, `provenance.json`, `profile_sha256.json`, `profiles_public/` | A network profile (commands that set the rate, delay and loss, once per second for traces), the trace id and start second of each window, the hash of each profile's command lines, and the stripped copies shipped where a trace may not be redistributed | none (`docs/TESTBED.md`, section 5) |
