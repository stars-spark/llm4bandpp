<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: LLM schema matching baseline (llm-schema-match-baseline-v1, written on the evening of 2026-10-04, Beijing time, fixed before running)

## Design

- **Parts shared between the baseline and the designer:**
  - Same hosted model deepseek-flash, same call parameters (coldstart_rule_v1.ask, temperature 0, limit 48000 tokens);
  - The target attributes are word for word the interface description the designer sees, i.e., SHORT as the name and FEAT as the description;
  - Source presentation and the three field orders are identical.
- **Parts where the baseline differs:** It uses a generic schema-matching prompt that asks only for the matching source attribute name (or null) for each target attribute; it does not mention units, the differencing of cumulative counters or windows, and it does not write an adapter. The prompt is frozen before any call, sha256 4fb768f3b6b1…, see scripts/coldstart/llm_schema_match_v1.py.
- **Scoring:** Identical to the seven non-LLM controls. Matched fields are supplemented with differencing and coefficients by the same set of rules we wrote (is_cum, unit_scale), then scored with the same scoring function.
  - Parse failures count as all missing;
  - Items whose names match no field count as missing and are counted and reported.
- **Designer side:** Reuses the raw outputs already registered in realtel-scale-v1 and realtel-adapter-v1, with no new calls.
- **Sources:**
  - Claims: the 12 sources of realtel-scale-v1, using the finalized ground truth;
  - Report only: the 7 specifications of realtel-adapter-v1, using the module's current ground truth.
- **Call volume:** 57 calls.

## Criteria (same template as realtel-scale-v1)

- **Primary endpoint:** Δ = BA (designer) − BA (LLM schema matching), full scoring (fields, differences, coefficients all correct).
- **Interval:** Block resampling by source 5000 times, seed 20261003, 90% interval.
- **Decision:**
  - Holds: lower bound greater than 0, and Δ ≥ 0.15;
  - Direction only: Δ > 0, but does not reach holds;
  - Does not hold: Δ ≤ 0.
- **Report only:**
  - Field-only scoring;
  - Schema matching's mis-mapping rate, parse failure count, count of items whose names match nothing;
  - The same set of readings on the 7 specifications;
  - Schema matching's readings relative to the best of the seven non-LLM controls (Cupid 0.560).

## Predictions unfavorable to us

1. **Field-only gap is small.** Generic schema matching may approach the designer on field-only, within 0.05: picking the right field reflects the LLM's ability to read documents and is unrelated to the designer's specific formulation.
2. **On full scoring the result may be only direction only.** The unit and differencing rules we wrote will recover part of the gap for the baseline, so Δ may not reach 0.15.
3. **The baseline will likely far outperform the seven non-LLM controls.** This means a large part of the paper's headline gap comes from "using an LLM" itself, not from the designer's formulation.

