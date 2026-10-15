<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Closed-loop validation of new client interface adaptation (obsschema-closedloop-v1, 2026-10-02 at 08:52 Beijing time, fixed before running)

## System

Corrected collector v6 → new client interface layer (rewrites 15 interface features into foreign schema fields, order and units per scripts/arb/obsschema_v1.py) → adapter layer (mapping: which source field each interface feature takes and by what coefficient it is multiplied) → challenge baseline → probing envelope v4.
The interface layer and adapter layer act simultaneously on the inputs of the estimator and the envelope, because after new client integration both read the output of the adapter layer. Implementation deploy/fixed_schema_x_v1.py (arm arm_default_schema), entry point v7, run script v10; element-wise identical to offline to_foreign, from_mapping (deploy/test_fixed_schema_x_v1.py, including cases that should fail).

## Procedure

1. Evidence: telemetry from the first 30 seconds of the first 3 calls of the new client. The estimator input observations of three error-free runs ev_1, ev_2, ev_3 from obsrepair-cl-fault-screen-v1 (driven by the reference collector plus the challenge baseline) are rewritten into the new client's fields for each test schema, and quantiles are computed (obsschema_v1.fstats, same method as offline). These three calls are used only as evidence, not as evaluation windows.
2. Mapping: one per test schema (test_c, test_d, test_e, test_f).
   - LLM: obsschema-llm-v1 frozen prompt (template hash 4abe82ad; the interface description is the frozen version, in which the descriptions of features 4 and 5 do not match the official challenge text, as noted in the registry; the offline test holds under this version of the description, and this experiment tests exactly this frozen method), real field names, DeepSeek flash reasoning mode, one call per schema, at most 48000 tokens; unparseable means no adaptation.
   - Distribution matching DIST, name matching NAME: same evidence, same reference, obsschema_v1.dist_match and name_match.
   - Once written to K/maps.json, the mappings are not changed; also record whether each mapping is element-wise identical to the correct mapping (report only).
3. Evaluation: eight evaluation windows sc_1 to sc_8 (rule obsschema_cl_v1, seed 20261003; four Norwegian 3G ferry windows and four bus windows, from traces not used by any existing profile in this repository). Each window has 17 conditions: error-free as-is CLEAN; four schemas each with four treatments: no adaptation NONE (fed directly in field order), the LLM (label LLM), distribution matching DIST, name matching NAME. 136 runs in total, ordered by window, with conditions shuffled within each window by the window seed. Media collection on, quality step 4.
4. The run mode is determined by testbed-parallel-equiv-v1: four container pairs in parallel if it holds, otherwise serial runs on the original pair (v10). All conditions within the same experiment use the same mode.

## Endpoints and criteria

Primary endpoint: network utility U (run result network.utility). Quality VMAF is reported but not judged. Paired by window; if a condition in a window is invalid, that window is excluded from comparisons involving that condition.
For each schema: the "better control" is the one with higher mean U among DIST, NAME (chosen post hoc, biased toward the control).
- Schema valid: mean U of no adaptation is at least 3 points lower than error-free as-is. Invalid schemas are reported and excluded from criteria.
- **Holds**: at least two schemas valid; on each valid schema, LLM has mean U at least 3 points higher than no adaptation, at least seven of eight windows positive, and the difference from error-free as-is mean U does not exceed 2 points; on each schema LLM is not more than 1 point lower than the better control; on at least half of valid schemas (rounded up) LLM is at least 3 points higher than the better control.
- **Does not hold**: on any valid schema LLM is not higher than no adaptation (difference not greater than 0); or on any schema LLM is more than 3 points lower than the better control; or on no valid schema is LLM at least 3 points higher than the better control (i.e., the statistical method is already sufficient in the closed loop).
- **Inconclusive**: the rest, including fewer than two valid schemas.

## Predictions unfavorable to us

- Testbed observations differ from the offline reference in normal ways (latency, packet interval, audio fraction), and the LLM may get caught up in these differences while reasoning and hit the token limit without giving an answer (already occurred twice in obsrepair-closedloop-v1), in which case that schema is treated as no adaptation.
- Although the statistical method's mapping is not element-wise fully correct offline, if the misalignment falls on features to which the estimator and envelope are insensitive (e.g., several fraction-type fields), closed-loop utility may tie with the LLM, and the experiment is judged does not hold.
- Under no adaptation the envelope may compress the estimate near the safety floor, and the loss from no adaptation may be less than 3 points, making the schema invalid.

## Revision (2026-10-02 at 10:43 Beijing time, before any main evaluation run; only the run mode changed)

The run mode is now determined by testbed-parallel-equiv-v2 (four container pairs in parallel if it holds, otherwise serial runs on the original pair). testbed-parallel-equiv-v1 remains recorded as does not hold, but its tolerance came from an inapplicable noise estimate and cannot tell whether parallelism has an effect. Criteria and design unchanged.

## Revision (2026-10-02 at 12:00 Beijing time, before any main run)

The run mode is fixed to four container pairs in parallel, no longer determined by equivalence test version 2. This revision was made after seeing an interim preview of that test (preview: parallel minus serial +1.49, 90% interval [−0.59, +3.58], judged inconclusive; no difference in timing or invalid count). Reason: the criteria are all within-experiment differences, all conditions use the same run mode and are interleaved across the four pairs, and the overall offset cancels in the differences. The conclusion of the equivalence test only determines whether absolute readings can be compared with those of the serial period. The utility of the error-free condition on each container pair is also reported.

## Condition audit and run environment (2026-10-02 at 12:05 Beijing time, before any main run)
Before the verdict, the condition audit (scripts/alphartc/deploy/cl_condition_audit_v1.py) is run first. Hard checks: the conditions actually used match the job; code and binary hashes are identical across all runs, and the profile hash matches the job; run script validity. Any run that fails a hard check is treated as a tool failure, the adjudication script does not produce a conclusion, and the run is rerun after the cause is identified. Soft checks are report-only: timing outliers, insufficient control points, whether temperature and power mode are consistent during runs, the allocation of each method across the four container pairs, and the error-free utility of each pair. Power mode is switched to performance when the job manifest is generated, and the actual mode is recorded per run.
