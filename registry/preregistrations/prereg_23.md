<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Small control replacing the cross-feature aggregator with a Mamba-style state space block (aggregator-mamba-control-v1)

## Procedure
- Only one thing is changed: the two-layer cross-feature Transformer aggregator in the encoder is replaced with two-layer Mamba-style selective state space blocks, and the rest of the code is unchanged (the generator `scripts/encoder/make_mamba_aggregator_arm.py` asserts that the hashes of the remaining files are unchanged). mamba-ssm is not available in the training environment, so the state space blocks are implemented in pure PyTorch; the aggregated sequence has only 15 tokens, so the step-by-step scan overhead is negligible. The two aggregators have 1856 versus 1744 parameters.
- Main criterion arm MB: the no-LLM architecture-matched arm (15-token interface plus capacity anchor), seeds 0, 1, 2, 50k steps each, with the same code, same budget, and same evaluator as the NL arm of the existing baseline `llm-indispensability-mt-anchor-3seed`; the baseline is not retrained.
- The arm with the LLM (MBL) is report-only, seed 0, 50k steps, against the existing LLM arm seed 0.
- Trained on two GPUs of gpu-server-2.
- The 5-item CPU pre-check has passed: shapes match, parameter counts are of the same order, the last token can see the first token, the scan is causal, and all parameters receive gradients. The pre-check caught one real problem (the initial step size was too large so information could not reach the last token), which was corrected according to the original Mamba initialization.

## Criteria
The rules of `reanalysis_peer_metrics_p4.py` are followed: the three seeds are averaged call by call, a stratified paired bootstrap over the 870 calls with 10000 resamples is used, and the threshold is 2 times the standard deviation of the three-seed scenario means of the control arm.
The verdict rests on **macro MSE, MB against NL**: equal or worse is **holds** (switching to a state space model brings no gain, and keeping the Transformer aggregator is justified); better is **does not hold** (the state space model is better); indistinguishable is **inconclusive**.
Per-scenario MSE and overestimation rate, the 712 leakage-free subset, the single-seed reading of MBL, and the parameter counts and CPU single-forward latency of the two aggregators are all reported only.

## Predictions unfavorable to us
There are only 15 tokens, and both aggregators are more than sufficient, so the most likely result is a tie; in that case we can only report the two as indistinguishable, with the original design kept, and not that the Transformer is better. Mamba may also be slightly better.
