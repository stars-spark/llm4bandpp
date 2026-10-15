<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Competing flow and 720p recheck for probing envelope v6 (drafted 2026-10-04 at 10:30 Beijing time)

Both are confirmatory tier; the registration reason is "method changed." The method under test changed, so the conditions, endpoints, and criteria are carried over unchanged from v1. The v1 conclusion is unchanged.

## 2. What v6 changes

The file is `scripts/alphartc/deploy/safety_envelope_v6.py`, a new file; v4 is untouched. Everything else is taken verbatim from v4; only two things are added:

- **A: the congestion decision gains one more condition: the shadow GCC reports overload.** The shadow GCC is the same code used by the baseline arm (gcc_pt125_c200_v1), receiving the same packet reports. So overload detection, that is the trend line plus adaptive threshold, is identical to the baseline arm and no longer depends on an absolute delay threshold tied to buffer size. The existing two conditions, loss rate above 0.10 and delay rise above 300 milliseconds, remain.
- **B: after congestion, follow GCC.** At each congestion onset, the total receiving rate Cc at that moment is recorded. Thereafter the output takes the shadow GCC rate, F is synchronized to it, and the model is not used during this period. Each step writes the actual output back to the shadow GCC, so the rate during congestion is GCC's own rise and fall.
  - Handback condition: if the output stays above Cc without congestion for 5 consecutive seconds, control is handed back to the model. The 5 seconds is taken from the v4 probing duration. After handback F starts from the GCC level.
  - Periods that never had congestion are step-by-step identical to v4.

No new numerical constants are introduced: the only addition is the shadow GCC, and all its constants come from the same code as the baseline arm.

**Design process (exploration tier, not used as paper evidence):**

- Unit test `test_safety_envelope_v6.py`, 8 of 8 pass, including counterexamples that must be caught. Key points:
  - With no congestion it is step-by-step identical to v4;
  - While the cap is in place the output does not exceed the shadow GCC;
  - Real GCC reports overload 0.4 seconds after sending 20% above the bottleneck;
  - Two threads receiving packets concurrently have no errors.
- Mechanism simulation `sim_compete_env6_v1.py`: fluid bottleneck, 2 Mbit/s, 250 milliseconds buffer, the competitor is the actual Python GCC.
  - Share: v4 is 0.97 to 0.99, v6 is 0.54 to 0.58, GCC against GCC gives the first-arriving call 0.559.
  - Exclusive utilization: v6 is 0.92 to 0.94, v4 is 0.96 to 0.98, GCC is 0.92.
  - In a rough TCP simulation v6's share also stays close to GCC's (2 Mbit/s is 0.40 to 0.45 versus 0.51, 3 Mbit/s is 0.67 to 0.71 versus 0.75).
- Item B was changed twice, both on development data and before any confirmation run. The first time (simulation): the first draft tied the cap to the v4 hold period:
  - Problem: in a step simulation alternating between capacities 0.6 and 2.4 Mbit/s, high-level utilization was only 0.50, the same as GCC's 0.48.
  - Fix: a separate release condition, and high-level utilization rose to 0.74 (v4 is 0.93).
  - Competing share unchanged.
  - This was changed after seeing the simulation, and the change happened before any testbed confirmation run.
- The second time (development smoke round one env6-dev-smoke-v1): at that time item B was "output does not exceed the shadow GCC."
  - Conditions: development profile hd_dev15, constant 1.5 Mbit/s, sequence KristenAndSara, not part of the two experiments below.
  - All wiring checks passed: version 6, shadow GCC has readings every step, 0 errors.
  - Against one GCC call the share is 0.579, GCC reference 0.686.
  - Against TCP only 0.139, GCC reference 0.468. The reason is that under a standing queue the model estimates about 200 kbit/s, F is pushed down by overload-triggered backoff and only recovers in the clear state, and the shadow GCC is synchronized to this low value every step.
  - Based on this it was changed to "output equals the shadow GCC," and the unit test counterexample was replaced with the old approach.
- Development smoke round two env6-dev-smoke-v2 (final rules, same development profile, 7 runs):
  - Against TCP: 0.492, 0.281, GCC reference 0.468, 0.473. The 0.281 run hit 42% loss when TCP entered, the rate collapsed, and afterward it recovered along with GCC.
  - Against one GCC call: 0.581, 0.684, GCC reference 0.686, 0.538.
  - Exclusive 1.5 Mbit/s: video 1184 kbit/s, VMAF 79.7.
  - Freezes: 10 to 15 per minute under competition, GCC 5 to 6 (report only).
  - The rules have been frozen since then and are no longer tuned on development data.
**Data seen before the design:** The v6 design drew on the per-step traces of the three conditions of compete-flow-v1. All confirmation runs below are newly run, with conditions unchanged.

## 3. compete-flow-v2 (criteria identical to compete-flow-v1 claim 2)

- Conditions: T2 (2 Mbit/s, one TCP CUBIC, seconds 30 to 90), T3 (3 Mbit/s, same as above), G2 (2 Mbit/s, one GCC 720p call every 200 ms, starting at second 30 for 60 seconds). Main call Johnny 720p 30 fps, competition window seconds 40 to 90.
- Arms:
  - GCC every 200 ms;
  - one-token LLM variant plus v6 (arm_llm4bandpp_x, collector v6, BWE_ENVELOPE=6), run on container pair p1;
  - echo plus v6, report only.
- 3 runs per cell, 27 total, run script v15.
- Share: video payload rate within competition window ÷ (video payload rate + competitor effective throughput).
- Primary endpoint S: mean of three runs per condition, share of the one-token LLM variant plus v6 minus share of GCC, equal-weight average over three conditions. Interval: within-condition resampling with replacement for each arm, 10000 iterations, seed 20261003, 90% interval.
- Decision:
  - holds: lower bound greater than −0.10, and safety line not triggered;
  - direction only: S greater than −0.10, but lower bound not greater than −0.10;
  - does not hold: S not greater than −0.10, or safety line triggered.
- Safety line: in any condition, the mean share of the one-token LLM variant exceeds GCC's by more than 0.15, or in some condition all three of its runs are invalid.
- Validity: same gates as v1, plus one probing envelope v6 check. The check: in the observation traces all probing envelope versions are 6, the shadow GCC error count is 0, and more than ninety percent of steps have shadow GCC readings after 10 seconds of shaping; otherwise the run is judged invalid and recorded, not deleted.
- The competing-traffic tools follow the calibration of compete-flow-v1 (all calibration checks passed); relative to v13, run script v15 adds only the estimator file.
- Report only:
  - competitor throughput, Jain index, competition-window queueing and loss, VMAF and freezes, recovery time;
  - v6 cap and overload proportion;
  - echo arm;
  - comparison with the share under v4 in v1.
- Decision script: `scripts/alphartc/deploy/compete_flow_env6_eval_v1.py`, judge and selftest same as v1.

## 4. hd720-closedloop-env6-v1 (criteria identical to hd720-closedloop-v1 claim 1)

- Units: 6 conditions (hd_c1, hd_c2, hd_c3, hd_c8, hd_r1, hd_r2) times 2 sequences (Johnny, FourPeople), 12 cells total. Sequences and caps follow hd720-closedloop-v1.
- Arms: GCC every 200 ms, the one-token LLM variant plus v6, echo plus v6 (report only). 3 runs per cell, 108 total.
- Primary endpoint D: per cell, mean VMAF of three runs of the one-token LLM variant plus v6 minus that of three GCC runs, equal-weight average over 12 cells. Interval by unit-stratified resampling, 10000 iterations, seed 20261003, 90% interval.
- Decision (non-inferiority, margin 6 VMAF):
  - holds: lower bound greater than −6, and safety line not triggered;
  - direction only: D greater than −6, but lower bound not greater than −6;
  - does not hold: D not greater than −6, or safety line triggered.
- Safety line: any cell lower by more than 10 points, or in some cell all three of our runs are invalid.
- Validity: same as v1, plus v6 check.
- Report only:
  - superiority;
  - freezes (in v1, the one-token LLM variant plus v4 had 8.7 per minute, GCC 3.03);
  - cap proportion;
  - echo arm;
  - per-cell difference from v4 in v1.
- Decision script: `scripts/alphartc/deploy/hd720_env6_eval_v1.py`.

## 5. Predictions unfavorable to us (written before running)

1. At 720p, D with v6 is below v4's +7.87 and most likely no longer superior. The difference on constant-link cells is near 0, and the gain mainly remains on the two real traces.
2. Against TCP, the share with v6 may be slightly below GCC's: the two-run development mean is 0.387 versus 0.47, and single runs can vary by 0.2. The S point estimate is most likely slightly negative near 0, the 90% interval lower bound may sit right at −0.10, and there is a substantial chance it is judged direction only.
3. In G2 the first-mover advantage still holds: share may be above GCC first-mover 0.587, but will not reach 0.737.
4. Freezes exceed GCC's: in the development smoke test they were about twice GCC's during competition. In the 720p batch, freezes may still be above GCC's 3.03 per minute.
5. The VMAF difference between echo plus v6 and the one-token LLM variant plus v6 is within 3 points. The LLM executed at every step has no visible contribution in this batch, as in v1.

## 8. Frozen code (before 2026-10-04 pre-registration, sha256)

```
25cad022e3b32b4564763eeac8067ecc0cfde5eb1136eb377f25730b4b6699d2  scripts/alphartc/deploy/safety_envelope_v6.py
aa9e1c5e49dfc36fe680036c94e2c59826ce8080d78bbaa9fd193411b263333e  scripts/alphartc/deploy/online_llm_arms_v4.py
21819b4b4b570687612ed8184093395db83f281d826f604624701d67066e7661  scripts/alphartc/deploy/echo_x_v2.py
da2416fe03e78db21abd43254934a8ec0f1e488aee5b77fe10a7ce3d4191dc74  scripts/alphartc/BandwidthEstimator_staleness_v10.py
045e0475e32972ef40297ec098c6a8ae4fdb022c76c4dd28049d2cddbb9bee53  scripts/alphartc/run_staleness_once_twocontainer_midsnap_v15.sh
5f87f048b1f8fb0c95458e9165d136f5ca79d8e6b0f1c36e71c5616481820720  scripts/alphartc/deploy/hd720_env6_eval_v1.py
6dbbf5702b16fdc3f623cb297ac1526ae101802d2025236174ea8bff564e5546  scripts/alphartc/deploy/compete_flow_env6_eval_v1.py
```
