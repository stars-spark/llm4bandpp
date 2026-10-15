<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Derivation function (closure) on a real client, version 2 (realtel-closure-v2)

## The only change

For all methods, missing features, i.e. those returned as None or that cannot be read, are filled with the per-feature median of the training data, using the short-window median for the short window and the long-window median for the long window.

- Source: the ref field of experiments/results/obsschema_rt_openreason_v1/evidence.json, i.e. the quantiles of dt_stage_v1 over multiple calls. The first 16 hex digits of the sha256 of ref are aeccde6eac2e7b67.
- The all-missing control accordingly becomes "fill all with the median".

## Unchanged

- LLM code: the frozen design_frozen.py from v1 is reused (sha256 1ca44ae99fd8…), not regenerated.
- Controls: seven non-LLM field mappings.
- Estimator: the challenge baseline (baseline.onnx).
- Ground truth: packet capture fed to audit collector v5.
- Assembly and overwrite: same slot assembly; f12 to f14 are overwritten with constants.
- Warm-up: the first 50 steps are not counted.
- Criterion: holds if Δ ≥ 0.10 and the interval lower bound is greater than 0, direction only if Δ > 0; the conditions for does not hold are unchanged, including the safety line at an exception rate above 5%.
- Report-only items: LLM field mapping, open-source 32B code.

## New data

8 entirely new runs, with conditions the same as v1: bandwidth caps 1 and 2.5 Mbit/s, packet loss 0 and 3%, two each. Run names use suffixes c and d to distinguish them from v1; the 8 runs of v1 do not enter the judgment of v2.

## Unfavorable predictions

- What is filled is a fixed median latency; under congestion the true queueing is far greater than the median, so the estimator may still overestimate, and the advantage of the LLM code at 1 Mbit/s may disappear.
- The good results of the exploratory run come from the same batch of data and may shrink on new runs.

