<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Schaferct's network architecture plus our recipe (schaferct-arch-recipe-v1, 2026-10-07, measurement only)

## Design
- Architecture: Schaferct v14_iql.py GaussianPolicy copied verbatim (Linear(150,256)+ReLU, two-layer GRU(256), Linear(256,256)+ReLU, two residual blocks, Linear(256,1)+Tanh, multiplied by 20 Mbit/s and clipped to no less than 10 bit/s), 1 157 528 parameters;
  The GRU is used as at inference time, with each sample as a single step and a zero initial state (its training-time practice of treating the whole batch as one sequence is not replicated). Generation script scripts/encoder/make_schaferct_arm_v1.py, estimator.py sha256 prefix 8153c33781de638f.
- Recipe: identical to the C-H cell of nl_2x2_v1 (same IQL.py, module.py, model.py, dualEncoder.py, hash-verified; λ 0.4, capacity anchor weight 1, balanced replay 3.5 million, 50k steps, only the 50 000-step checkpoint is read), seeds 0, 1, 2, on two GPUs of gpu-server-2.
- Evaluation: eval_value_per_file.py, 870 validation calls, same as nl_2x2 and ch-lambda-sweep.

## Criteria (fixed before running)
- Measurement only, no verdict: the three-seed mean and range of macro MSE, per-scenario MSE, e+ and e− are reported alongside C-H over three seeds (5.819, nl_2x2_v1) and Schaferct-R (7.074, its own recipe). "Holds" (readings complete) is recorded once all three seeds are evaluated.
- Report only: difference from C-H (the difference of the three-seed means and whether the ranges overlap).

## Prediction unfavorable to us
- The recipe is the main source of gain: Schaferct's architecture plus our recipe may tie with or even beat C-H, in which case the contribution of the "estimator" should be attributed to the recipe, not the architecture.

