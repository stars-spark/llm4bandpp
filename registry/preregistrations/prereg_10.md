<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Low-bandwidth standalone run confirmation after adding a 5 kbps estimation floor to C-H (drafted 2026-10-05 around 10:15 Beijing time, fixed before running)

## 1. Estimator under test

- **C-H itself is unchanged.**
  - Module deploy/ch_estimator_v1/ch_estimator_v1.py, sha256 prefix cec41ba6.
  - Weights ckpt/ch.pt, prefix 954c68d2, seed 1.
  - Collector v6, no probing envelope.
- **The only change: the estimate is kept at or above 5 kbps.**
  - Basis for the value: the AlphaRTC branch's congestion_controller::GetMinBitrateBps() returns 5000, and upstream libwebrtc's kCongestionControllerMinBitrate is also 5 kbps. This is the absolute floor libwebrtc sets for any congestion control estimate, not tuned to this testbed.
  - Code: deploy/online_llm_arms_v8.py, switch BWE_MIN_BPS_FLOOR=1.
  - Run path: entry point BandwidthEstimator_staleness_v15.py, run script run_staleness_once_twocontainer_midsnap_v20.sh.
- **The LLM4Band arm is unchanged.**
  - The released online checkpoint of the conference version, loaded via the same path as lowbw-ch-vs-conf-v1, no floor.
  - In the existing 24 or more LLM4Band runs an estimate of 0 never appeared, so the floor is a no-op for it and is not added.

## 2. lowbw-chf-vs-conf-v1 (criteria identical to claim one of lowbw-ch-vs-conf-v1)

- **Conditions.** Constant 100, 200, 300, 400 kbps (deploy/profiles/lowbw_nl/nlc_*.profile), latency 50 ms, no packet loss, 120 seconds. Source 320x240, 15 fps, collector v6.
- **Arms.** C-H with floor and without probing envelope (ch0), LLM4Band without probing envelope (cf0). 3 runs per cell, arms rotate within the same capacity and the same repetition number, 24 runs in total. Run script v20, two container pairs in parallel.
- **Primary endpoint D.** The utility difference with equal weight over the four capacity cells, C-H minus LLM4Band, each cell taking the mean of three runs.
- **Interval.** Within each cell each arm is resampled with replacement 10000 times, seed 20261004, 90% interval.
- **Decision (non-inferiority bound −5.27).**
  - holds: the lower bound is greater than −5.27, and the safety line is not triggered.
  - direction only: D is greater than −5.27, but the lower bound is not greater than −5.27.
  - does not hold: D is not greater than −5.27, or the safety line is triggered.
- **Safety line.** In any cell the C-H mean is more than 10 points below LLM4Band, or C-H is invalid in all three runs of some cell.
- **Other rules.** If LLM4Band is invalid in all three runs of some cell, that cell is removed and this is stated. If fewer than 3 cells are usable, the judgment is inconclusive.
- **Decision script.** scripts/alphartc/deploy/lowbw_chf_vs_conf_v1.py. judge and selftest are taken verbatim from lowbw_ch_vs_conf_v1.py, selftest has passed.
- **Report only.** Utility, video rate, VMAF, SSIM for each arm in each cell; for each C-H run the number of steps where the floor triggered, and the number of steps with an estimate of 0 (should be 0).

## 3. The deployed system with probing envelope is not rerun
- **Verification result.** Replay check floor_noop_check_v1.py (results in experiments/results/floor_noop_check_v1/result.json): among the existing 60 C-H runs with envelope v6 added, no step shows "model output below 5 kbps and probing envelope output also below 5 kbps." These 60 runs come from 36 runs of hd720-closedloop-ch-v1, 9 runs of compete-flow-ch-v1, 12 runs of lowbw-ch-vs-conf-v1 with envelope v6 added, and 3 runs of ch-dev-smoke-v1.
- **Why this means no rerun is needed.**
  - The model value appears in the probing envelope in only three places: empty window, max(x, F) in the clear state, and max(x, F) in the mild state.
  - Therefore, as long as the probing envelope output at a step is not below 5 kbps, that step uses F or shadow GCC, and adding the floor does not change the output.
  - If the output is unchanged, the input to the next step is also unchanged, and by stepwise induction the entire run is bit-for-bit identical.
- **The negative control is valid.** The same check applied to runs without the probing envelope found 11 violations, showing that the check has discriminating power.
- **Conclusion.** The readings of hd720-closedloop-ch-v1, hd720-ch-vs-nl-v1, compete-flow-ch-v1, and lowbw-ch-vs-conf-env6-v1 hold as they are for the deployed artifact with the floor added.

## 4. Predictions unfavorable to us (written before the run)

1. **200 kbps still lags by about 5 to 6 points.** The floor does not trigger at 200 kbps; this cell in the original batch is −5.66, and the second smoke test gives 64.6 versus 70.1 for LLM4Band in another batch. If 400 kbps also lags by about 2 points, D may be between −1 and −3, and the lower bound may reach −5.27.
2. **At 100 kbps, some individual runs may still be invalid.** Smoke test two has only 3 runs, and the number of steps where the floor triggers varies widely (5 to 62 steps).
3. **The absolute utility at 100 kbps is only about 25 points.** LLM4Band is about 22 points; both are very poor, and non-inferiority holding does not mean 100 kbps is usable.

