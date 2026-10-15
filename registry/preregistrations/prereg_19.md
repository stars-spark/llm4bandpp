<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Does the HCQ quality term help in low-capacity closed loop (2026-10-06 evening, written before running)

## Design

- **Conditions**: same as lowbw-chf-vs-conf-v1, constant 100, 200, 300, 400 kbps, source 320x240, 15 fps, delay 50 ms, no packet loss, 120 s.
- **Three arms**: all deployed C-H seed 1, plus 5 kbps floor, without probing envelope (arm_ch_x), only weights changed.
  - l04: ch.pt, λ 0.4.
  - l10: ch_l10s1.pt, λ 1.0, only error term.
  - l00: ch_l00s1.pt, λ 0, only quality term, i.e. seed 1 of the C-B cell of nl_2x2.
  - 3 runs per cell, rotating, 36 total, two container pairs in parallel, run script v26.
- **Weights**: CPU equivalence check with the original evaluation script on gpu-server-1.
  - Pass gate: per-call relative difference less than 1e-3, macro less than 1e-4.
  - Discrimination control: λ 0.4 seed 1's CPU result must fail the gate against both references.
  - After the runs, seed_weight_check_v3.py verifies step by step that the weights actually used in each run match the arm key; mismatches are treated as tool issues and not judged.
- **Primary endpoint**: judge(arm=l10, ref=l04), i.e. the same judgment function as lowbw_chf_vs_conf_v1.
  - D is the utility difference with four cells equally weighted, λ1.0 minus λ0.4; within-cell resampling 10000 times, seed 20261004, 90% interval; non-inferiority bound −5.27.
  - Holds: λ 1.0 is not worse than λ 0.4, i.e. the quality term has no measurable benefit in low-capacity closed loop.
  - Direction only: D greater than −5.27, but lower bound not greater than −5.27.
  - Does not hold: λ 1.0 worse by 5.27 or more, or safety line triggered (any cell lower by 10 points or more, or all λ 1.0 runs invalid in some cell), i.e. the quality term is useful in closed loop.
- **Report only**:
  - judge(arm=l00, ref=l04).
  - Per-cell utility, video rate, queueing delay, VMAF, SSIM, floor triggers.

## Predictions unfavorable to us

- The primary endpoint may well hold. The offline difference is only 0.34, and below 1 Mbit/s the error term itself also penalizes overestimation.
- If it does not hold, these readings show that the tradeoff exists.

