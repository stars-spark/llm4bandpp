<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Repeated calls to the hosted designer (realtel-repeat-v1, 2026-10-08)

## Question
With the same frozen prompt (template hash d2467ef5dc35) and the same settings, called twice more on the 12 stacks with 3 field orders per stack, does the designer's advantage over the best non-LLM control still hold, and how much do the three calls differ?

## Procedure
- Script scripts/coldstart/realtel_repeat_v1.py, reusing realtel_scale_v1's sources (sources.json), prompt construction, parsing and scoring, without changing any item.
- The 1st and 2nd repeats each make 36 calls, 72 in total. Each call records the model identifier and timestamp returned by the API.
- Parse failures count as all missing (same as realtel-scale-v1).
- Run 0 is the original call of realtel-scale-v1, whose result was already seen; it enters only the report-only items.

## Criteria (fixed before running, confirmatory template identical to realtel-scale-v1)
- Primary endpoint: BA of the two new calls combined minus BA of the best non-LLM control (control mapping follows realtel-scale-v1, best is Cupid), block resampling by source 5000 times, seed 20261003, 90% interval.
- Holds: interval lower bound greater than 0 and Δ not less than 0.15; direction only: Δ greater than 0 but not reaching holds; does not hold: Δ not greater than 0 or safety line triggered.
- Safety line: mis-mapping rate (share of no-counterpart decisions given a mapping) exceeds 0.15.
- Report only: BA and range of each of the three calls, BA of the three combined; field-only BA; proportion of cells (source, order, feature) where the three mappings are exactly identical; number of sources fully correct in all three; model identifier and call date returned by the API; number of parse failures.

## Predictions unfavorable to us
In reasoning mode the outputs of repeated calls will vary: the BA of the two new calls may be below 0.90 and the cell-wise agreement rate below 90%; if a call fails to parse for an entire stack, BA may drop below 0.85.

