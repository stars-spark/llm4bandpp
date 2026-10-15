<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Closed-loop confirmation of the interface adapter for a new client (obsschema-closedloop-v2, confirmatory tier, 2026-10-02 around 14:45 Beijing time, fixed before running)


## Design

- Foreign schemas: four new held-out schemas test_g to test_j (added in scripts/arb/obsschema_v1.py; four naming styles: camelCase, metric names, abbreviations, English with spaces; units include kbit/s, Mbit/s, KiB, kB, bit, microseconds, seconds, percent, per-mille), with conversion factors all within the candidate factors of the statistical methods. The testbed interface layer (deploy/fixed_schema_x_v1.py) is element-wise consistent with the offline version (self-check passed).
- Windows: Norwegian 3G traces (driving, train, tram, bus) not used by any existing profile (rule obsschema_cl2_v1, seed 20261005); evidence es_1 to es_3, evaluation sd_1 to sd_8.
- Evidence: one error-free run on each of es_1 to es_3 (media off); the estimator input before adaptation (with audio) is rewritten into the foreign fields of each schema, and quantiles are computed from the first 30 seconds of each run.
- Mapping: the LLM uses the frozen prompt of obsschema-llm-v1 (template hash 4abe82ad), DeepSeek flash in reasoning mode, one call per schema; an unparseable answer means no adaptation; DIST and NAME use the same evidence.
- Evaluation: 17 conditions per window: error-free as-is; for each of the four schemas: no adaptation, LLM, DIST, NAME. 136 runs total plus 3 evidence runs. arm_default_schema, run script v10, media on, scoring version 2 (tesseract single-threaded). Runs on the cloud testbed (testbed-cloud-check-v1) with two container pairs in parallel; if that check does not hold, locally with four container pairs in parallel. The condition audit is the same as in the other closed-loop experiments of that day.

## Criteria (confirmatory tier, locked before run)

- Primary endpoint: deviation per schema-by-window unit = |U(method) − U(same-window error-free)|. Δ = mean deviation of the best statistical method − mean deviation of the LLM, where the best statistical method is the one with smaller mean deviation among DIST and NAME (selected post hoc, biased toward the control); 90% interval from 5000 block resamples by window.
- **Holds**: interval lower bound greater than 0, and Δ ≥ 3 points.
- **Direction only**: Δ > 0, not reaching holds.
- **Does not hold**: Δ ≤ 0, or safety line crossed.
- Safety line: no LLM unit is more than 10 points below same-window error-free.
- Report only: severe loss (more than 10 points below error-free) unit counts per method, mean utility, mean quality, whether mapping is correct item by item, error-free utility per container pair, condition audit summary.

## Predictions unfavorable to us

- If field names in the new schemas are plain enough, NAME may map correctly most of the time, with a deviation close to the LLM's, and the verdict would be direction only.
- Testbed utility is itself noisy: repeats in the same window can differ by several points, so the LLM's deviation will not be 0 and may reach 2 to 3 points, shrinking Δ.
- The LLM may map incorrectly on new naming styles (e.g., per-mille, KiB), causing severe loss and a verdict of does not hold.
