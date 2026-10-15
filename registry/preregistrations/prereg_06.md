<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Does the 720p closed-loop conclusion depend on the deployed seed (drafted 2026-10-05 around 18:20 Beijing time, fixed before running)

## Design

- **Tested.** Deployed system (C-H plus 5 kbps floor plus probing envelope v6), with weights replaced by seed 0 and seed 2. Weights taken from the C-H cell of ablation-nl-enc-hcq-2x2-v1.
  - Seed 0: sha256 prefix 6641d462.
  - Seed 2: sha256 prefix d1964e7d.
- **Equivalence check.**
  - Method: the weights are evaluated on CPU on gpu-server-1 with the original evaluation script and compared call by call with the training-side evaluation. Threshold same as seed 1: per-call maximum relative difference less than 1e-3, macro relative difference less than 1e-4.
  - Seed 0: passed, maximum relative difference 1.3e-6. Discriminating control (seed 0 vs seed 2 reference) did not pass, indicating the check has discriminating power.
  - Seed 2: verified automatically before the run, which does not start if the check fails.
- **Run script v21.** v20 plus two weights, selected via STALENESS_CH_CHECKPOINT.
- **Conditions and sequences.** Same as hd720-closedloop-ch-v1: hd_c1, hd_c2, hd_c3, hd_c8, hd_r1, hd_r2 × Johnny, FourPeople, 12 cells total.
- **Arms and scale.** Three arms: GCC every 200 ms, seed 0, seed 2. 3 runs per arm per cell, interleaved round-robin, 108 runs total, two container pairs in parallel.
- **Primary endpoint D_S.** Per cell, the mean VMAF of the pooled valid runs of seeds 0 and 2 (equal to the average of the two seed means) minus GCC's mean VMAF, 12 cells equally weighted.
- **Decision.** Decided by hd720_ch_eval_v1.judge, rules identical to hd720-closedloop-ch-v1.
  - Interval: stratified resampling by cell 10000 times, seed 20261003, 90% interval.
  - Holds: lower bound greater than −6, and safety line not triggered.
  - Direction only: D_S greater than −6, but lower bound not greater than −6.
  - Does not hold: D_S not greater than −6, or safety line triggered.
  - Safety line: any cell lower by more than 10 points, or any cell of the combined arm entirely invalid.
  - Fewer than 6 usable cells judged inconclusive.
  - Neither seed is required to pass on its own, which avoids a multiplicative condition.
- **Report only.**
  - Difference of each seed against GCC, computed the same way.
  - Comparison with seed 1 in other batches: +4.58 in hd720-closedloop-ch-v1 and +4.38 in hd720-echo-attr-ch-v1.
  - Freezes, video rate, probing envelope rewrite.
- **Script.** scripts/alphartc/deploy/hd720_seeds_v1.py, selftest passed. Both seed arms use arm_ch_x, distinguished by the arm key in the job name.

## Predictions unfavorable to us

1. **Seed 0 has the worst offline macro MSE (5.868).** Its lead on 720p may be noticeably smaller than seed 1, or even lower than GCC in some cells.
2. **The magnitude of the initial spike varies by seed.** This was already seen in ch-lowbw-startup-explore-v1: initial estimate medians 608, 642, 180 kbps. Seed 2 starts more conservatively, so it may be better at the 1 Mbit/s condition and worse at the 8 Mbit/s condition.

