<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Interface fidelity under the deployed estimator (hd720-designer-tel-fid-v1, 2026-10-07 evening)

## Design
- Downstream: arm_ch_schema_tel (deployed C-H, 5 kbps floor, probing envelope v4, no shadow GCC), run script v27, same as hd720-designer-tel-v1 and v2.
- Schema and mapping: five schemas, four interfaces, frozen maps.json (sha256 8d01ebb9…), designer mapping identical to the true mapping.
- New data: conditions hd_t5, hd_t7, hd_t8 (cellular windows not used in any designer test) and hd_c3 (constant 3 Mbit/s); sequence Johnny (none of these four conditions combined with Johnny appeared in the designer tests). CLEAN 2 runs per condition, 88 runs total, on a single container pair.

## Criterion (fixed before running, taken unchanged from obsschema-closedloop-v2)
- Deviation = |U(method) − U(true mapping under the same condition)|, U is network utility, and for the true mapping the mean of the two CLEAN runs under the same condition is used; cells are schema × condition, 20 cells.
- Δ = the mean deviation of the best statistical method (the one with the smaller mean deviation among distribution matching and name matching) − the mean deviation of the LLM, with a 90% interval from 5000 block resamples by condition (seed 20261007).
- Holds: lower bound greater than 0 and Δ not less than 3; direction only: Δ greater than 0; does not hold: Δ not greater than 0 or the LLM has a cell more than 10 utility points below CLEAN under the same condition.
- Broken-call scoring (same as hd720-designer-tel-v2, fixed before running): if an interface arm is invalid because the call did not finish or VMAF cannot be computed, its utility is counted as 0; a run invalid for tool reasons is not scored and its cell is removed. CLEAN uses only valid runs.
- Report only: deviation per interface, broken calls, mean utility, quality deviation.

## Predictions unfavorable to us
- Under constant 3 Mbit/s and the wider 4G window, name matching may have no broken calls and small deviation, and Δ may be less than 3.
- Block resampling by condition has only 4 blocks, so the interval will be wide.

