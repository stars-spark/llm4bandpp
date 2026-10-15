<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Low-bandwidth closed loop, no-LLM deployed estimator vs. LLM4Band (written on the evening of 2026-10-04, Beijing time, fixed before running)

Two confirmatory claims, same batch of runs:
- lowbw-nl-vs-conf-v1: estimator runs alone, no probing envelope;
- lowbw-nl-vs-conf-env6-v1: both arms with probing envelope v6.

## Design

- **Conditions**: constant 100, 200, 300, 400 kbps. Profiles are the new file deploy/profiles/lowbw_nl/nlc_*.profile, delay 50 ms, loss 0, 120 s; the body of the 400 profile is line-by-line identical to lowbw_400.
- **Other settings**: source 320x240, 15 fps, same as the existing 320x240 closed-loop batch; collector v6; run script v17; scheduler parallel_testbed_v1; two container pairs in parallel; one quality-scoring worker; balanced power mode.
- **Four arms, 3 runs per cell, 48 runs total**:
  - no LLM (arm_llm4bandpp_nl_x, weights nl_s1.pt), no probing envelope;
  - no LLM, with envelope v6;
  - conference version (arm_llm4band_conf_x, its released online checkpoint), no probing envelope;
  - conference version, with envelope v6.
  - Arms rotate within the same capacity and same repetition number.
- **Smoke**: not counted. One run each of no LLM and conference version at 400 kbps, no probing envelope. Three checks: the run is valid; the arm name in the startup log is correct; the asynchronous layer is enabled.
- **Script**: scripts/alphartc/deploy/lowbw_nl_vs_conf_v1.py; chain deploy/chain_lowbw_nl_v1.sh.

## Criteria (both claims same function, frozen before running)

- **Primary endpoint D**: utility difference with equal weight across the four capacity cells, i.e. no LLM minus LLM4Band, each cell averaged over three runs. Claim 1 compares the two arms without probing envelope, claim 2 compares the two arms with envelope v6.
  - Utility is the testbed's usual 100 × (0.4 R + 0.4 D + 0.2(1 − L)).
- **Interval**: within each cell, each arm resampled with replacement, 10000 times, seed 20261004, 90% interval.
- **Non-inferiority bound**: −5.27, i.e. the testbed noise threshold, taken from switch-closedloop-noise-v1, used by all our closed-loop batches.
- **Decision**:
  - holds: lower bound greater than −5.27, and safety line not triggered;
  - direction only: D greater than −5.27, but lower bound not greater than −5.27;
  - does not hold: D not greater than −5.27, or safety line triggered.
- **Safety line**: any cell where the no-LLM mean is more than 10 points below LLM4Band, or all three no-LLM runs in some cell are invalid.
- **Boundary**: when all three LLM4Band runs in a cell are invalid, that cell is dropped and noted; when fewer than 3 usable cells remain, judged inconclusive.
- **Report only**: per cell per arm utility, video payload rate, queuing delay, VMAF, SSIM, PSNR, frame skips, decision interval, inference time.

## Predictions unfavorable to us

1. **100 and 200 kbps cells.** The conference version has always been stable in this range; in earlier registered runs the 200 kbps condition was 64.52 vs 66.22. The no-LLM version is worse offline at low bandwidth, and without the probing envelope the difference in these two cells may be negative, so claim 1 may only reach direction only.
2. **Two risks: overestimation and locking low.**
   - The no-LLM offline overestimation rate is 0.84 to 0.90, at 100 kbps it may overestimate and hit packet loss.
   - Conversely, it may lock at a low bitrate like the one-token LLM variant.
3. **With envelope v6 added, the two arms are close.** The probing envelope rewrites most decisions, so claim 2 will most likely hold, but this only shows that the probing envelope works, not that the estimator itself does.

