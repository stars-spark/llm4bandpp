<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Estimator-only run in the 720p closed loop (2026-10-06 night, fixed before running)

## Design

- **Three arms**: Same as hd720-learned-baselines-v1, i.e., deployed C-H, Schaferct-R, supervised MLP, collector v6, 5 kbps floor.
  - Only change: no probing envelope for any arm, STALENESS_ENVELOPE=0.
  - Run script v24.
- **Conditions**: hd_c1, hd_c2, hd_r1, hd_r2, crossed with Johnny, FourPeople, 8 cells total, 2 runs per arm per cell, 48 runs total, on a single container pair.
- **Primary endpoint and decision**: identical to hd720-learned-baselines-v1, i.e., C-H minus Schaferct-R, calling hd720_ch_eval_v1.judge, non-inferiority bound −6; safety line: any cell more than 10 points lower, or all runs of a cell invalid; superiority reported but not judged.
- **Report only**: C-H minus MLP, plus packet loss, delay score, and freezes.

## Predictions unfavorable to us

- Without the probing envelope, all three may starve or overload at 1 Mbit/s or on trace windows.
  - Supervised MLP overestimates by 1.845 at low bandwidth and is most likely to overload.
  - C-H overestimates by 0.66 at low bandwidth, also higher than Schaferct-R's 0.53, and may be worse than Schaferct-R.

