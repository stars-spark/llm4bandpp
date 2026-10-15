<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: The designer in a deployment that can read only telemetry (fixed before the runs)

## Design

- **Identical to hd720-designer-ch-v1**: schemas, mappings, conditions, sequences, run counts, primary endpoint D_A, interval, verdict (holds if the lower bound is above 0 and D_A is at least 1.5 VMAF), safety line, schema check and smoke test.
- **The only change**: the downstream estimator is arm_ch_schema_tel.
  - Code in deploy/fixed_schema_ch_v2.py: C-H, collector v6, 5 kbps floor, probing envelope v4.
  - Both the envelope and the estimate read the adapted observation.
  - Run script v27.
- **Container check**: on an empty observation the designer's mapping gives a normal estimate; the distribution-matching mapping pushes the estimate to the 5 kbps floor, which envelope v4 cannot lift.

## Prediction unfavorable to us

- The delay and loss rules of envelope v4 may still hold back part of the loss from a wrong interface, so D_A may stay below 1.5.
- This is another deployment, not the version 6 deployed in the paper; even if it holds, the conclusion is limited to a deployment that reads only telemetry.

