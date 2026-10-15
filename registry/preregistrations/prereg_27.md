<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Counterfactual document contrast (realtel-cfdoc-v1, 2026-10-08)

Written before the run. Script `scripts/coldstart/realtel_cfdoc_v1.py`. The rewrite table is in the script's CF dictionary, frozen before the run.

## Design
- **Source**: 7 real specifications from realtel-adapter-v1. Scored are the 11 mapping fields in the third version of the ground truth, distributed across 6 specifications; qlog has no mapping fields and is kept as is.
- **Rewrite**: for each mapping field only one statement in the description is changed, and the ground truth changes accordingly; all other fields and source descriptions are unchanged. Rewrites fall into three categories:
  - Counting rule: cumulative total changed to interval count cleared after each read, or the reverse;
  - Unit: bytes changed to kilobytes or bits, bits per second changed to kilobits per second;
  - Ratio notation: percentage changed to ratio, 8-bit fixed point changed to basis points.
- **Name hiding**: field names are hidden as field_NN according to realtel_namehide_v1.hide, and occurrences of that field name in the description are replaced as well.
- **Prompt**: the frozen template of realtel-adapter-v1 (hash verified), DeepSeek settings unchanged. Three field orders per source, shuffled the same way as in the name-hiding experiment, 21 calls in total.

## Criteria
- **Primary endpoint**: Δ = S − Mm, block resampling by source 5000 times, seed 20261008, 90% interval.
  - The computation scope is 11 rewritten fields times 3 orders.
  - S is the proportion following the rewritten document: the answer's field, difference, and coefficient (within 2%) all match the rewritten ground truth.
  - Mm is the proportion following the public specification: the answer matches the original ground truth.
- **Holds**: lower bound greater than 0, and S not below 0.80.
- **Direction only**: Δ greater than 0.
- **Does not hold**: Δ not greater than 0.
- **Report only**: whole-table BA under the rewritten ground truth (1.000 for the name-hidden original), number of parse failures, per-field answers.

## Unfavorable prediction
For widely known specifications such as W3C and RFC 3550, the model may answer from memory, making Mm high.

