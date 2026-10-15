<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Repair of telemetry units and offsets, version 2: offline re-verification and closed-loop validation (obsrepair-llm-v2, obsrepair-closedloop-v2, 2026-10-02 at 10:10 Beijing time, written before running)

## Method improvements (scripts/coldstart/obsrepair_llm_v2.py)

1. The interface description is replaced verbatim with the challenge's official text (the 15 items in data/audit_bench_v1/official_feature_spec.txt, numbering changed to start from 0, body text unchanged).
2. The prompt states that different collectors inherently differ in small implementation details (counting a few extra packets that the reference does not count, different rounding), and that small differences are not errors; the model should report an error only when a relation required by the specification is broken by a large factor or a large constant. Specific factors are not listed, to avoid leaking the test errors.
3. When the token limit is reached without an answer, the model is asked once more (at most two calls) and the first parseable answer is taken; if neither call yields one, no repair is made.

## Development (run before the test, used only to fix the prompt)

- Testbed development set of 10: observations of ev_1 to ev_3 of obsrepair-cl-fault-screen-v1 under no error and the seven error classes, plus the origin offset and swap classes from the obsrepair-closedloop-v1 evidence; checked against the truth-repaired structure (after repair each feature's median difference from the truth-repaired one does not exceed 5%).
- Offline development set of 12: the development set of obsrepair-llm-v1 (rate in kbit/s, delay in seconds, no error).
- At most three rounds of prompt modification, all recorded per round; then frozen and the template hash recorded. These development data are not used as evidence thereafter.

## 1. Offline re-verification, obsrepair-llm-v2

- New test set of 70 groups (built by scripts/arb/obsrepair_v2.py): all 446 calls used by v1 are excluded; two groups of 13 calls for each of the four original scenarios under each of the seven test error classes and no error (56 error groups, 8 no-error groups); one group for each of five distinct real networks (two for medium bandwidth), 6 collateral-damage control groups in total, each with 4 to 10 evaluation calls. Reference, control method and evaluation are the same as v1.
- The criterion is identical to obsrepair-llm-v1: an error group with median not exceeding 1.2 counts as repaired, a control group exceeding 1.05 counts as collateral damage, net score = repaired − collateral damage. **Holds**: the LLM's net score is at least 4 higher than the best non-LLM one, collateral damage does not exceed 1, and at least half the error groups are repaired; **does not hold**: the LLM's net score is not higher than the best non-LLM one; otherwise **inconclusive**.
- Unfavorable prediction: with repair required only for large factors, small constants such as the 100 ms delay origin offset (v1 repaired 0 groups) still cannot be repaired; there are fewer collateral-damage control groups, so the collateral-damage criterion is easier to satisfy but statistical power is weaker.

## 2. Closed-loop validation, obsrepair-closedloop-v2

- Errors: only the three classes effective in the closed loop in obsrepair-cl-fault-screen-v1: rate in kbit/s (F_kbps_real), rate in Mbit/s (F_mbps), delay in microseconds (F_us). In the offline test, thousand-fold snapping repaired 0 groups of delay in microseconds.
- Windows: Norwegian 3G ferry traces not used by any existing profile (rule obsrepair_cl2_v1, seed 20261004), 3 evidence windows, 8 evaluation windows.
- Evidence: each of the three evidence windows is run once under no error and each of the three error classes (without repair), and for each class the mis-written observations of the first 500 steps of three calls are used to compute quantiles. Repair specifications: LLM (version-2 frozen prompt, at most two calls), thousand-fold snapping SNAP1000, all-factor snapping SNAPALL (obsrepair_v1.snap), and one of each is also given for the no-error evidence.
- Evaluation: 16 conditions per window: no error as-is; under no error the specifications given by each of the three methods (test collateral damage); each of the three error classes under four treatments: no repair, thousand-fold snapping, all-factor snapping, LLM. 8 windows give 128 runs in total, plus 12 evidence runs. arm_default_repair, run script v10, media collection on. The run mode is determined by testbed-parallel-equiv-v1 (if it holds, four container pairs in parallel, otherwise the original pair in serial).
- The primary endpoint is network utility U, paired by window; quality is reported but not judged. The better snapping is the one of the two snappings with the higher mean U (chosen post hoc, biased toward the control).
- An error class is effective if the mean U without repair is at least 3 points lower than with no error.
- **Holds**: at least two error classes are effective; on each effective error class the LLM is at least 3 points higher than no repair, positive in at least 7 of 8 windows, and no more than 2 points below no error; on each error class the LLM is not more than 1 point lower than the better snapping; on at least one effective error class the LLM is at least 3 points higher than the better snapping; under no error the U with the LLM's specification is not more than 2 points lower than no error as-is.
- **Does not hold**: on any effective error class the LLM is not higher than no repair; or on any error class the LLM is more than 3 points lower than the better snapping; or under no error the LLM's specification lowers U by more than 3 points; or on no effective error class is the LLM at least 3 points higher than the better snapping.
- **Inconclusive**: otherwise.
- Unfavorable prediction: all-factor snapping may also repair delay in microseconds well (if the testbed's median queuing delay is not zero); the LLM may still reach the token limit, and if neither call answers, no repair is made.

## Revision (2026-10-02 at 10:43 Beijing time, before any main evaluation run; run mode only)

The run mode is now determined by testbed-parallel-equiv-v2 (if it holds, four container pairs in parallel, otherwise the original pair in serial). testbed-parallel-equiv-v1 remains recorded as does not hold, but its tolerance came from an inapplicable noise estimate and cannot tell whether parallelism has an effect. The criterion and design are unchanged.

## Revision (2026-10-02 at 12:00 Beijing time, before any main run)
The run mode is fixed at four container pairs in parallel and is no longer determined by the second version of the equivalence test. This revision was made after seeing an interim preview of that test (preview: parallel minus serial +1.49, 90% interval [−0.59, +3.58], judged inconclusive; no difference in timing or invalid count). Reason: the criteria are all within-experiment differences, all conditions use the same run mode and are interleaved across the four pairs, and the overall shift cancels out in the differences. The conclusion of the equivalence test only determines whether absolute readings can be compared with those of the serial period. The utility of the no-error condition on each container pair is also reported.

## Condition audit and run environment (2026-10-02 at 12:05 Beijing time, before any main run)

Before judging, the condition audit (scripts/alphartc/deploy/cl_condition_audit_v1.py) is run. Hard checks: the conditions actually used match the job; code and binary hashes are identical across all runs, and profile hashes match the job; run script validity. Any run that fails a hard check is treated as a tool failure, the judging script does not produce a conclusion, and the run is repeated after the cause is identified. Soft checks only report: timing outliers, insufficient control points, whether temperature and power mode are consistent during the run, the assignment of each method across the four container pairs, and the no-error utility of each pair. The power mode was switched to performance when the job list was generated, and the actual mode is recorded for each run.
