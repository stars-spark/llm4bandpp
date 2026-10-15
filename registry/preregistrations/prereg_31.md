<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Interface adaptation closed loop, downstream replaced with the no-LLM deployed estimator (obsschema-closedloop-nl-v1, written on the evening of 2026-10-04, Beijing time, fixed before running)

## Design (as in obsschema-closedloop-llm4bandpp-v2 except for the downstream estimator)

1. **Downstream.** arm_nl_schema (deploy/fixed_schema_nl_v1.py), i.e. the no-LLM estimator, weights nl_s1.pt.
   - With collector v6 and probing envelope v6, i.e. the deployed system; the original batch used probing envelope v4.
   - Interface layer, adapter layer, foreign schema table (test_g to test_j plus rt_getstats), to_foreign and adapt are unchanged.
2. **Mapping.** v2's maps.json is reused unchanged (sha256 8d01ebb9…3133; v2 took it from v1), with no LLM calls.
3. **Windows and conditions.** Windows rt_1 to rt_8, 21 conditions per window (one error-free; each of the five schemas once with each of no adaptation, LLM, distribution matching and name matching), condition shuffle seed same as v2, 168 runs total.
   - The windows are the same as in v2. The downstream estimator changed, so the question differs; these windows were used only for evaluation in v1 and v2, never for designing a method.
4. **Testbed.** Two container pairs in parallel, one quality-scoring worker, balanced power mode, run script v17 (v16 plus one arm_nl_schema arm).
5. **Smoke (not counted).** The error-free condition and rt_getstats without adaptation run once each on es_1 and must satisfy three conditions: valid; estimator name and condition correct in startup log; in the error-free run, after the first 10 seconds, the fraction of inference steps with no packet in the long window is below 0.01.
6. **Directory and scripts.** Results directory /path/to/testbed/results/obsschema-closedloop-nl-v1; judge script scripts/alphartc/deploy/obsschema_rt_nl_v1.py, judge function still obsschema_cl2_v1.judge.

## Criteria (unchanged from the v1 pre-registration, same as v2)

- **Primary endpoint.** Deviation from the true mapping |U(method) − U(same-window error-free)|, cells are schema × window, 40 in total.
- **Δ and interval.** Δ = mean deviation of the best statistical method (the one of distribution matching and name matching with the smaller mean deviation) − mean deviation of the LLM, 90% interval from 5000 whole-window block resamples.
- **Holds.** Interval lower bound greater than 0, and Δ ≥ 3.
- **Direction only.** Δ > 0, but does not reach holds.
- **Does not hold.** Δ ≤ 0, or safety line triggered. Safety line: LLM has a cell more than 10 points below same-window error-free.
- **Invalid run.** Removed per run script rules.
- **Report only.**
  - Per-schema deviation, rt_getstats listed separately;
  - Number of severe-loss cells per method;
  - Mean utility, mean quality;
  - Whether each mapping item is correct;
  - Error-free utility per container pair;
  - 95th percentile of per-step computation time.

## Predictions unfavorable to us

1. **Δ may be smaller.** Probing envelope v6 outputs the shadow GCC after congestion, and shadow GCC receives native packet reports, bypassing the adapter layer. So once a wrong mapping causes congestion, it is taken over by GCC, and utility differences between mapping conditions are compressed. Δ may be below v2's +2.11, or even below 3, so the result may be only direction only.
2. **The loss without adaptation may be smaller.** The no-LLM estimator overestimates more heavily (offline overestimation rate 0.84 to 0.90), and the misaligned input without adaptation may also make it more aggressive, which the envelope then clips.
3. **Distribution matching may tie with the LLM.** On schemas like test_h where only order differs, the two may tie, as in v2.

