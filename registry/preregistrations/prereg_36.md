<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Encoder plus HCQ 2x2 ablation, improved version (2026-10-03)

Two confirmatory claims are registered, sharing the same batch of runs: ablation-enc-hcq-2x2-v1 (encoder plus HCQ combined, macro MSE) and ablation-hcq-lowbw-v1 (HCQ alone, low-bandwidth MSE).
This file fixes the criteria; no changes after launch.

## What the method changed (relative to the original ablation)

All four cells share: 15-token interface, LoRA (rank 16, alpha 32, all linear layers), capacity anchor (weight 1.0, Huber knee 1 Mbit/s), 50000-step fixed endpoint, batch 512, three optimizers with learning rate 3e-4, actor cosine annealing, IQL hyperparameters β 3.0, τ 0.7, γ 0.99, soft update 0.005; only the encoder and the reward differ, selected by two environment variables (an error is raised if either is missing).
- Conference-version encoder: split-sum 15-token version, the i-th token is LeakyReLU(LayerNorm(W_i x_i + b_i)), the sum of the 15 tokens before activation equals the conference-version Linear(150,1024).
- Multi-scale encoder, corrected: only the short-term and long-term LSTMs and the 2-way gating are kept; the cross-scale and bidirectional branches built on the concatenated time axis are removed, and the unused TemporalAttention and prototype layer are no longer constructed; the two-layer cross-feature aggregator is kept; the output is a per-position Linear(8,1024) followed by LayerNorm, GELU, Dropout 0.1.
- Reward: the same MRE_4 relabeled via relabel_hcq_reward, relative error term not truncated; λ 0 is conference reward, λ 0.4 is HCQ. The four cells have bit-identical state, action, next state, termination, capacity columns and valid rows, differing only in the reward column.

## Four cells and seeds (fixed before running, no additions after seeing results)

| Cell | Encoder | Reward | Seeds |
|---|---|---|---|
| C-B | conference-version split-sum 15-token | λ 0 | 0, 1, 2, 3, 4 |
| C-H | same as above | λ 0.4 | 0, 1, 2 |
| M-B | corrected multi-scale 15-token | λ 0 | 0, 1, 2 |
| M-H | same as above | λ 0.4 | 0, 1, 2, 3, 4 |

16 training runs total. The two main-endpoint cells use 5 seeds to reduce the seed noise of the 15-token LoRA interface (the three-seed macro range of a single cell is 2.6% to 9.3%). Only the 50000-step checkpoint is read.

## Evaluation protocol

Unified protocol on the 870 calls (a1-unified-offline-matrix-protocol-parity-v1, main-table-unified-v1): high bandwidth 77, low bandwidth 469, the two fluctuation directories merged 324; per call, the nanmean of the per-step squared error (in squared Mbit/s); calls are averaged within each scenario, and macro is the simple average of the three scenarios. Each cell first averages the MSE of its seeds on the same call. The scoring code imports fm from scripts/arb/main_table_unified_v1.py; re-evaluating the checkpoint of the earlier version must give a value within 0.5% of 6.743.

## Claim one: ablation-enc-hcq-2x2-v1 (encoder plus HCQ, macro MSE)

- Main endpoint: relative improvement in macro MSE of M-H over C-B, (C-B − M-H) / C-B × 100, each cell using seeds 0 to 4.
- Interval: scenario-stratified paired resampling of calls (the same resampled calls for both cells), 10000 times, seed 20260909, 5th and 95th percentiles as the 90% interval.
- Threshold: 1.631% (the increment from HCQ alone in our earlier version's Table III, the reportable tier of criteria-amendment-v2).
- Safety line (criteria-amendment-v2 group D): when any scenario's M-H scenario MSE is higher than C-B, the difference divided by 3 then divided by the C-B macro value is the macro rise from that scenario's worsening; more than 1% crosses the safety line.
- Conclusion: holds = 90% interval lower bound greater than 0, point estimate not below 1.631%, safety line not crossed; direction only = point estimate positive but the holds condition not met; does not hold = point estimate not positive or safety line crossed.
- Invalidation: code hash does not match the manifest, environment variable combination is not exactly four kinds, any run missing the 50000-step checkpoint, evaluation export misaligned, recomputed checkpoint of the earlier version beyond 0.5%. An invalidated result is not assigned to any of the three tiers; after diagnosis, a rerun is registered separately as "void, rerun".

## Claim two: ablation-hcq-lowbw-v1 (HCQ alone, low-bandwidth MSE)

HCQ's relative error term mainly acts on low-capacity samples (the only per-scenario argument for HCQ in our earlier version is that adding HCQ gives the best low-bandwidth result), and under the rule that the main endpoint follows the purpose of the method, low-bandwidth MSE is its appropriate readout.
- Main endpoint: relative improvement of the HCQ main effect on low-bandwidth MSE, base two cells (C-B, M-B) averaged versus HCQ two cells (C-H, M-H) averaged, each cell using only seeds 0, 1, 2 (balanced design), (base − HCQ) / base × 100.
- Interval: paired resampling of the 469 low-bandwidth calls, 10000 times, seed 20260909, 90% interval.
- Threshold: 1.631%.
- Safety line: the mean of the two HCQ cells against the mean of the two base cells, judged on macro MSE by group D; a macro rise of more than 1% from the worsening of any scenario crosses it.
- Three conclusion tiers and invalidation conditions same as claim one.

## Predictions unfavorable to us
1. The point estimate of HCQ's main effect on macro MSE is within plus or minus 1% (capacity anchor already absorbs high-bandwidth correction).
2. The interaction term is within plus or minus 1 percentage point and the interval crosses 0; the synergy claimed in our earlier version does not hold.
3. The main effect of the multi-scale encoder is negative at low bandwidth.
4. Claim 1 is at least as likely to land in the direction only tier as in the holds tier.
5. All four cells' macro MSE are between 5.5 and 6.3, far below the main table's 6.743; this is mainly due to capacity anchor and the 15-token interface, not attributable to the encoder or HCQ.

## Report-only items

Encoder main effect and reward main effect macro readings and interaction term (seeds 0 to 2 balanced), each with a 90% interval computed the same way; the two main endpoints on the 712 leakage-free subset; MSE, e+, e− for the four cells across three scenarios; each seed's own main endpoint and seed-level t interval (including training randomness); per-call win rate; 10k to 40k training curves (diagnostic only); parameter counts and single-batch latency for both encoders.

## Runs

Artifacts: server /path/to/server/work/enc_hcq_2x2_v1/, ~/work/outputs/enc_hcq_2x2_v1/; local experiments/results/enc_hcq_2x2_v1/.

