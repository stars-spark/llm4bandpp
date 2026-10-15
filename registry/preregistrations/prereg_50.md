<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Stronger baselines for real telemetry interface adaptation (realtel-baseline-strength-v1)

## Question

After swapping in published schema-matching tools and retrieval with pretrained semantic vectors, does DeepSeek's advantage in writing adapters on real telemetry still hold?

## Tested system and baselines

**LLM:** The DeepSeek output from realtel-adapter-v1 is used directly; the run is shared, with no new calls. Its result is known; the only unknown in this experiment is on the baseline side.

**Seven baselines in total:**
- Three public schema matchers from Valentine 1.0: Coma (schema only), Cupid, Similarity Flooding. They read only field names, not descriptions.
- Two pretrained semantic vector models for retrieval: BAAI/bge-large-en-v1.5, with the officially recommended retrieval instruction appended to the query; sentence-transformers/all-mpnet-base-v2, mean pooling. The text "field name, containing object, full description" is compared with the feature description by cosine similarity.
- The NAME and TFIDF from v1.

**The decision rule is identical throughout:** each feature takes the highest-scoring field, and answers missing if below threshold. The threshold is chosen only on the two development sources, as the one with the highest balanced accuracy on them; ties take the smaller threshold.

## Criteria (confirmatory tier template)

To favor the baselines, the primary endpoint looks only at whether the field is correctly identified, not at differences and coefficients.

- **Scoring:**
  - For same quantities, a correct field counts as correct;
  - For no counterpart, answering missing counts as correct;
  - The LLM is also scored by the same rule.
- **Primary endpoint:** balanced accuracy, the average of the two classes' correct rates.
- **Δ:** LLM minus the best of the seven baselines. The best is chosen post hoc, compared only on the average.
- **Interval:** block resampling by source 5000 times, 90% interval.

| Conclusion | Condition |
|---|---|
| holds | interval lower bound greater than 0 and Δ ≥ 0.15 |
| direction only | Δ > 0 |
| does not hold | Δ ≤ 0 |

**Safety line** follows v1: the LLM's mis-mapping rate on no-counterpart decisions does not exceed 15%. In v1 it is known to be 0.

## Report only

- Full scoring including differences and coefficients;
- Per-source results;
- Readings for the open-source R1 distilled 32B and 14B by the same rule.

## Unfavorable predictions

- The semantic vector models read the full description and may correctly identify most same quantities.
- The threshold chosen on the development sources may also happen to block decoy fields, so Δ may fall below 0.15.
- Valentine's matchers are designed for aligning two tables, and may be very weak here, in which case they only show that the public tools are inapplicable, and cannot serve as strong baselines.

