<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Closed-loop re-check of the no-LLM deployed system (drafted 2026-10-04 at 15:11 Beijing time)

All three are confirmatory tier, with the registration reason "method changed": the deployed estimator under test has changed, while conditions, endpoints, and criteria are carried over unchanged from the two batches of envelope v6 (hd720-closedloop-env6-v1, compete-flow-v2).

## 1. Estimator under test and selection rule (fixed before running)

- Source: the no-LLM arm of llm-indispensability-mt-anchor-3seed (code at /path/to/server/work/caiql_llm_screen_v2r1/nollm_mt_anchor on gpu-server-2; the hashes of the five source files match the registration).
  - Structure: one four-path dual-scale LSTM encoder per feature (short-term, long-term, cross-scale, bidirectional, gated fusion, output 8-dimensional), a 2-layer Transformer aggregator (width 8), per-position projection to 1024, readout of the last token, head 1024 to 512 to 1, tanh multiplied by 20 Mbit/s.
  - Training: IQL, HCQ reward λ 0.4 (error term capped at 5), capacity-anchoring weight 1.0, 50k steps, batch 512.
  - 926,888 parameters, of which the temporal attention module's 220,500 are computed but do not enter the output (disclosed in supplementary material).
- **The deployed seed is the one with the median offline macro MSE among the three seeds, i.e., seed 1** (5.809; seed 0 is 5.867, seed 2 is 5.716). Selected by this rule before any closed-loop run, not as the best seed. Weight sha256 0e08406d….
- The testbed module `scripts/alphartc/deploy/nl_estimator_v1/nl_estimator_v1.py` is extracted verbatim from the training code by `build_nl_estimator_v1.py`, removing only the imports of transformers and peft; the new arm is `arm_llm4bandpp_nl_x` (online_llm_arms_v5.py, entry point v11, run script v16).
  - Equivalence check in exploration record nl-deploy-equiv-v1: on gpu-server-1, using the original evaluation script, the 870 calls are evaluated on CPU and compared call by call.
- Single-step inference on four laptop CPU threads: p50 7.3 ms, p99 7.9 ms (exploratory reading; the confirmatory cost measurement is registered separately).

## 2. hd720-closedloop-nl-v1 (claim one, criteria identical to hd720-closedloop-env6-v1)

- Units: 6 conditions (hd_c1, hd_c2, hd_c3, hd_c8, hd_r1, hd_r2) times 2 sequences (Johnny, FourPeople), 12 cells in total. Content and caps carried over from hd720-closedloop-v1.
- Arms:
  - GCC every 200 ms;
  - no-LLM plus envelope v6 (arm_llm4bandpp_nl_x, collector v6, BWE_ENVELOPE=6);
  - the one-token LLM variant plus envelope v6 (arm_llm4bandpp_x), for claim two.
- Scale: 3 runs per cell, 108 runs in total, run script v16, container pairs p1 and p2.
- Primary endpoint D: per cell, the mean VMAF of three runs of no-LLM plus envelope v6, minus the mean of three GCC runs, averaged with equal weight over the 12 cells.
- Interval: stratified resampling by cell, 10000 times, seed 20261003, 90% interval.
- Decision (non-inferiority, bound 6 VMAF):
  - holds: lower bound greater than −6, and safety line not triggered;
  - direction only: D greater than −6, but lower bound not greater than −6;
  - does not hold: D not greater than −6, or safety line triggered.
- Safety line: any cell lower by more than 10 points, or all three runs of one of our cells invalid.
- Validity: same as the v6 batch, including the probing envelope v6 check. Invalid runs are recorded, not deleted.
- Decision script: `scripts/alphartc/deploy/hd720_nl_eval_v1.py`, decision function and selftest taken verbatim from hd720_env6_eval_v1.

## 3. hd720-nl-vs-llm-v1 (claim two, same batch and runs as claim one)

- Question: in the deployed system, if the LLM executed at every step is removed, is closed-loop quality meaningfully worse than with the LLM (the one-token LLM variant)?
- Primary endpoint D2: per cell, the mean VMAF of three no-LLM runs, minus the mean of three with-LLM runs, averaged with equal weight over the 12 cells. Interval as above.
- Decision: same decision function, same bound 6 VMAF.
- Safety line: any cell where no-LLM is lower than with-LLM by more than 10 points, or all three runs of a no-LLM cell invalid.
- The two arms have different recipes: no-LLM is fifteen tokens, capacity-anchored, 50k steps; with-LLM is one token, 1.24M steps. So this compares two deployed configurations, not an architecture-matched ablation. The architecture-matched ablation was already done offline by llm-indispensability-mt-anchor-3seed, with the conclusion of a tie.

## 4. compete-flow-nl-v1 (claim three, criteria identical to compete-flow-v2)

- Conditions:
  - T2: 2 Mbit/s, one TCP CUBIC, from second 30 to 90;
  - T3: 3 Mbit/s, same as above;
  - G2: 2 Mbit/s, one 720p call with GCC every 200 ms.
- Main call Johnny 720p, competition window from second 40 to 90.
- Arms: GCC every 200 ms; no-LLM plus v6; with-LLM plus v6, report only, pinned to container pair p1. 3 runs per cell, 27 total.
- Share: video payload rate ÷ (video payload rate + competitor effective throughput).
- Primary endpoint S: mean of three runs per condition, share of no-LLM minus share of GCC, three conditions equally weighted. Interval: each arm resampled within each condition, 10000 iterations, seed 20261003, 90% interval.
- Decision:
  - holds: lower bound greater than −0.10, and safety line not triggered;
  - direction only: S greater than −0.10, but lower bound not greater than −0.10;
  - does not hold: S not greater than −0.10, or safety line triggered.
- Safety line: in any condition the mean share of no-LLM exceeds GCC by more than 0.15, or in some condition all three no-LLM runs are invalid.
- Decision script: `scripts/alphartc/deploy/compete_flow_nl_eval_v1.py`.

## 5. Predictions unfavorable to us (written before the run)

1. **No-LLM overestimation is more severe.** Offline macro overestimation rate: 0.84 to 0.90 for the no-LLM arm over three seeds, 0.46 for the one-token LLM variant. In closed loop it more often meets the congestion criterion and hands control to shadow GCC. Expected:
   - freezes per minute more than GCC, and possibly more than the with-LLM arm;
   - D of claim one between 0 and +4, not reaching superiority.
2. **Claim two likely holds, but the reading may be negative.** The quality of both arms is mainly determined by the probing envelope, so D2 is expected within ±3, and the point estimate may be negative.
3. **Low bandwidth may be worse.** Offline Low BW MSE is 1.07 to 1.21 without the LLM and 1.00 with it; the hd_c1 (1 Mbit/s) cell may be the worst.
4. **The share against competing flows should stay close to GCC's.** After congestion v6 outputs shadow GCC, so S is expected between −0.06 and +0.02. More severe overestimation may make the share against TCP slightly higher, but does not trigger the 0.15 safety line.

