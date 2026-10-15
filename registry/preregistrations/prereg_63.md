<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Learned baselines under high bandwidth (hd720-hb-learned-env-v1, hd720-hb-learned-alone-v1, 2026-10-07)

## Design
- Sender and conditions same as hd720-highbw-ch-v1: patched 720p cap 20 Mbit/s; hb_c3, hb_c6, hb_c10, hb_c15, hb_t1, hb_t2 × Johnny, FourPeople, 12 cells; source caps Johnny 12124, FourPeople 16058 kbit/s.
- Four arms: ch (deployed C-H, collector v6, 5 kbps floor, probing envelope v6), scr (Schaferct-R, same ONNX as Table I, same collector, floor, probing envelope v6), ch0 and scr0 (no probing envelope, floor only).
- 2 runs per arm per cell, interleaved in rotation, 96 runs total, on a single container pair, run script v24.
- Validity: the two arms with the probing envelope use the v6 check, and the two without it use the check for envelope 0 (lesson from hd720-learned-alone-v1); the rest is the same as in the 720p batches.

## Criteria (fixed before running)
- Claim one hd720-hb-learned-env-v1: D_E = per-cell mean VMAF difference of ch minus scr, 12 cells equally weighted; hd720_ch_eval_v1.judge: non-inferiority bound 6 VMAF; holds if the interval lower bound is greater than -6; direction only if D_E is greater than -6 but the lower bound is not; otherwise does not hold; safety line: any cell more than 10 points lower, or all ch runs of a cell invalid; fewer than 6 usable cells: inconclusive; superiority (lower bound greater than 0 and D_E not less than 6) reported but not judged.
- Claim two hd720-hb-learned-alone-v1: D_A = ch0 minus scr0, same resampling; holds: interval lower bound greater than 0 and D_A not less than 6 VMAF (the paper's superiority definition), and safety line not triggered; direction only: D_A greater than 0 but not reaching holds; does not hold: D_A not greater than 0 or safety line triggered (some cell lower by more than 10 points or all ch0 runs of a cell invalid); fewer than 6 usable cells judged inconclusive.
- Report only: per-arm VMAF, SSIM, freezes, packet loss, latency score, video rate, probing envelope rewrite share, per-condition VMAF.

## Predictions unfavorable to us
- With the probing envelope, the envelope may also rewrite most decisions at high bandwidth, so the two tie and superiority is not reached.
- Without the probing envelope, our overestimation is heaviest in the Fluctuating class (offline e+ 1.34), so C-H may be worse in the two 4G windows; at the constant high-bandwidth tiers Schaferct-R underestimates slightly more, and the gap may be less than 6 VMAF.

