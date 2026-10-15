<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: 720p echo attribution and random packet loss (drafted 2026-10-05 around 11:40 Beijing time, fixed before running)

## Common setup

- **Deployed system under test.** C-H plus 5 kbps estimate floor plus envelope v6 (arm_ch_x; collector v6, BWE_ENVELOPE=6, BWE_MIN_BPS_FLOOR=1).
  - Module sha256 prefix cec41ba6, weights 954c68d2.
  - Run script v20, entry point v15, arms v8.
- **Control GCC.** Corrected Python GCC called every 200 milliseconds (gcc_pt125_c200).
- **720p setup same as hd720-closedloop-ch-v1.**
  - Video-call sequences Johnny and FourPeople (contents.json copied from that batch), 30 fps.
  - Sender egress shaping, one-way delay 50 milliseconds, two container pairs in parallel, scheduler v2.
- **Run validity.** Use hd720_run_metrics_v1.run_metrics and code_audit; non-GCC arms additionally get the v6 check (hd720_ch_eval_v1.env6_check). Invalid runs are recorded and not deleted.
- **Scripts.**
  - scripts/alphartc/deploy/hd720_attr_loss_v1.py, selftest passed.
  - Intervals and safety lines decided by hd720_ch_eval_v1.judge: stratified resampling by cell 10000 times, seed 20261003, 90% interval; fewer than 6 usable cells judged inconclusive; a cell whose control runs are all invalid is dropped.

## 1. hd720-echo-attr-ch-v1 (behind the envelope, how much more the estimator brings than echo)

- **Conditions and scale.** hd_c1, hd_c2, hd_c3, hd_c8, hd_r1, hd_r2 times two sequences, 12 cells total. Three arms (GCC, deployed system, echo plus v6), each arm 3 times per cell, interleaved in rotation in the same batch, 108 runs total.
- **Primary endpoint D_E.** Per cell, the mean VMAF of the three C-H runs minus that of the three echo runs, 12 cells equally weighted.
- **Decision.**
  - Here the question is whether there is a detectable contribution, so no separate magnitude threshold is set; magnitude is reported as is, and it is stated whether it reaches 6 points (the superiority line for our 720p batches).
  - Holds: lower bound greater than 0, and safety line not triggered.
  - Direction only: D_E greater than 0, but lower bound not greater than 0.
  - Does not hold: D_E not greater than 0, or safety line triggered.
- **Safety line.** Any cell C-H lower than echo by more than 10 points, or all three C-H runs invalid in some cell.
- **Report only.**
  - Echo vs GCC and C-H vs GCC, computed the same way, to separate the parts due to the envelope and to the estimator.
  - Freezes, video rate, envelope rewrite share.
  - C-H vs GCC is not a recheck of hd720-closedloop-ch-v1; that conclusion is unchanged, and if the two disagree, both are reported.

## 2. hd720-randloss-ch-v1 (whether under random packet loss it is not worse than GCC by more than 6 points)

- **Conditions.** hd_l2p1, hd_l2p5, hd_l8p1, hd_l8p5 under profiles/hd720_loss, times two sequences, 8 cells total.
  - Capacity constant 2 or 8 Mbit/s, queue packet counts same as original files (53, 209).
  - Random packet loss 1% or 5%, applied by netem loss random on all UDP at the sender egress.
- **Scale.** Two arms, GCC and the deployed system, each arm 3 times per cell, 48 runs total.
- **Primary endpoint D_L.** Per cell C-H minus GCC VMAF mean difference, 8 cells equally weighted.
- **Decision.** Identical to hd720-closedloop-ch-v1, using judge directly.
  - Holds: lower bound greater than −6, and safety line not triggered.
  - Direction only: D_L greater than −6, but lower bound not greater than −6.
  - Does not hold: D_L not greater than −6, or safety line triggered.
  - Safety line: any cell lower by more than 10 points, or all three C-H runs invalid in some cell.
  - Superiority is reported but not judged.
- **Validity adds a packet loss check.** Each applied loss_pct in the control log equals the setting, and netem in the shape log carries the same loss value; otherwise judged invalid.
- **8 Mbit/s does not use a decoded frame rate threshold.** The original file's "lightweight arm decoded frame rate not lower than 25" checks whether CPU can keep up; frame rate drop in the loss files is a network effect. Frame rate is reported as is.
- **Smoke (not counted).** On hd_l8p5 with KristenAndSara (not part of the main batch sequences), C-H and GCC 1 run each. SMOKE_OK is written only if both runs are valid, the packet loss check passes, the measured packet loss rate is between 2% and 10%, and the C-H v6 check passes; the main batch runs only after SMOKE_OK.

## 3. Predictions unfavorable to us (written down before running)
1. **Echo attribution may only reach direction only, or even tie.**
   - The probing envelope rewrites about 80% of decisions at 720p.
   - Echo is already 3.7 higher than GCC in another batch.
   - At 1 Mbit/s and on two real traces, echo may not be worse than C-H.
   - The cross-batch estimate of +2.5 may itself have ±2 batch-to-batch error (in the competing-flow test, the share of the deployed system differed by about 0.05 between two batches, a precedent for batch-to-batch difference).
2. **D_E does not reach 6 points.**
3. **Under 5% random loss, C-H may degrade more than GCC.**
   - The probing envelope only declares congestion when loss exceeds 10%, so 5% does not trigger it, and here the output is determined by the model and F.
   - Random loss is rare in the model training data, so it may read loss as congestion and lower the rate.
   - GCC maintains rate between 2% and 10% loss.
4. **Under 5% loss, the absolute VMAF of both arms will drop noticeably.** Non-inferiority holding does not mean visual quality is good under 5% loss.

