<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: LLM maps a new client's telemetry interface to the estimator interface (obsschema-llm-v1, 2026-10-02 around 23:00 Beijing time, written before running)

Scenario: a learned estimator must be connected to a new client stack; the telemetry reported by the new client per window has the same meaning as the estimator's 15 interface features, but the field names, units, and order all differ.
At deployment, the LLM reads the new client's field names once, the telemetry quantiles of the first 30 seconds of the first 3 calls, the interface description, and the reference quantiles, and produces a mapping (which source field each interface feature takes and by what coefficient it is multiplied), which code then executes at every step.

## Design

- Six foreign schemas (SCHEMAS in scripts/arb/obsschema_v1.py): development dev_a, dev_b (visible when designing prompts and controls); test test_c, test_d, test_e, test_f (name style and unit combinations held out). Field order is deterministically shuffled by schema name.
- Calls: three groups of 13 calls are drawn from each of the four original scenario directories (one development group, two test groups); calls in the same group are shared across schemas at that stage; the first 3 calls serve as evidence, the remaining 10 for evaluation. The correct mapping restores the original observations element by element (already verified).
- 32 test groups (four scenarios × four schemas × two groups), 8 development groups.
- Methods:
  - LLM (main arm): DeepSeek flash reasoning mode, reads real field names and quantiles.
  - LLM ablation: same prompt, field names replaced with field_01 to field_15 (only distribution information remains).
  - Distribution matching DIST: minimum log-quantile distance plus candidate coefficients, Hungarian assignment.
  - Name matching NAME: literal similarity between field names and interface feature names with Hungarian assignment, coefficients snapped among candidate coefficients by median log distance.
  - Upper bound: correct mapping.
  Prompts are tuned only on the development groups and frozen before the test, with the hash recorded.

## Criteria

Metric: the median over each group's evaluation calls of "post-mapping error ÷ error under the true mapping"; a median of no more than 1.2 counts as mapping success.
- **Holds**: the number of successful groups of the LLM (real names) exceeds that of the better of DIST and NAME by at least 8, and is at least 24 (three quarters).
- **Does not hold**: the number of successful groups of the LLM (real names) is no more than that of the better of DIST and NAME.
- **Inconclusive**: otherwise.
- Mechanism (report only, reading fixed before running): the LLM with real names has at least 8 more successful groups than the LLM ablation, read as "the semantics of field names is the source of gain".

## Predictions unfavorable to us

- Distribution matching may already distinguish most fields by numerical range (rates, bytes and latencies differ in magnitude), leaving a gap under 8 groups.
- Several ratio-type fields (video, audio, probing proportion, packet loss rate) have similar numerical ranges, so the LLM may also confuse them; the estimator may be insensitive to some of them, in which case the confusion does not affect the reading.
- Name matching will fail on schemas with many abbreviations, but on schemas whose field names are close to the interface description it may not lose to the LLM.

## Appendix: open-source model reproduction (obsschema-llm-openmodel-v1, 2026-10-02 around 23:40 Beijing time, written before running)

Same frozen prompt (template hash 4abe82ad), with the model switched to a local Qwen2.5-32B-Instruct, 4-bit (on two GPUs of gpu-server-2, non-reasoning, temperature 0, at most 4096 tokens), 8 development groups and 32 test groups, asked in two forms, with real names and with shuffled field names; parsing, evaluation, and criteria are the same as the main arm.
