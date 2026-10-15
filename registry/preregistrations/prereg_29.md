<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Designer in the telemetry-only deployment, confirmation on new data (hd720-designer-tel-v2, 2026-10-07)

## Design
- Downstream, run script, schema and mapping same as v1: arm_ch_schema_tel (deployed C-H, 5 kbps floor, probing envelope v4, no shadow GCC, both estimation and probing envelope read the adapted observations); run script v27; five schemas test_g, test_h, test_i, test_j, rt_getstats, four interfaces LLM, DIST, NAME, NONE, mappings taken unchanged from the frozen maps.json (sha256 8d01ebb9…); CLEAN 2 runs per condition.
- New data: conditions are hd_t1 through hd_t4 from profiles/hd720_real8 (cellular trace windows not used in any designer test, first four by index; hd_t6 has a 45-second outage at the start and is not among them); sequence FourPeople (v1 was Johnny).
- Total 4 conditions × (20 interface runs + 2 CLEAN) = 88 runs, on a single container pair, interleaved in rotation.
- Smoke test: 1 CLEAN and 1 test_g-LLM on hd_t1; the full run starts only if both are valid and pass the schema check.

## Criteria (frozen before running)
- Primary endpoint D_A: per cell (schema × condition, 20 cells) the VMAF difference of LLM minus the best non-LLM interface (the one with the highest mean VMAF across all cells among NONE, DIST, NAME, selected post hoc, applied uniformly to all cells), equally weighted average; 10000 cell resamples (seed 20261007) for the 90% interval.
- Broken-call scoring: when an interface arm run is invalid because the run script validity check fails (call not completed) or the decoded video is insufficient to compute VMAF, it counts as VMAF 0; runs invalid for tool reasons (missing run directory, code hash mismatch, probing envelope version not 4, schema check mismatch) are not scored and the cell is dropped. CLEAN uses only valid runs.
- Holds: interval lower bound greater than 0 and D_A not less than 1.5 VMAF, and safety line not triggered; direction only: D_A greater than 0 but the holds condition is not met; does not hold: D_A not greater than 0 or safety line triggered; fewer than 10 usable cells judged inconclusive.
- Safety line: any cell where LLM is more than 10 VMAF below the same-condition CLEAN mean.
- Report only: broken-call count per interface, mean VMAF (broken calls counted as 0), VMAF counting only completed calls, freezes, packet loss, latency score, probing envelope rewrite share.

## Predictions unfavorable to us
- The cellular trace windows have means of 1.5 to 2.3 Mbit/s; name matching broke 5 calls in v1, but in the new windows it may break none, and D_A will shrink substantially or even fall below 1.5.
- FourPeople's bitrate demand differs from Johnny's, and interfaces other than NONE may all complete calls.

