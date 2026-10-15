<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Low-capacity anchor removal closed loop (lowbw-noanchor-200-v1, 2026-10-08)

Written before running. Script `scripts/alphartc/deploy/lowbw_noanchor200_v1.py`.

## Design

- **Conditions**: two, both with one-way delay 50 ms, both 320x240, 15 fps.
  - Constant 200 kbit/s, no loss (lowbw_nl/nlc_200);
  - 200 kbit/s plus 1% random loss (lowbw_loss/nlc_200_l1).
- **Arms**: three arms, none with probing envelope.
  - ch0: deployed C-H seed 1, plus 5 kbps floor.
  - a0: same recipe with capacity anchor removed (A0l04 cell of anchor-ablation-v1), plus 5 kbps floor.
    - The seed is chosen by the deployed-seed rule, the median of the three seeds by macro MSE: seeds 0, 1, 2 are 6.460, 6.342, 6.356 respectively, so seed 2 is taken.
  - cf0: LLM4Band.
- **Replicates**: 4 per condition per arm, arms rotated within replicate number, 24 total. Run script v29, two container pairs in parallel.

## Criteria

- **Primary endpoint D**: utility difference of anchor removed minus deployed.
  - Two conditions equally weighted, each condition takes the difference of the two arm means.
  - Interval: within each condition, each arm is resampled with replacement 10000 times, seed 20261008, 90% interval.
- **Holds**: lower bound > 0 and D ≥ 3, i.e. at least half of the roughly 6-point gap is recovered.
- **Direction only**: D > 0.
- **Does not hold**: D ≤ 0, or the anchor-removed arm is invalid in all 4 runs of some condition.
- **Inconclusive**: the deployed-system arm is invalid in all runs of some condition.
- **Report only**:
  - anchor removed minus LLM4Band;
  - deployed minus LLM4Band;
  - per-arm per-condition video rate, queueing delay, VMAF, broken-call count.

## Unfavorable prediction

The HCQ error term itself also pulls the estimate toward capacity; after anchor removal it may still send too much and queueing may still be long, with D near 0. If so, the closed-loop source of the overestimation remains undetermined.

