<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Interface adaptation of an open-source reasoning model on new foreign schemas (obsschema-openreason-newschema-v1, 2026-10-02 around 16:55 Beijing time, written before running)

## Design

- Five new foreign schemas: test_g to test_j (never used offline), plus rt_getstats (constructed according to WebRTC getStats conventions, see scripts/arb/obsschema_rt_v1.py).
- 40 completely new groups of calls: on gpu-server-1, scripts/arb/obsschema_rt_offline_v1.py draws two more sets of 13 calls for each scenario (seed 20261702 + 100 × scenario number + set number), excluding all groups of obsschema-llm-v1 and the 196 calls used for the sensitivity measurement, giving 104 new calls; the same set of calls is shared by the five schemas; each group has 3 calls of evidence and 10 calls of evaluation.
- Prompts: the frozen template of obsschema-llm-v1 (hash checked), asked in two ways, with true names and with shuffled field names (field_01 to field_15), 80 prompts in total, built as for the main arm.
- Main arm: DeepSeek-R1-Distill-Qwen-32B, 4-bit (on two GPUs of gpu-server-1, vLLM, temperature 0.6, top-p 0.95, at most 32768 tokens, one sample per group), with the same settings as obsschema-llm-openreason-r1_32b. Report-only arm: R1 distilled 14B (on two GPUs of gpu-server-2, same settings).
- Evaluation: same as obsschema-llm-v1, per call, the error after mapping is divided by the error under the true mapping, and a within-group median no greater than 1.2 counts as success; an unparseable answer means no adaptation and counts as failure. Distribution matching and name matching use the same evidence.

## Criteria (confirmatory tier template)

Main endpoint Δ = (number of successful groups for the LLM with true names − number of successful groups for the better-performing one of distribution matching and name matching) ÷ 40, with a 90% interval from 5000 block resamples by call set (scenario times set number, 8 sets).
Holds: interval lower bound greater than 0 and Δ ≥ 0.25 (the same as the original criterion of 8 more groups divided by 32). Direction only: Δ > 0, not reaching holds. Does not hold: Δ ≤ 0, or the safety line is crossed, namely the number of groups where the LLM's true-name ratio median exceeds 2 is greater than for the better statistical method.

Report only: success counts by schema (rt_getstats listed separately); success counts with shuffled field names; the mechanism reading follows the original pre-registration (written down before running), and true names exceeding shuffled by at least 10 groups (one quarter of 40) is read as "the semantics of field names is the source of gain"; all readings of the 14B arm; counts of parsed answers and of answers that hit the token limit.

## Unfavorable predictions

(1) the 4-bit 32B model was correct on only 3/8 groups of the old schema test_e, and in the new schemas unit combinations of the same kind (seconds, per mille) may fail again; (2) rt_getstats field names are very long and have prefixes, so reasoning may hit the token limit without an answer; (3) statistical methods may do well on schemas with simple coefficients, narrowing the gap.
