<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Closed-loop value of the designer in the deployed system (2026-10-06 evening, written before running)

## Design

- **Downstream**: deployed system arm_ch_schema, see deploy/fixed_schema_ch_v1.py.
  - i.e. C-H (ch.pt), collector v6, 5 kbps floor, probing envelope v6.
  - Interface layer and adapter layer imported from fixed_schema_nl_v1 and fixed_schema_x_v1.
  - Run script v25.
- **Schemas and mappings**: from frozen maps.json, sha256 8d01ebb9….
  - Five schemas: test_g, test_h, test_i, test_j, rt_getstats.
  - Four interfaces: LLM (designer), DIST, NAME, NONE.
  - Plus CLEAN, i.e. the true mapping.
- **Conditions**: 720p hd_c1, hd_c2, hd_r1, hd_r2, sequence Johnny.
  - Each (schema, condition) cell gets 1 run with each of the four interfaces, and CLEAN gets 2 runs per condition, 88 runs total.
  - Runs on a single container pair, appended after hd720-learned-baselines-v1.
- **Primary endpoint D_A**: per cell, VMAF difference of LLM minus the best non-LLM interface, 20 cells equally weighted.
  - Best non-LLM interface means the one among NONE, DIST, NAME with the highest mean VMAF across all cells, chosen post hoc, applied uniformly to all cells.
- **Interval**: 10000 cell resamples, seed 20261006, 90%.
- **Decision**:
  - holds: lower bound greater than 0, and D_A not less than 1.5 VMAF, and safety line not triggered.
  - direction only: D_A greater than 0, but not reaching holds.
  - does not hold: D_A not greater than 0, or safety line triggered.
  - Fewer than 10 usable cells judged inconclusive.
  - Basis for 1.5: hd720-echo-attr-ch-v1 measured the estimator's contribution beyond the envelope at 3.0 VMAF; a wrong interface can lose at most about this much, and half of it is taken as the minimum meaningful effect.
- **Safety line**: any cell where LLM is more than 10 VMAF below the same-condition CLEAN mean.
- **Validity**:
  - Same as the 720p batches.
  - Plus a schema check: the schema and map in the first record of each run's observation trace must match the job; otherwise no decision is made.
  - A 2-run smoke test comes first (NONE and LLM on test_g, hd_c2); both smoke runs must be valid and pass the schema check.
- **Report only**:
  - Mean VMAF per interface and mean deviation from CLEAN.
  - Freezes, packet loss rate, latency score, probing envelope rewrite share.
  - LLM minus CLEAN.

## Predictions unfavorable to us

- Probing envelope v6 also has latency rules; high estimates that cause queuing may be pushed back down. If the loss from a wrong interface shrinks below 1.5 VMAF, the verdict is direction only or does not hold.
- No adaptation (NONE) deviates little on some schemas (e.g. at most 2.9 on rt_getstats); the differences in these cells may be near 0, which pulls D_A down.

