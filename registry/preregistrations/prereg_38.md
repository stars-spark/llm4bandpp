<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Name hiding on 12 new sources (realtel-scale-namehide-v1)

## Method

- Sources and ground truth: sources.json and truth_final.json as finalized in realtel-scale-v1, unchanged.
- Name hiding: hide() from realtel-namehide-v1 is reused: field names are replaced, in the order presented, by field_01 to field_NN, and the field's own name in the description text is replaced as well; other field names, code variable names, and containing object names are not hidden. The script self-check confirms no residue.
- LLM: the frozen prompt from realtel-adapter-v1 (hash d2467ef5dc35 verified before running), DeepSeek with the same settings, three field orders per source, 36 calls in total.
- Scoring: full scoring (fields, differences, coefficients), same as realtel-scale-v1.

## Criteria (confirmatory tier template, same as realtel-namehide-v1)

- Primary endpoint: DeepSeek's balanced accuracy after name hiding.
- Δ: the LLM after name hiding minus the best of the seven non-LLM controls under true names (taken from the control readings of realtel-scale-v1; the controls see true names, which favors the controls).
- Interval: block resampling by source 5000 times, 90% interval.
- Holds: lower bound greater than 0 and Δ ≥ 0.15; direction only: Δ > 0; does not hold: Δ ≤ 0, or the mis-mapping rate on no-counterpart decisions exceeds 15%.

## Report only

The drop with hidden names relative to true names (0.920 in realtel-scale-v1); per-source results.

## Unfavorable prediction

SDK documentation text is often very short (e.g., one sentence for Agora and Twilio); with names removed, the LLM may be unable to determine field meanings, and accuracy may drop clearly.

