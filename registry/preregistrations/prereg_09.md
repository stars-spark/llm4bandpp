<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: High-bandwidth closed loop after removing the libwebrtc 720p bitrate ceiling (drafted 2026-10-05 around 20:40 Beijing time, fixed before running)

## Design

- **Conditions.** Rule hd720_hb_v1, seed 20261006, written first and then executed by make_hd720_hb_profiles_v1.py.
  - Constant 3, 6, 10, 15 Mbit/s, queue length is capacity times 250 ms, i.e. 79, 157, 261, 391 packets.
  - Two unused UCC 4G windows:
    - hb_t1: train, mean 6.6 Mbit/s, 95th percentile 15.0, 391 packets.
    - hb_t2: bus, mean 10.5 Mbit/s, 95th percentile 34.3, 895 packets.
  - Delay 50 ms, no random packet loss, 120 seconds each.
- **Sequences.** Johnny, FourPeople (same as hd720-closedloop-ch-v1). Source ceilings use the calibration values: Johnny 12124, FourPeople 16058 kbit/s. 12 cells total.
- **Arms.** Both arms use the patched sender, 3 runs per arm per cell, interleaved round-robin, 72 runs total, on a single container pair.
  - GCC every 200 ms (gcc_pt125_c200).
  - Deployed system: C-H plus 5 kbps floor plus probing envelope v6.
- **Primary endpoint D_H.** Per cell, the mean VMAF difference of C-H minus GCC, with 12 cells equally weighted.
- **Decision.** Decided by hd720_ch_eval_v1.judge, identical to hd720-closedloop-ch-v1.
  - Interval: stratified resampling by cell 10000 times, seed 20261003, 90% interval.
  - Holds: lower bound greater than −6, and safety line not triggered.
  - Direction only: D_H greater than −6, but lower bound not greater than −6.
  - Does not hold: D_H not greater than −6, or safety line triggered.
  - Safety line: any cell lower by more than 10 points, or all three runs of some C-H cell invalid.
  - Fewer than 6 usable cells is judged inconclusive.
- **Report only.**
  - Superiority: lower bound greater than 0 and D_H not less than 6.
  - Per-condition VMAF, video rate, freezes, decoded frame rate, probing envelope rewrite.
- **Validity.**
  - Same as the 720p batch (run_metrics, code_audit, envelope v6 check).
  - One more check: the code hash of a valid run must contain the patched program; otherwise the patch did not take effect, which is treated as a tool problem, and no decision is made.
  - The decoded-frame-rate threshold specific to hd_c8 is not used; decoded frame rate is still reported.
- **Script.** scripts/alphartc/deploy/hd720_highbw_v1.py, selftest passed.

## Predictions unfavorable to us

1. **The probing envelope may slow ramp-up under high bandwidth.** In the clear state F multiplies by at most 1.08 per second, and if the C-H estimate is below F then F determines it. Under high bandwidth the estimator's offline error is also larger: the MSE of the High BW scenario is far larger than other scenarios, and it may underestimate or overestimate.
2. **The bus window fluctuates extremely strongly (95th percentile 34 Mbit/s).** When overestimated, the queue is very deep (895 packets), and queuing delay and freezes may be greater than GCC's.
3. **GCC ramps slowly (about 8% per second), and VMAF may be clearly lower at high capacities.** If C-H leads, the main reading will come from ramp-up speed, not from more accurate estimation.

