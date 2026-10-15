<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Name hiding on real telemetry (realtel-namehide-v1)

## Method

- **Name hiding:** The seven real sources are those of realtel-adapter-v1; field names are replaced in transcription order with field_01 to field_NN. Occurrences of that field's own name in the original description are also replaced with the same identifier: identifier-style occurrences are replaced as whole strings, and ordinary words are replaced only when quoted or backticked.
- **Not hidden:** Other field names, code variable names, containing object names.
- **Verification:** A script self-check confirms that the field's own name does not remain in the description.
- **LLM:** The frozen prompt from realtel-adapter-v1 is reused, with its hash verified before running. DeepSeek with the same settings, three field orders per source, 21 calls total.
- **Ground truth:** Version 3 (truth_v3.json, checked by two independent LLM checks), full scoring, i.e. fields, differences, and coefficients must all be correct.

## Criteria (confirmatory template)

- **Primary endpoint:** DeepSeek's balanced accuracy after name hiding.
- **Δ:** The LLM after name hiding minus the best of seven non-LLM controls that see the real names. The seven are NAME, TFIDF, Coma, Cupid, Similarity Flooding, bge-large, all-mpnet, using fields selected by development thresholds, with generic unit and difference rules, full scoring. This comparison favors the controls.
- **Interval:** Block resampling by source 5000 times, 90% interval.

| Conclusion | Condition |
|---|---|
| holds | lower bound greater than 0 and Δ ≥ 0.15 |
| direction only | Δ > 0 |
| does not hold | Δ ≤ 0, or the LLM's false mapping rate on decisions with no counterpart exceeds 15% |

## Report only

- The drop from real names to hidden names;
- Per-source results.

## Unfavorable prediction

- The LLM may indeed rely on interface names, and after name hiding may drop noticeably on sources that depend on names such as W3C and tcp_info.
- For sources where the original description is only a code snippet (iperf3, tcp_info), it may be difficult after name hiding to determine differences and units.

