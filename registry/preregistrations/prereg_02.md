<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Learned baselines behind the same probing envelope in the 720p closed loop (2026-10-06 evening, written down before running)

## Design

- **Conditions and sequences**: same as hd720-closedloop-ch-v1.
  - 6 conditions × Johnny, FourPeople, 12 cells in total.
  - The default 2.5 Mbit/s cap remains unchanged.
- **Three arms**: all use the same deployed system, namely collector v6, 5 kbps floor, probing envelope v6, code online_llm_arms_v8._Base, with only the model swapped across the three arms.
  - ch: the deployed C-H, namely ch.pt.
  - scr: Schaferct-R, the same ONNX as Table I.
  - mlp: the supervised MLP (Table I, seed 0).
  - The latter two arms are connected by deploy/fixed_x_v2.py, run script v24.
  - Each arm runs 3 times per cell, interleaved in rotation, 108 runs in total, on a single container pair.
- **Primary endpoint D_S**: per cell, the VMAF mean difference of ch minus scr, with 12 cells equally weighted.
- **Decision**: call hd720_ch_eval_v1.judge.
  - holds: interval lower bound greater than −6, and safety line not triggered.
  - direction only: D_S greater than −6, but lower bound not greater than −6.
  - does not hold: D_S not greater than −6, or safety line triggered.
  - Safety line: any cell lower by more than 10 points, or all three runs of ch invalid in some cell.
  - Fewer than 6 usable cells is judged inconclusive.
- **Report only**:
  - Superiority: lower bound greater than 0 and D_S not less than 6.
  - The difference ch minus mlp, computed the same way.
  - Per-arm, per-condition VMAF, SSIM, freezes per minute and mean freeze duration, packet loss rate, latency score, video rate, probing envelope rewrite share.
- **Smoke** (exploratory, not counted): hd720-learned-smoke-v1, scr and mlp 1 run each, both valid.
  - Code hash includes fixed_x_v2.py and both models.
  - Probing envelope rewrite about 97%, VMAF about 89 at 2 Mbit/s, close to the historical reading of ch at this level.

## Predictions unfavorable to us

- The smoke test already shows that the estimates of both arms are almost entirely rewritten by the probing envelope, so D_S is very likely close to 0, judged as "holds (non-inferior)" but superiority not reached.
  - This means that behind the same probing envelope, the closed-loop difference between learned estimators is very small, and the closed-loop gain mainly comes from the probing envelope.
- The supervised MLP has far lower offline MSE; if the closed loop also ties, then offline accuracy does not translate into visual quality behind the probing envelope.

