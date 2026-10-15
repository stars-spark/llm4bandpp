<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Low-bandwidth closed-loop re-verification, collector v5 (switch-closedloop-lowbw-v5)

**Written 2026-09-18, before the batch run started.** Previously only one pipeline smoke run of arm_pioneer was performed and is not counted as a result.
Question: with the collector fixed, does the closed loop at 200 kbps and below stop collapsing?

## Configuration
- Collector: `STALENESS_COLLECTOR=v5` (fixed packet-interval definition plus per-stream loss counting); everything else is identical to perf-v1: same run script, same driver, slack 80, obs trace on, 3 repetitions per cell, at most 3 attempts per cell; collapsed cells are recorded in the failure list and the batch continues.
- Profiles: lowbw_100, lowbw_156, paper_low_200 (loss 1%).
- Arms: switch_nn, arm_pioneer, arm_schaferct_public, arm_schaferct_retrained. **arm_mlp is not included**: `closedloop-collapse-delay-dose-v2` has already established that it responds to queuing delay with positive feedback, so its collapse needs no collector defect to explain it, and under v5 replay its median prediction is 0.
- GCC does not read the 150-dimensional observation and is not affected by the collector, so the perf-v1 results on the same profiles are cited directly as reference and are not rerun.
- 36 runs in total. The metric is network utility recomputed with a source cap of 610 kbps, threshold 5.27 (from `switch-closedloop-noise-v1`).

## Criteria: conclusions per profile, no overall criterion
For each profile three questions are answered separately, each with its own holds or does not hold:
- S1 no longer collapses: switch_nn has at least 2 valid runs among its 3 repetitions.
- S2 not worse than the best single arm: the mean utility of switch_nn is not lower than the maximum mean utility among the valid fixed arms minus 5.27. A fixed arm with no valid run on that profile is not counted.
- S3 versus GCC: the mean utility of switch_nn minus the mean utility of GCC in perf-v1; a difference not less than 5.27 is recorded as better, not greater than −5.27 as worse, and in between as comparable.

The registry verdict is mapped from S1, because S1 answers the question of this experiment, whether the fix removed the collapse: holds if S1 holds on at least two of the three profiles, inconclusive if on one, does not hold if on none. S2 and S3 are written into the conclusion text per profile and are not merged into the verdict.

## Report only
The number of collapsed cells per arm per profile compared with perf-v1; rate score, queuing delay, loss, underestimation ratio, overestimation ratio; the arm selection share and switch count of switch_nn (splitting each attempt at the point where the step counter resets to zero); the distribution of the long-window loss count feature (should return to the offline magnitude).

