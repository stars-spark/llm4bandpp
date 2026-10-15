<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Probing envelope comparison under low-capacity packet loss (lowbw-loss1-env6-v1, 2026-10-08)

Written before the run. Script `scripts/alphartc/deploy/lowbw_loss1_env6_v1.py`.

## Design
- Conditions: constant 100, 200, 300, 400 kbit/s, each with 1% random packet loss, one-way 50 ms, 120 s, 320x240 Mobcal 15 fps, collector v6.
- Both arms use the deployed probing envelope v6:
  - ch6: deployed C-H seed 1, with 5 kbps floor;
  - cf6: LLM4Band.
- 3 runs per cell, 24 total; run script v29, two container pairs in parallel.

## Criteria (identical to lowbw-ch-vs-conf-env6-v1)
- Primary endpoint D: utility difference with four cells equally weighted (deployed minus LLM4Band); within-cell resampling 10000 times, seed 20261004, 90% interval.
- Holds: lower bound greater than −5.27, and safety line not triggered.
- Direction only: D greater than −5.27, but lower bound not above the threshold.
- Does not hold: D not greater than −5.27, or safety line triggered.
- Safety line: any cell lower by more than 10 points, or any cell of the deployed-system arm entirely invalid.
- Report only: per-cell utility, VMAF, video rate, queueing, broken calls, floor triggers.

## Unfavorable prediction
When run alone, under 200 kbit/s plus 1% packet loss the deployed estimator lags by 5.5. The probing envelope may not recover this gap, and the 200 kbit/s cell may approach the safety line.

