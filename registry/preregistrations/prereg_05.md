<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: 720p closed loop on unused real cellular traces (drafted 2026-10-05 around 17:30 Beijing time, fixed before running)

## Design

- **Traces.** scripts/alphartc/deploy/make_hd720_real8_profiles_v1.py, rule hd720_real8_v1, seed 20261005, rule written before execution.
  - Corpus: UCC 4G and Chorus traces in data/llm_kp/corpus_v1.jsonl.
  - Exclusion: traces used at any tier in the repository or shared directory, including the traces containing hd_r1 and hd_r2.
  - Windowing: 120-second windows, at least 108 valid seconds.
  - Sampling: alternate between mean [1200, 2000) and [2000, 3000], drawing 4 from each, at most one window per trace.
  - Link: 50 ms delay, no random packet loss; queue length in packets computed from the 95th-percentile capacity times 250 ms.
  - Drawn windows: 6 UCC 4G stationary, 1 Chorus driving and 1 Chorus high-speed rail; mean 1.5 to 2.9 Mbit/s. Sources, start points, and hashes in profiles/hd720_real8/provenance.json.
- **Cells.** 8 windows × Johnny and FourPeople, 16 cells total.
- **Arms.** Two arms, 3 runs per arm per cell, interleaved round-robin within the same batch, 96 runs total; run script v20, scheduler v2, two container pairs in parallel.
  - GCC every 200 ms (gcc_pt125_c200).
  - Deployed system: C-H plus 5 kbps floor plus probing envelope v6 (arm_ch_x; module cec41ba6, weights 954c68d2).
- **Primary endpoint D_T.** Per-cell mean VMAF difference of C-H minus GCC, 16 cells equally weighted.
- **Decision.** Identical to hd720-closedloop-ch-v1, decided by hd720_ch_eval_v1.judge.
  - Interval: stratified resampling by cell 10000 times, seed 20261003, 90% interval.
  - Holds: lower bound greater than −6, and safety line not triggered.
  - Direction only: D_T greater than −6, but lower bound not greater than −6.
  - Does not hold: D_T not greater than −6, or safety line triggered.
  - Safety line: any cell lower by more than 10 points, or all three C-H runs invalid in some cell.
  - Boundary: if all GCC runs of a cell are invalid, that cell is dropped; if fewer than 6 usable cells, judge as inconclusive.
  - Superiority (lower bound greater than 0 and D_T not less than 6) is reported but not judged.
- **Validity.** Use hd720_run_metrics_v1.run_metrics and code_audit, with an additional v6 check for the C-H arm. Invalid runs are recorded, not deleted.
- **Script.** scripts/alphartc/deploy/hd720_realtrace_v1.py, selftest passed.

## Predictions unfavorable to us

1. **Real traces fluctuate more, so envelope rewriting will be more frequent.** On the two traces in the main batch, C-H's lead is smaller than on constant-capacity conditions, and in the echo-attribution batch hd_r1 FourPeople also trails echo by 8 points. Some window may be more than 10 points below GCC and trigger the safety line.
2. **6 windows come from UCC 4G stationary scenarios, with small fluctuation.** If the conclusion holds, it still cannot generalize to high-speed mobility; only 2 windows (driving, high-speed rail) are highly dynamic.

