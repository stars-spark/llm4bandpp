# Reproducing the offline results

Offline results: Table I, the per-step row of Table II, Sections V-B to V-D and the supplement.

- **Level 1** regenerates Tables I, II, S3 and S4 and Fig. S1 (`README.md`).
- **Level 2** recomputes every number from the per-call and per-step results in this package: no GPU, no download,
  under 40 s per command on a laptop CPU.
- **Level 3** has two parts. (a) Re-evaluate the released checkpoints on the 870 validation calls rebuilt from the
  public challenge data: a few minutes on a CPU after an 8 GB download. (b) Retrain the deployed estimator and its
  variants from the public data: about 70 GB of data, a GPU and about 20 GB of host memory per run. The training
  pickle is rebuilt exactly; the training runs are not bitwise identical to ours (last section).

The deployed estimator is cell C-H: the conference encoder trained with the HCQ reward (λ = 0.4) and the capacity
anchor, without an LLM, seed 1. C-B, M-H and M-B are the other cells of the encoder and reward ablation (Section V-C;
C = conference encoder, M = multi-scale encoder, H = HCQ, B = the conference reward). Other names are defined in
`docs/GLOSSARY.md`. Commands run from the package root after the path placeholders are set as in `docs/PACKAGE.md`.

## Data and licenses

- Training and validation data: the emulated dataset of the ACM MMSys 2024 Bandwidth Estimation Challenge
  (<https://github.com/microsoft/RL4BandwidthEstimationChallenge>): 9405 calls in three zip files
  (`emulated_dataset_chunk_0.zip` to `_2.zip`, 8.1 GB, about 72 GB unpacked), fetched with the repository's
  `download-emulated-dataset.sh` (uncomment its `curl` line). The repository's code is under the MIT license and its
  content under CC BY 4.0; the datasets are provided as is. Please cite Khairy et al., "ACM MMSys 2024 Bandwidth
  Estimation in Real Time Communications Challenge", MMSys 2024.
- `experiments/results/arb_perstep_dump_v1/perstep.npz` holds the per-step ground-truth capacity and short-window
  features of the 870 validation calls, taken from that dataset (CC BY 4.0).
- Conference code: <https://github.com/WzjCoder/LLM4Band> (we checked commit `9699441`).
- Pre-trained model: `Qwen/Qwen1.5-0.5B` at revision `8f445e3628f3500ee69f24e1303c9f10f5342a39`, under its own license.
  Its `model.safetensors` (SHA-256 `a88bcf41b3fa9a20031b6b598abc11f694e35e0b5684d6e14dbe7e894ebbb080`) is the file we
  used. The runs without an LLM read only its `config.json`.

## Level 2: recompute from the released results

Python 3.13.13 with `requirements-level1.txt` (tested); the commands of this section need only numpy and matplotlib, except that
`finalize_enc_hcq_2x2_v1_offline_v1.py` also needs scipy: without it the judge falls back to tabulated t quantiles and the
script reports a mismatch with the recorded `result.json` (exit 1).
Every per-call file lists its calls as `<scenario directory>/<file>`; macro MSE is the mean of the High BW, Low BW and
Fluctuating means. `docs/GLOSSARY.md` maps the row labels that `main_table_unified_v1.py` prints ("Schaferct(public)"
is the challenge baseline, "LLM4band++ (Qwen)" the one-token LLM variant, ...) to the rows of Table I.

| Result | Command | Reads |
|---|---|---|
| Table I, rows from per-step predictions | `python3 scripts/arb/main_table_unified_v1.py` | `arb_perstep_dump_v1/perstep.npz` (Pioneer, challenge baseline, Schaferct-R, MLP), `llm4bandpp_perstep_dump_v1/` (one-token variant), `llm4band_conf_perstep_dump_v1/` (LLM4Band), `main_table_unified_v1/extra/` (Decision Transformer), `_deleak.json` (712-call subset) |
| Table I, receiving-rate echo | `python3 scripts/arb/offline_echo_row_v1.py` | `perstep.npz`, `_deleak.json`, `main_table_unified_v1/result.json` (check of the Pioneer row) |
| Table I, deployed row and paired intervals | `python3 scripts/paper/table1_ch_rows_v1.py` | the same per-step exports, `_deleak.json`, `nl_2x2_v1/eval/CHs0-2.json` |
| Tables I to V | `python3 scripts/paper/make_tables_v2.py` | the result files above and `experiments/registry.jsonl` |
| Table II per-step row, supplement intervals (+2.2% [−4.0, +8.4], +0.1% [−4.8, +5.0], +2.7% [−0.2, +5.5]) | `python3 scripts/arb/perstep_position_ci_v1.py` | `llm_indispensability/paper_data/raw/`, `pretrained_fulltrain_fourth_arm/raw/` |
| Encoder by reward ablation, Section V-C (8.1%, 6.4% to 10.2%; Low BW 5.0%, 2.5% to 8.0%) | `python3 scripts/encoder/nl2x2_v1/judge_nl2x2_v1.py dry` | `nl_2x2_v1/eval/`, `llm_indispensability/paper_data/per_trace.csv` |
| Capacity anchor, Section V-B (6.386 to 5.819) | `python3 scripts/encoder/anchor_ablation_v1.py summarize` | `anchor_ablation_v1/eval/`, `nl_2x2_v1/eval/` |
| HCQ weight sweep (6.25 at 0, 5.45 at 0.8, 5.48 at 1.0) | `python3 scripts/encoder/ch_lambda_sweep_v1.py summarize`, then `python3 scripts/paper/make_fig_lambda_supp_v2.py` (Fig. S1) | `ch_lambda_sweep_v1/eval/`, `nl_2x2_v1/eval/` |
| Schaferct's network with our recipe (5.83) | `python3 scripts/encoder/finalize_scharch_v1_offline_v1.py` | `schaferct_arch_recipe_v1/eval/`, `nl_2x2_v1/eval/` |
| Mamba aggregator, supplement (5.674 against 5.797, [−0.180, −0.058], threshold 0.152) | `python3 scripts/finalize_aggregator_mamba_control_v1_offline_v1.py` | `aggregator_mamba_control_v1/`, `llm_indispensability/paper_data/raw/NLs*` |
| Corrected-encoder ablation on the LLM variant, supplement (−6.4%, −27.4%) | `python3 scripts/finalize_enc_hcq_2x2_v1_offline_v1.py` | `enc_hcq_2x2_v1/per_call_metrics.csv` |
| Supplement tables S3 and S4 | `python3 papers/revision-v2/supplement/make_supp_tables.py` | as above |

All paths in the last column are under `experiments/results/`. The scripts that end in `_offline_v1.py` and
`perstep_position_ci_v1.py` compare their output with the recorded result file and print whether it matches. The others
rewrite their result file in place; the content is identical, except that `main_table_unified_v1/result.json` then
holds only the seven rows whose inputs ship (the recorded file also lists rows the paper does not use), and that
`offline_echo_row_v1.py` writes the absolute path of its input into the `source` field (the numbers are unchanged).

## Level 3a: re-evaluate the released checkpoints (needs the public calls)

Needs torch and numpy; a CPU is enough.

1. Download and unpack the emulated dataset into one directory, say `emulated/`.
2. Rebuild the 870 validation calls. Each is a public file copied unchanged into one of four scenario directories:

   ```bash
   python3 scripts/arb/make_validation_scenarios_v1.py --emulated emulated --out scen --check
   ```

   `--check` compares every call with the per-step export (number of steps, ground truth, short-window features).
3. Evaluate a checkpoint with our per-call evaluator. The C-H network is self-contained in
   `scripts/alphartc/deploy/ch_estimator_v1/ch_estimator_v1.py`, which the evaluator imports as `estimator.py`:

   ```bash
   mkdir -p ch_code && cp scripts/alphartc/deploy/ch_estimator_v1/ch_estimator_v1.py ch_code/estimator.py
   python3 scripts/alphartc/deploy/nl_estimator_v1/src/eval_value_per_file.py --code-dir ch_code --scen scen \
     --ckpt scripts/alphartc/deploy/ch_estimator_v1/ckpt/ch.pt --device cpu --chunk 256 --tag CHs1_cpu --out CHs1_cpu.json
   python3 scripts/alphartc/deploy/ch_estimator_v1/compare_ch_equiv_v1.py CHs1_cpu.json experiments/results/nl_2x2_v1/eval/CHs1.json
   ```

   The comparison passes when every call is present, the per-call MSE differs by less than 1e-3 (relative) and the macro
   MSE by less than 1e-4. Our own CPU re-evaluations are in `scripts/alphartc/deploy/ch_estimator_v1/equiv/`
   (`CH*_cpu.json`, with the comparisons in `check_*.json`): the largest per-call difference from the GPU evaluation made at
   training time is 3.1e-6.

| Checkpoint (`scripts/alphartc/deploy/ch_estimator_v1/ckpt/`) | Run | Reference per-call file (`experiments/results/`) | Macro MSE |
|---|---|---|---|
| `ch.pt` | C-H seed 1, the deployed estimator | `nl_2x2_v1/eval/CHs1.json` | 5.795 |
| `ch_s0.pt`, `ch_s2.pt` | C-H seeds 0 and 2 | `nl_2x2_v1/eval/CHs0.json`, `CHs2.json` | 5.868, 5.792 |
| `ch_l00s0.pt` to `ch_l00s2.pt` | C-B (λ = 0) seeds 0 to 2 | `nl_2x2_v1/eval/CBs0-2.json` | 6.313, 6.161, 6.280 |
| `ch_l06s1.pt`, `ch_l08s1.pt` | λ = 0.6 and 0.8, seed 1 | `ch_lambda_sweep_v1/eval/CHl06s1.json`, `CHl08s1.json` | 5.524, 5.462 |
| `ch_l10s0.pt` to `ch_l10s2.pt` | λ = 1.0, seeds 0 to 2 | `ch_lambda_sweep_v1/eval/CHl10s0-2.json` | 5.539, 5.447, 5.463 |
| `ch_a0s2.pt` | no capacity anchor, λ = 0.4, seed 2 | `anchor_ablation_v1/eval/A0l04s2.json` | 6.356 |

The supervised MLP (Table I, seed 0; seeds 1 and 2 as well) is in `experiments/results/supervised-mlp-baseline-3seed-50k-v1/seed*/`:

```bash
python3 scripts/baselines/eval_supervised_mlp.py --checkpoint experiments/results/supervised-mlp-baseline-3seed-50k-v1/seed0/checkpoint_final.pt \
  --dataset scen --output mlp_s0.json --device cpu --scenario-dir "High BW=scen/high_bw_call" --scenario-dir "Low BW=scen/low_bw_call" \
  --scenario-dir "Fluctuating=scen/high_fluctuating_bw" --scenario-dir "Fluctuating=scen/low_fluctuating_bw"
```

Its per-call MSE matches the per-step predictions of `perstep.npz` (`pred__MLP_seed0`).

## Level 3b: retrain C-H and its variants

### Data

1. The training calls are those of the conference version's split: 8464 of the 9405 public calls for training and 941
   held out, the 870 validation calls among the held-out ones. The split was drawn by the conference script
   (`dataset/split_emulated_dataset&make_pickle.py`, `random.shuffle` without a seed), which copied the two parts into
   two directories; we kept them. `experiments/results/training_split_v1/split_v1.json` lists both parts with the
   SHA-256 of every file. Put the 8464 training calls into TRAIN_CALLS and check their hashes.
2. Rebuild `MRE_4.pickle`, the balanced pickle our runs trained on:

   ```bash
   python3 scripts/encoder/make_balanced_pickle_v1.py --train-dir TRAIN_CALLS --out MRE_4.pickle \
     --from-index experiments/results/training_split_v1/mre4_index_v1.npz
   ```

   `mre4_index_v1.npz` gives the call and step of each of the 3,500,000 transitions, in pickle order. MRE_4 was drawn
   without a recorded index; `scripts/encoder/export_split_mre4_index_v1.py` recovered it on our server by matching
   every transition to its call and step (observation, action and next observation byte for byte; 47,660 transitions
   that occur more than once, by true capacity and reward). The pickle rebuilt from the index equals MRE_4 in all six
   fields, and every source is a training call (`training_split_v1/summary_v1.json`; registry entry
   training-split-mre4-index-export-v1). To draw a new sample instead, run the same script with
   `--per-bin 500000 --reward-lambda 0.4 --skip-bins 3-4 --seed 0` in place of `--from-index`; it writes its own
   (call, step) index next to the pickle.

   Every step of a call is one transition, with the logged bandwidth prediction as the action and the reward of Eq. (1),
   λ = 0.4, missing quality scores replaced by the call mean and NaN rewards set to 1. Transitions are
   grouped into the capacity bins of the conference script `dataset_analysis/range_average.py` ([0, 1), [1, 2), ...,
   [6, 7), at least 7 Mb/s) and at most 500,000 are drawn per bin. Our pickle has 3,500,000 transitions: 500,000 per
   bin, except that the 3 to 4 Mb/s bin is empty (the cause was not recorded; `--skip-bins 3-4` reproduces it) and the
   last bin includes the 1,444 transitions with a missing capacity. Training drops those 1,444 when it relabels the
   rewards. The pickle needs about 8.5 GB on disk.

### Code

Our training directory is the conference directory `Qwen_for_bwe/Qwen_LoRa` with its files replaced by ours. The
package ships them complete, so no patch is applied:

- `scripts/alphartc/deploy/nl_estimator_v1/src/IQL.py`: IQL training with the HCQ reward relabeled from the pickle
  (`relabel_hcq_reward`, error term capped at 5), the capacity anchor (Huber loss of the policy mean to the logged
  capacity, weight 1, threshold 1 Mb/s), the replay buffer kept in host memory, and a checkpoint every `--eval_freq`
  updates;
- `module.py`, `dualEncoder.py`, `model.py`: encoders and layers (the conference `StateEncoder`, our multi-scale encoder);
- `estimator.py`: the multi-scale cells (M-H, M-B), without the LLM;
- `scripts/encoder/nl2x2_v1/estimator_conf.py`: the conference-encoder cells (C-H, C-B), used as `estimator.py`.

The files keep the license headers of the code they derive from. Set up one directory per encoder and point the paths
at your copies (`IQL.py` lists the evaluation directory when imported, so it must exist; its content is not used):

```bash
D=scripts/alphartc/deploy/nl_estimator_v1/src; W=$PWD/work; X=$PWD/challenge
mkdir -p $W/M $W/C $W/out $X/solution/dataset/training_dataset_pickle/MRE $X/solution/evaluate_dataset $X/Qwen1.5
cp $D/IQL.py $D/module.py $D/model.py $D/dualEncoder.py $D/estimator.py $W/M/
cp $D/IQL.py $D/module.py $D/model.py $D/dualEncoder.py $W/C/ && cp scripts/encoder/nl2x2_v1/estimator_conf.py $W/C/estimator.py
mv MRE_4.pickle $X/solution/dataset/training_dataset_pickle/MRE/
hf download Qwen/Qwen1.5-0.5B --revision 8f445e3628f3500ee69f24e1303c9f10f5342a39 --local-dir $X/Qwen1.5/Qwen1.5-0.5B-hf
sed -i "s#/path/to/challenge#$X#g" $W/M/IQL.py $W/M/estimator.py $W/C/IQL.py $W/C/estimator.py
```

`IQL.py` sets `CUDA_VISIBLE_DEVICES` to `0, 1` when imported; choose `--device cuda:0` or `cuda:1`.

### Commands

One run (cell C-H, seed 1, the deployed estimator):

```bash
cd $W/C && python3 -u IQL.py --device cuda:0 --env nl2x2-CHs1 --max_timesteps 50000 --checkpoints_path $W/out \
  --buffer_size 3500000 --eval_freq 5000 --seed 1
```

The checkpoint is `$W/out/IQL-nl2x2-CHs1-<id>/checkpoint_50000.pt`; evaluate it as in Level 3a above with `--code-dir $W/C`.

| Cell or variant | Directory | Extra arguments | Seeds |
|---|---|---|---|
| C-H (conference encoder, HCQ λ = 0.4) | `$W/C` | none | 0, 1, 2 |
| C-B (conference encoder, conference reward) | `$W/C` | `--reward_lambda 0.0` | 0 to 4 |
| M-H (multi-scale encoder, HCQ) | `$W/M` | none | 0 to 4 |
| M-B (multi-scale encoder, conference reward) | `$W/M` | `--reward_lambda 0.0` | 0, 1, 2 |
| Capacity anchor removed | `$W/C` | `--capacity_aux_weight 0.0`, with or without `--reward_lambda 0.0` | 0, 1, 2 |
| HCQ weight sweep | `$W/C` | `--reward_lambda X`, X in 0.2, 0.6, 0.8, 1.0 (0 and 0.4 are C-B and C-H) | 0, 1, 2 |
| Schaferct's network with our recipe | `$W/C` with `estimator.py` from `scripts/encoder/make_schaferct_arm_v1.py` | none | 0, 1, 2 |

`scripts/encoder/nl2x2_v1/run_nl2x2_v1.sh` is the job queue we used for the four cells; before training it checks the
hashes of the files in the two directories. The LLM variants (Table II and the supplement) and the Mamba arm cannot be
retrained from this package: their estimator files are not included.

### Settings

Batch 512; 50,000 updates; discount 0.99; target update rate 0.005; expectile 0.7; inverse temperature 3 with the
advantage weight capped at 100; learning rates 3e-4 for value, critic and actor, with cosine decay of the actor's;
reward relabeled as `capped_mre` from the pickle's λ = 0.4 to `--reward_lambda` (default 0.4) with the error term
capped at 5; capacity anchor weight 1 with Huber threshold 1 Mb/s; replay buffer 3,500,000; action bound 20 Mb/s.
Seeds set Python, NumPy and PyTorch (`set_seed`, `deterministic_torch=False`).

We trained on V100S-PCIE-32GB GPUs, two runs per GPU; a run needed about 0.4 GiB (C cells) to 0.75 GiB (M cells) of GPU
memory and about 20 GB of host memory for the pickle and the replay buffer. Python 3.10.18, torch 2.8.0 (CUDA 12.6),
transformers 4.57.0, peft 0.17.1, numpy 2.1.2; the full list is in `docs/requirements-train.txt`. The time per run of
these cells was not recorded.

### What is not bitwise reproducible

- Training uses `deterministic_torch=False` on GPUs, so a rerun on our pickle with the same seed is not bitwise
  identical; the pickle itself is rebuilt exactly (Data, step 2).
- Expect differences of the size of the seed spread: macro MSE of one arm varies across seeds by up to 0.34 (M-B; 0.31 for the LLM variants of Table S3), and C-H
  seeds 0 to 2 give 5.868, 5.795 and 5.792. Compare a retrained recipe with the three-seed means of Table I and the
  supplement, not with one checkpoint.
