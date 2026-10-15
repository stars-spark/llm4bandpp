<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Closed-loop re-check after switching deployed system to C-H (drafted 2026-10-04 around 23:50 Beijing time, fixed before running)

## 1. Estimator under test and selection rule (fixed before results)

- **Composition of C-H:**
  - Conference encoder: Linear(150,1024), LayerNorm, LeakyReLU, outputs one vector fed directly to the head;
  - Head identical to the multi-scale variant's: 1024 to 512 to 1, tanh output multiplied by 20 Mbit/s;
  - HCQ reward λ 0.4 (error term cap 5), capacity anchor (Huber, weight 1, knee 1 Mbit/s), IQL, 50k steps, batch 512, training code the same as the two conference-encoder cells of the 2×2;
  - Parameters 683,160.
- **Seed:** the seed with the median macro MSE of the three on the 870-call validation set, i.e. seed 1 (5.795; seed 0 is 5.868, seed 2 is 5.792). The rule was written into the header of scripts/alphartc/deploy/ch_smoke_v1.py before the seed 1 result was known; it is the same rule that selected seed 1 for the multi-scale variant (NL).
- **Testbed modules:**
  - scripts/alphartc/deploy/ch_estimator_v1/ch_estimator_v1.py extracted verbatim from training code by build_ch_estimator_v1.py, sha256 prefix cec41ba6; weights ckpt/ch.pt, prefix 954c68d2.
  - Equivalence check: with the original evaluation script on gpu-server-1, on CPU, over the 870 calls, maximum per-call relative difference 2.3e-6 and macro relative difference 3.2e-8; the control (seed 0) is blocked. Recorded in the READY file.
- **New arm and new files:** arm_ch_x loaded by online_llm_arms_v6.py, entry point v13, run script v18. Collector v6 and probing envelope v6 as for the multi-scale variant (NL), with only the model switched.

## 2. hd720-closedloop-ch-v1 (claim one, criteria identical to hd720-closedloop-nl-v1)

- **Units:** 6 conditions (hd_c1, hd_c2, hd_c3, hd_c8, hd_r1, hd_r2) times 2 sequences (Johnny, FourPeople), 12 total.
- **Arms:**
  - GCC every 200 ms;
  - C-H plus envelope v6 (arm_ch_x);
  - The multi-scale variant (NL, arm_llm4bandpp_nl_x) plus envelope v6, for claim two.
- **Scale:** 3 runs per cell, 108 total, run script v18, two container pairs in parallel.
- **Primary endpoint D:** per cell, the three-run mean VMAF of C-H minus that of GCC, 12 cells equally weighted.
- **Interval:** stratified resampling by cell 10000 times, seed 20261003, 90% interval.
- **Decision (non-inferiority, margin 6 VMAF):**
  - holds: lower bound greater than −6, and safety line not triggered;
  - direction only: D greater than −6, but lower bound not greater than −6;
  - does not hold: D not greater than −6, or safety line triggered.
- **Safety line:** any cell lower by more than 10 points, or all three C-H runs invalid in some cell.
- **Report only:** superiority (lower bound greater than 0 and D not less than 6).
- **Decision script:** scripts/alphartc/deploy/hd720_ch_eval_v1.py, decision function and selftest taken verbatim from hd720_nl_eval_v1, selftest passed.

## 3. hd720-ch-vs-nl-v1 (claim two, same batch and runs as claim one)

- **Question:** after switching to C-H, is 720p closed-loop quality meaningfully worse than the multi-scale variant (NL)?
- **Primary endpoint D2:** per cell, the mean VMAF of C-H minus that of the multi-scale variant (NL), 12 cells equally weighted. Interval, decision function, margin 6 VMAF same as claim one.
- **Safety line:** any cell C-H lower than the multi-scale variant (NL) by more than 10 points, or all three C-H runs invalid in some cell.
- **Relation of the two arms:** they differ only in the encoder; reward and training recipe are the same.

## 4. compete-flow-ch-v1 (claim three, criteria identical to compete-flow-nl-v1)
- **Condition and share definition:** unchanged (T2, T3, G2, competition window 40th to 90th second, Johnny 720p).
- **Arms:** GCC, C-H plus envelope v6, the multi-scale variant (NL) plus envelope v6 (report only). 3 runs per cell, 27 total.
- **Primary endpoint S:** C-H share minus GCC share, three conditions equally weighted.
- **Decision:**
  - holds: lower bound greater than −0.10, and safety line not triggered;
  - direction only: S greater than −0.10, but lower bound not greater than −0.10;
  - does not hold: S not greater than −0.10, or safety line triggered.
- **Safety line:** any condition where C-H average share is more than 0.15 above GCC, or any condition where all three runs are invalid.
- **Decision script:** compete_flow_ch_eval_v1.py, selftest passed.

## 5. lowbw-ch-vs-conf-v1 and lowbw-ch-vs-conf-env6-v1 (claims four and five, criteria identical to the two lowbw-nl entries)

- **Conditions:** constant 100, 200, 300, 400 kbps, source 320x240, 15 fps, collector v6.
- **Four arms:** C-H without probing envelope, LLM4Band without probing envelope, C-H plus envelope v6, LLM4Band plus envelope v6. 3 runs per cell, 48 total, run script v18.
- **Primary endpoint D:** utility difference equally weighted over the four capacity cells (C-H minus LLM4Band). Claim four compares the two arms without probing envelope, claim five compares the two arms with envelope v6.
- **Decision:** non-inferiority bound −5.27, safety line is any cell more than 10 points lower, or any C-H cell where all three runs are invalid.
- **Decision script:** lowbw_ch_vs_conf_v1.py, selftest passed.
- **Smoke:** no separate run. The exploratory smoke test already checked the wiring with run script v18.

## 6. client-hw-ch-v1 (measurement only, protocol identical to client-hw-nl-v1)

- Arms ch, nl, hcq measured in the same round, on four CPU threads and the laptop GPU, batch 1, 50 warm-up and 500 measured runs. Script scripts/measure_client_hardware_v5.py.
- Validity gates:
  - testbed not running during measurement, load below 2 in the minute before start;
  - connected to external power;
  - SM frequency at end of GPU measurement no more than 15% below pre-measurement.
  - any failure recorded as void and remeasured.

## 7. Predictions unfavorable to us (written before running)

1. **Claim four likely does not hold.** In the exploratory smoke test C-H was invalid in both runs at 100 kbps; if all three runs in that cell are invalid in the main batch, the safety line is triggered; 200 kbps may also be about 6 points below LLM4Band.
2. **Claim five likely holds.** With probing envelope the two arms are close, but this only shows the probing envelope works.
3. **At 720p, C-H and the multi-scale variant (NL) are likely close.** D2 is expected within ±3, because the probing envelope rewrites about eighty percent of decisions at 720p. C-H is slightly worse offline at high bandwidth (13.97 vs 13.74), so the 8 Mbit/s cell may be slightly lower.
4. **Claims one and three are expected to be on par with the multi-scale variant (NL).** The multi-scale variant reads D +4.63 and S −0.004; C-H is not necessarily better.

