<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: 720p closed loop and competing flow (2026-10-03)

Two confirmatory claims: hd720-closedloop-v1 (visual quality of the one-token LLM variant plus probing envelope versus GCC every 200 ms on 720p talking-head content, non-inferiority) and compete-flow-v1 (video share when sharing a bottleneck with one long-lived TCP CUBIC flow or one GCC video call, non-inferiority, plus a safety line against crowding out the competitor).

The open points of the protocol (not released) are fixed as below; the criteria are frozen before the run and will not change after it starts.

## Decisions on the points in Section 6 of the protocol

1. Accept the 2.5 Mbps ceiling, do not change the media stack; the estimator difference at the 4 to 8 Mbps conditions is still evaluated offline only.
2. Use only talking-head content: main batch Johnny, FourPeople; KristenAndSara as backup per the replacement rule in protocol 2.2; Mobcal, Parkrun only for ceiling calibration.
3. Capacity conditions C1, C2, C3, C8 plus two new trace windows R1, R2 (window selection rule hd720_real_v1, seed 20261003, rule written before execution).
4. Add back the echo-plus-probing-envelope arm (five arms).
5. The 720p primary endpoint uses non-inferiority (see below); superiority is reported but not judged.
6. A single bottleneck buffer size, 200 ms.
7. The competing flow continues to use sender egress shaping, consistent with all existing closed-loop conventions, reusing the main batch's no-competition baseline; TCP is added to the rate-limited class.
8. Disable sender container segmentation offload: first use a method that does not require host sudo (docker exec --privileged to change gso or tso inside the container network namespace); if that cannot be done, the batch stops. The setting is restored when the container restarts.
9. Scoring temporary files go in /path/to/storage.
10. The Xiph public raw sequences are downloaded by us, with upstream hashes recorded.
11. If the LLM arm is confirmed by the gate smoke test to have extra freezes due to synchronous inference, no asynchronous version is made in this batch.

## Common setup

Run script v12 (v11 plus the queue length in packets, a sender resolution log, a competitor switch, and ports 8000 and 8001 allowed; with the competitor off it must behave identically to v11, verified by calibration K5); container pairs p1 and p2 in parallel, one scoring worker; one-way delay 50 ms, no random loss, shaping 120 s; queue packet count = ceil(capacity × 250 ms ÷ 9600 bits).

3 runs per cell, arms rotated and interleaved within the same condition, same sequence, same repetition number. Run validity and condition audit per protocol 2.7, frozen and unchanged; runs that fail the gate are still recorded and not deleted.

Five arms: gcc_pt125_c200 (GCC every 200 ms), arm_llm4bandpp_x (one-token LLM variant plus probing envelope), arm_llm4band_conf_x (LLM4Band plus probing envelope), arm_schaferct_public_x (challenge baseline plus probing envelope), echo_x (echo plus probing envelope); collector v6, probing envelope v4, all deployed files, unchanged.

Sequence ceiling: the median video rate measured in ceiling calibration (fixed 10 Mbps estimate, 20 Mbps link, 2 runs per sequence), written into the results directory after calibration and before the main batch; the utility's R uses "the smaller of capacity and this ceiling" as the denominator.

## Claim one: hd720-closedloop-v1

- Unit: 6 conditions × 2 sequences = 12 cells.
- Primary endpoint: within each cell, the mean VMAF of three runs of the one-token LLM variant plus probing envelope minus that of three runs of GCC every 200 ms, equally weighted averaged over the 12 cells, denoted D.
- Interval: stratified by cell, resampling runs within cell, 10000 times, seed 20261003, 90% interval.
- Criterion (non-inferiority, bound 6 VMAF, i.e. the meaningful difference fixed before the main run): holds = the 90% interval lower bound of D is greater than −6 and the safety line is not triggered; direction only = D is greater than −6 but the lower bound is not greater than −6; does not hold = D is not greater than −6 or the safety line is triggered.
- Safety line: in any cell the mean VMAF of the one-token LLM variant is more than 10 points below GCC, or in some cell all three of its runs are invalid.
- Report only: whether D reaches superiority (lower bound greater than 0 and D not below 6); utility, SSIM, PSNR, the three freeze definitions, loss, queuing delay, probing envelope rewrite share and state proportions, decision interval, high-definition duration proportion, time to reach the ceiling; the differences of the LLM4Band, challenge baseline and echo arms versus GCC, computed the same way; the difference of echo versus the one-token LLM variant; per-condition breakdown; resources.

## Claim two: compete-flow-v1

- Conditions: T2 (2 Mbps, one TCP CUBIC, seconds 30 to 90), T3 (3 Mbps, same as above), G2 (2 Mbps, one GCC 720p call every 200 ms, starting at second 30 for 60 s); Johnny 720p 30 fps; competition window seconds 40 to 90.
- Share = video payload rate within the competition window ÷ (video payload rate + competitor effective throughput).
- Primary endpoint: mean of three runs per condition, share of the one-token LLM variant plus probing envelope minus share of GCC every 200 ms, equally weighted averaged over the three conditions, denoted S.
- Interval: same method as claim one, 90% interval.
- Criterion (non-inferiority, bound 0.10): holds = the lower bound of S is greater than −0.10 and the safety line is not triggered; direction only = S is greater than −0.10 but the lower bound is not greater than −0.10; does not hold = S is not greater than −0.10 or the safety line is triggered.
- Safety line (crowding out the competitor): any condition where the mean share of the one-token LLM variant exceeds GCC's mean share by more than 0.15, or any condition where all three of its runs are invalid.
- Report only: competitor throughput, Jain index, queuing delay and packet loss within the competition window, VMAF and freezes within the competition window and over the full run, recovery time, probing envelope state proportion, number of invalid runs, and all other arms.

## Predictions unfavorable to us

1. At 720p, the one-token LLM variant plus probing envelope will not outperform GCC (it tied at 320x240 earlier, with the gain attributed to the probing envelope).
2. The VMAF difference between echo plus probing envelope and the one-token LLM variant is within 3 points; the LLM executed at every step has no visible contribution in this batch.
3. At the 1 Mbps condition, the one-token LLM variant may lose to GCC (probing envelope ramps up quickly, 720p keyframes are large).
4. The LLM arm has more freezes than the lightweight arms, possibly due to synchronous inference on the testbed.
5. Against TCP CUBIC, all arms' shares may be below 0.3; against GCC competing calls, the earlier arrival has the advantage, and our share may be significantly higher than the later arrival's.
6. If the Python version of GCC cannot ramp above 1 Mbps at 720p, our lead only indicates that this GCC reproduction is weak.

