<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Value-rule baselines on the real-software end-to-end test (realtel-e2e-valuerule-v1)

## Design (runs reused, method outputs new)
- The 24 real-software runs of realtel-e2e-v1 (headless Chrome WebRTC, iperf3, tcp_info, GStreamer RTP; 0, 2 and 5% loss, two runs each) and their scoring function are reused; cells follow the third version of the ground truth, which drops the tcp_info byte count, 42 cells in total.
- Designer: DeepSeek's adapter for field order 0, unchanged.
- Value-rule baselines: the seven non-LLM methods and the same hosted model used as a generic schema matcher (spec7 of llm_schema_match_v1, field order 0) keep the fields they chose;
  differencing is decided by the values: in the snapshots of the same run, a field whose value sequence never decreases and grows at least once is differenced, otherwise not; coefficients follow the original rules. Judging from the values of the same run favors the baselines.

## Criteria (fixed before the runs)
- Primary endpoint Δ = the designer's share of correct cells minus that of the best of the eight value-rule baselines (chosen afterwards), with a 90% interval from 5000 resamples of whole runs (seed 20261007).
- Holds: lower bound above 0 and Δ at least 0.15 (the threshold fixed before the runs of realtel-e2e-v1); direction only: Δ above 0; does not hold: Δ at most 0.
- Report only: each method's share of correct cells under the original and the value rules, and per-source results.

## Prediction unfavorable to us
- The generic matcher chooses fields even more accurately than the designer (fields only, 0.979 against 0.940); with value differencing it may miss only the 1/256 coefficient of the RFC 3550 loss fraction (6 cells), so Δ may be about 0.14, below 0.15.

