<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Two-step LLM matching comparison (llm-twostep-match-v1, 2026-10-08)

Written before running. Script `scripts/coldstart/llm_twostep_match_v1.py`. Step-two prompt hash prefix 6763a70b466c, written to prompt_hash_frozen.txt on first call.

## Design

- **Step one**: the generic-matching results cached by llm-schema-match-baseline-v1 are reused unchanged, with no new calls.
  - Same hosted model deepseek-flash, temperature 0, three field orders.
- **Step two**: new calls.
  - One call per source per field order, 57 calls total, covering 12 stacks and 7 specifications.
  - Each (interface feature, source field) pair matched in step one is listed with its feature description, field name, containing object and original description.
  - Only the differencing and the scale are asked, with wording identical to item (a) of the designer prompt.
- **Missing rules**:
  - Features not matched in step one remain missing;
  - If step two fails to parse entirely, all features of that source and order count as missing, same rule as the generic matcher;
  - If a pair lacks an answer, that feature counts as missing.

## Criteria

- **Primary endpoint**: Δ = BA(designer) − BA(two-step) on 12 real client stacks.
  - Judged with realtel_adapter_v1.judge, 5000 whole-block resamples by source, 90% interval.
  - Sources and ground truth same as realtel-scale-v1.
- **Holds**: lower bound > 0 and Δ ≥ 0.15, threshold same as realtel-scale-v1 and llm-schema-match-baseline-v1.
- **Direction only**: Δ > 0.
- **Does not hold**: Δ ≤ 0.
- **Report only**:
  - Δ on 7 specifications;
  - Number of correct pairs on the end-to-end 42 cells, alongside designer 42 and generic matcher 38;
  - Number of step-two parse failures and missing answers.

## Unfavorable prediction

When units and differencing are asked explicitly, two-step may tie with the designer or even be slightly higher, because it selects fields more accurately (0.979 vs 0.940).

