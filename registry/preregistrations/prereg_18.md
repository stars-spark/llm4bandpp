<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Additional seeds for the reward weight at low capacity (lowbw-lambda-seeds-v1, 2026-10-08)

Written before running. Script `scripts/alphartc/deploy/lowbw_lambda_seeds_v1.py`.

## Design

- Conditions: constant 100, 200, 300, 400 kbit/s, one-way 50 ms, no packet loss, 120 s, 320x240, 15 fps, collector v6. Identical to lowbw-lambda-ch-v2.
- Arms: all six arms are arm_ch_x plus a 5 kbps floor, without probing envelope, only the weight is changed.
  - λ 0.4 seeds 0, 2: ch_s0, ch_s2.
  - λ 0 seeds 0, 2: the C-B cells of nl_2x2_v1.
  - λ 1.0 seeds 0, 2: ch-lambda-sweep-v1.
  - Weights are byte-identical copies of the training checkpoints on gpu-server-2. sha256 is checked before the run. The run starts only after all CPU equivalence checks on gpu-server-1 pass.
- 3 runs per cell, arms rotate within blocks, 72 runs total. Run script v29, two container pairs in parallel.

## Criteria

- **Primary endpoint B (broken calls)**: B = (λ 0 broken calls + λ 1.0 broken calls) ÷ 2 − λ 0.4 broken calls.
  - Each weight merges seeds 0 and 2, 24 runs each.
  - Broken calls are counted as invalid runs, same counting as lowbw-lambda-ch-v2; invalid reasons are reported one by one.
- **Interval**: runs are resampled with replacement 10000 times within (capacity, arm) cells, seed 20261008, 90% interval.
- **Holds**: lower bound > 0 and B ≥ 3.
- **Direction only**: B > 0.
- **Does not hold**: B ≤ 0, or the safety line is triggered.
- **Safety line**: λ 0.4 total broken calls ≥ 4.
- **Report only**:
  - Broken calls per arm and per capacity;
  - utility difference after merging seeds: λ 1.0 vs λ 0.4, λ 0 vs λ 0.4, using lowbw_lambda_mid_v1.judge, bound −5.27;
  - video rate, queueing, VMAF.

## Unfavorable prediction

λ 0 with seed 1 had 4 broken calls, which may be specific to that seed; with new seeds λ 0 may have none, leaving only the λ 1.0 half of B.

