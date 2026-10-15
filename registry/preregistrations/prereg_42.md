<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Stronger baseline for interface adaptation, unit-aware name matching (obsschema-strong-baseline-v1, 2026-10-02 around 18:50 Beijing time, written before running)

## Design
- Blind design: the matcher is designed without the field names of the test schemas. Because the field names of the test schemas had already been seen, the matcher is designed and frozen in an isolated directory without access to them, using only the interface specification, the two development schemas (dev_a, dev_b), and development-group evidence; during design it must not read files in the repository that contain test schemas; the source hash after freezing is written into the note and not changed afterward.
- Test group: the 32 groups of obsschema-llm-v1 (four held-out schemas) and the 40 groups of obsschema-openreason-newschema-v1 (five new schemas), 72 groups in total; evaluation is the same as the original experiment (on gpu-server-1, per-call mapping error divided by the error under the true mapping, median within a group not exceeding 1.2 counts as success).
- Comparison targets: open-source R1 distilled 32B (24 successes on the old 32 groups, 36 successes on the new 40 groups, using the already registered readings, not rerun). DeepSeek (32 on the old 32 groups) and 14B are reported but not judged.

## Criteria (confirmatory tier template, thresholds follow obsschema-openreason-newschema-v1)
Primary endpoint Δ = (number of successful groups for R1 distilled 32B − number of successful groups for unit-aware name matching) ÷ 72, with a 90% interval from 5000 block resamples by call set (8 old sets, 8 new sets, 16 sets in total). Holds: lower bound greater than 0 and Δ ≥ 0.25; direction only: Δ > 0; does not hold: Δ ≤ 0, or the safety line is crossed (the number of groups where the LLM ratio median exceeds 2 is greater than for the matcher). Report only: success counts by schema, per-item correct mapping counts, the comparison for DeepSeek and 14B, and readings on the development groups.

## Unfavorable prediction
Most held-out schemas have field names with explicit unit suffixes (Kbps, Us, seconds, pct, permille), and a matcher that parses by unit may match most of them, with a difference below 0.25; rt_getstats uses getStats naming conventions, and the synonym table may also cover it.
