<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Real telemetry end to end (realtel-e2e-v1)

## Apparatus

**Environment:** a loopback interface inside a user and network namespace (unshare -rn), without root privileges on the host. netem sets a delay of 10 ms and packet loss at three levels, 0%, 2% and 5%, two runs per level. tcpdump with -Z root captures the packets; the smoke test has already verified that capture works.

**Four sources, real software:**

| Source | Real software | Telemetry acquisition |
|---|---|---|
| W3C webrtc-stats | headless Chrome 154, two RTCPeerConnection loopback calls on the same page, 640×480, 40 seconds | receiver getStats every 100 ms |
| iperf3 UDP | source-compiled iperf3 3.19.1, 1 Mbit/s, 30 seconds | server --json, one interval every 1 second |
| Linux tcp_info | our own TCP sender/receiver program, constant-rate sending at about 1.5 Mbit/s, 30 seconds | receiver reads getsockopt(TCP_INFO) every 100 ms. In the namespace the loopback MTU is set to 1500 and tso, gso and gro are disabled, so that packet capture sees the real on-wire segmentation |
| RFC 3550 | GStreamer rtpbin sends VP8, 60 seconds | RTCP receiver reports sent by the receiver, parsing the raw 8-bit fraction lost value from packet capture |

## Only same-quantity features are compared

According to the ground truth of realtel-adapter-v1, there are 8 features in total:

| Source | Features |
|---|---|
| W3C | 1 packet count, 2 byte count |
| iperf3 | 0 rate, 2 byte count, 10 loss rate |
| tcp_info | 1 packet count, 2 byte count |
| RFC 3550 | 10 loss rate |

Each run has one cell per feature, 48 cells in total.

## Ground truth (all from packet capture, defined before running)

**Comparison window:**
- W3C and tcp_info: a pair of telemetry readings is taken every 1 second; the ground-truth interval runs between the times of the two readings. W3C uses the getStats timestamp, tcp_info uses the read time.
- iperf3: the server intervals are used, starting from the arrival time of the first UDP data packet in the capture.
- RFC 3550: bounded by the extended highest sequence number in two adjacent receiver reports.

**Ground truth for each source:**
- **W3C:**
  - Packet count is all RTP packets received for the video stream's media SSRC and RTX SSRC; under our interface convention all received packets count.
  - Byte count is the UDP payload of these packets minus the RTP header (12 bytes, CSRC, extension header) and minus the 10-byte SRTP authentication.
  - Report only: counting only the media SSRC, and counting the authentication as 16 bytes.
- **iperf3:**
  - Byte count is UDP payload bytes; rate is byte count times 8 divided by interval length.
  - Loss rate is computed from the sequence numbers in the payload, that is, (expected packets in the interval minus received packets) divided by expected packets.
- **tcp_info:**
  - Packet count is segments sent to the receiver with payload greater than 0;
  - Byte count is in-order received bytes, that is, the advance of the maximum contiguous sequence number.
- **RFC 3550:**
  - Loss rate is (expected minus received) divided by expected, computed over the sequence-number interval between two reports.
  - If the interval between two adjacent reports exceeds 1.5 times the median interval, it is skipped, because the report in between was lost in netem.

**Conditions for a unit to be judged correct:**
- Counts, bytes, rate: median per-window relative error no more than 5%;
- Loss rate: median per-window absolute error no more than 0.01.

## Methods

**LLM:** the adapter written by DeepSeek for the first field order of realtel-adapter-v1, taking only fields, differencing, and coefficients.

**Controls:** the seven methods of realtel-baseline-strength-v1, namely NAME, TFIDF, Coma, Cupid, Similarity Flooding, bge-large, all-mpnet. Each uses the fields selected with its threshold from the development sources, together with v1's generic unit and differencing rules.

**Output rules:**
- If a feature is answered as missing, or is mapped to another field, the unit is counted wrong.
- Non-differenced fields take the reading at the end of the window times the coefficient; differenced fields take the difference of the two readings times the coefficient.
- iperf3 interval fields directly take the value of that interval.
- RFC report fields take the value of that report.

**Report only:** the adapters of open-source R1 distilled 32B and 14B.

## Criteria (confirmatory tier template)

- **Primary endpoint:** proportion of cells judged correct.
- **Δ:** LLM minus the best of the seven controls, with the best chosen post hoc, compared only on the average.
- **Interval:** block resampling by run 5000 times, 90% interval, 24 runs total across the four sources.

| Conclusion | Condition |
|---|---|
| holds | lower bound greater than 0 and Δ ≥ 0.15 |
| direction only | Δ > 0 |
| does not hold | Δ ≤ 0, or safety line breached |

**Safety line:** no unit of the LLM has a median per-window relative error exceeding 50%, and for loss-rate units an absolute error exceeding 0.1.

## Unfavorable prediction
The implementation may not match the specification, for example in how Chrome counts packets (including retransmissions and probing) and how tcp_info counts segments on the local machine. In that case the LLM adapter will also be wrong.
Several of the comparison methods may choose correctly on the simple fields of iperf3 and tcp_info, so Δ may be less than 0.15.
RFC has only one feature and about ten reports per run, so readings are few.

