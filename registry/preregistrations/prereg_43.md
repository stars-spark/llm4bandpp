<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Interface-adaptation closed loop with the one-token LLM variant downstream (obsschema-closedloop-llm4bandpp-v1, 2026-10-02 around 16:20 Beijing time, written before the run)

## Question

When the downstream estimator is the one-token LLM variant (collector v6, probing envelope v4, i.e. the configuration c3_v6_env4 chosen for deployment by llm4bandpp-online-unlock-v1), can the interface mapping given by the LLM get closer to the closed-loop performance under the true mapping than the best statistical mapping?

## Design

- Estimator arm arm_llm4bandpp_schema (deploy/fixed_schema_llm4bandpp_v1.py): the collector output is first rewritten into the foreign schema, then mapped back into the 15 interface features and fed to both the model and the envelope; the interface and adapter layers are element-wise identical to those of arm_default_schema (self-check test_fixed_schema_llm4bandpp_v1.py passes). Run script v11 and entry point v8, both new files.
- Five foreign schemas: the four held-out schemas test_g to test_j of obsschema-closedloop-v2, plus rt_getstats. The field names of rt_getstats carry statistical type prefixes (inbound-rtp, transport), time quantities use seconds, loss uses a 0 to 1 ratio, rate uses webrtc-internals' bytesReceived_in_bits/s; the field meanings are still the 15 interface features, not data exported by a real client.
- Mapping: the LLM, distribution matching, and name matching mappings of the four held-out schemas follow v2's maps.json as is (the mapping depends only on the evidence and field names, and is independent of the downstream estimator; the model is not re-tuned); rt_getstats uses the same three evidence calls as v2, the frozen prompt of obsschema-llm-v1 (template hash checked), and one DeepSeek inference call; if the answer cannot be parsed, no adaptation is applied. We had not looked at v2's closed-loop results.
- Windows: rule obsschema_rt_v1, seed 20261007; 8 windows of 120 seconds, rt_1 to rt_8, are taken from Norwegian 3G traces not used by any existing profile (driving 2, tram 3, train 2, bus 1, mean 475 to 3234 kbit/s).
- 21 conditions per window: no error; for each of the five schemas, no adaptation, LLM, distribution matching, name matching. Conditions within a window are shuffled by seed; four container pairs run in parallel on the local machine; balanced power mode, media collection on, 168 runs in total.
- Smoke test before the run (not counted): on v2 evidence window es_1, one no-error run and one rt_getstats run without adaptation; both must be valid and the condition in the startup log must be correct. If the smoke test fails, the batch stops for investigation.
- The condition audit cl_condition_audit_v1 is run before judging, with the same rule as obsschema-closedloop-v2; no conclusion is produced if a hard check fails.

## Criteria (confirmatory tier template, same judging function obsschema_cl2_v1.judge written down before the run as in obsschema-closedloop-v2)

The primary endpoint is the deviation from the true mapping |U(method) − U(no error in the same window)|, cells are schema × window, 40 in total. Δ = mean deviation of the best statistical method (the one with the smaller mean deviation between distribution matching and name matching) − mean deviation of the LLM, with a 90% interval from 5000 block resamples by window.
Holds: interval lower bound greater than 0 and Δ ≥ 3. Direction only: Δ > 0, not reaching holds. Does not hold: Δ ≤ 0, or the safety line is crossed, i.e. the LLM has a cell more than 10 points below no error in the same window. Invalid runs are removed according to the run script rules.

Report only: deviation by schema (rt_getstats listed separately), number of severe-loss cells per method, mean utility, mean quality, whether each mapping item is correct, no-error utility on each container pair, 95th percentile of the computation time of the one-token LLM variant.

## Unfavorable predictions

(1) the envelope rewrites about 95% of decisions of the one-token LLM variant (llm4bandpp-online-unlock-v1); if wrong mappings act mainly through the envelope, the deviations of all methods may become smaller, and Δ may not reach 3.
(2) the coefficients of rt_getstats are simple (mostly 1 and 1e-3), distribution matching may also get this schema right, narrowing the gap; the second-based delay fields may also make the LLM choose the wrong coefficients.
(3) running Qwen 0.5B inference on CPU on four container pairs in parallel may lengthen the decision interval, and absolute utility is not directly comparable with v1 and v2 (the criteria use only differences within the same experiment).

## Relation to existing experiments

It is a "new question": the downstream estimator is different, and it asks whether we can deploy our own estimator to a new client. It is parallel to v2, and the conclusions do not rewrite each other; each claim gets only this one confirmation, and no rerun is made for the same claim regardless of whether the conclusion is favorable or not.
