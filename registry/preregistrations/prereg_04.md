<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: offline-best λ 0.8 vs deployed λ 0.4 in the 720p closed loop (2026-10-06, fixed before running)

## Design

- **Conditions and sequences**: same as hd720-closedloop-ch-v1.
  - hd_c1, hd_c2, hd_c3, hd_c8, hd_r1, hd_r2, times Johnny, FourPeople, 12 cells total.
  - libwebrtc default 2.5 Mbit/s cap as before, no patch enabled.
- **Two arms**: both in deployed system, i.e. C-H plus 5 kbps floor plus probing envelope v6, arm_ch_x.
  - l04: ch.pt, λ 0.4 seed 1, i.e. the deployed weights.
  - l08: ch_l08s1.pt, λ 0.8 seed 1, selected via STALENESS_CH_CHECKPOINT.
  - 3 runs per arm per cell, interleaved round-robin, 72 runs total, on a single container pair, run script v23.
- **Primary endpoint D_L**: per-cell mean VMAF difference of l08 minus l04, 12 cells equally weighted.
- **Decision**: decided by hd720_ch_eval_v1.judge.
  - holds: 90% interval lower bound greater than −6, and safety line not triggered.
  - direction only: D_L greater than −6, but lower bound not greater than −6.
  - does not hold: D_L not greater than −6, or safety line triggered.
  - Safety line: any cell lower by more than 10 points, or all three runs of l08 invalid in some cell.
  - Fewer than 6 usable cells judged inconclusive.
- **Report only**:
  - superiority: lower bound greater than 0 and D_L not less than 6.
  - per-condition VMAF, freezes, video rate, probing envelope rewrite share.
- **Validity**:
  - same as the 720p batches, i.e. run_metrics and code audit.
  - additionally the weight check seed_weight_check_v2.py: the weights identified by recomputing step by step from the recorded raw model outputs must match the arm key; otherwise no decision is made (tool problem).
- **Weight equivalence check**: on gpu-server-1 the 870 calls are evaluated on CPU with the original evaluation script, and the result must pass the gate against the training-side evaluation on gpu-server-2. Gate same as compare_ch_equiv_v1.py, i.e. per-call relative difference less than 1e-3, macro relative difference less than 1e-4. Discrimination control: the CPU result of λ 0.4 seed 1 must fail the gate against the λ 0.8 reference.

## Predictions unfavorable to us

- λ 0.8 overestimates more at 1 Mbit/s and in trace windows, freezes more, and D_L may be negative.
- If D_L is not less than 0, the offline gain has no closed-loop cost; the deployment nevertheless stays at λ 0.4 and other batches are not rerun.

