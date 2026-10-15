# -*- coding: utf-8 -*-
# Build field_transcription.json, counts.json and tables.json for the seven real telemetry specifications of the designer test (W3C webrtc-stats, Chrome webrtc-internals,
# RFC 3550 / 3611, QUIC qlog, iperf3, Linux tcp_info, GStreamer rtpmanager) from the table in this file; build_md.py then writes field_transcription.md.
# Version 1 of the transcriptions: the ground truth of realtel-adapter-v1 (the seven-specification rows of Table IV). data/real_telemetry_specs_v2/build.py builds
# the 12 held-out client stacks of realtel-scale-v1 and adds a check of every quote against the cached sources.
import json, os

OUT = os.path.dirname(os.path.abspath(__file__))

FEATS = [
    "receiving rate (bit/s)", "packets received", "bytes received", "queuing delay (ms)",
    "mean one-way delay (ms, clock offset)", "minimum one-way delay (ms)", "delay ratio (mean/minimum)",
    "mean minus minimum delay (ms)", "packet inter-arrival time (ms)", "jitter (ms)", "loss ratio (0-1)",
    "mean lost packets per loss event", "video packet share", "audio packet share", "probing packet share",
]

SAME, KIN, NONE = "same quantity", "different definition", "none"
NF = "not found"


def none(reason, url, quote="(none)"):
    return dict(name=NF, context="—", unit="—", cumulative="—", relation=NONE,
                reason=reason, quote=quote, url=url)


# ---------------------------------------------------------------- 1 W3C
W3C = "https://www.w3.org/TR/webrtc-stats/"
s1 = {
 0: dict(name="bytesReceived", context="RTCInboundRtpStreamStats",
         unit="bytes (based on \"Total number of bytes\"); the specification has no receive rate field",
         cumulative="cumulative", relation=KIN,
         reason="The specification deliberately does not provide a rate; the receive rate must be computed as the difference of bytesReceived from two getStats() calls divided by the difference of timestamp, then multiplied by 8. Although RTCIceCandidatePairStats.availableIncomingBitrate is in bit/s over a 1-second window, it is an available bandwidth estimate computed by congestion control, not a measured receive rate.",
         quote="\"For stats that are measured against time, such as byte counts, no separate counter is needed; one can instead divide by the difference in the timestamps.\" (§4.1 Guidelines for design of stats objects)",
         url=W3C + "#guidelines-for-design-of-stats-objects"),
 1: dict(name="packetsReceived", context="RTCReceivedRtpStreamStats (RTCInboundRtpStreamStats inherits; RTCTransportStats has a field of the same name, counting the entire transport)",
         unit="Packets (IDL type unsigned long long; inferred as a count from \"Total number of RTP packets\")",
         cumulative="cumulative", relation=SAME,
         reason="The difference between two readings is the number of RTP packets received within the window; counted by SSRC, including retransmissions.",
         quote="Total number of RTP packets received for this SSRC. This includes retransmissions.",
         url=W3C + "#dom-rtcreceivedrtpstreamstats-packetsreceived"),
 2: dict(name="bytesReceived", context="RTCInboundRtpStreamStats",
         unit="bytes (based on \"Total number of bytes\")", cumulative="cumulative", relation=SAME,
         reason="The difference between two readings is the number of bytes received within the window; only RTP payload is counted, RTP headers and padding are counted separately in headerBytesReceived, excluding IP/UDP headers.",
         quote="Total number of bytes received for this SSRC. This includes retransmissions. Calculated as defined in [RFC3550] section 6.4.1.",
         url=W3C + "#dom-rtcinboundrtpstreamstats-bytesreceived"),
 3: dict(name="jitterBufferDelay", context="RTCInboundRtpStreamStats",
         unit="seconds (original text \"in seconds\")", cumulative="cumulative (sum; the average must be divided by jitterBufferEmittedCount)",
         relation=NONE,
         reason="It measures the dwell time of samples or frames in the receiver-side jitter buffer, which is application-layer buffering, not queuing delay on the network path; the specification has no network queuing delay field. It is listed only because its name and unit are the most similar.",
         quote="It is the sum of the time, in seconds, each audio sample or a video frame takes from the time the first packet is received by the jitter buffer (ingest timestamp) to the time it exits the jitter buffer (emit timestamp).",
         url=W3C + "#dom-rtcinboundrtpstreamstats-jitterbufferdelay"),
 4: dict(name="roundTripTime", context="RTCRemoteInboundRtpStreamStats",
         unit="seconds (original text \"measured in seconds\")", cumulative="instantaneous (value computed from the most recent RTCP RR)",
         relation=KIN,
         reason="It is the round-trip time rather than the one-way delay, computed from the timestamps of RTCP RR, and does not include clock offset. The mean can be obtained by dividing totalRoundTripTime by roundTripTimeMeasurements; RTCIceCandidatePairStats.currentRoundTripTime is the STUN-based round-trip time.",
         quote="Estimated round trip time for this SSRC based on the RTCP timestamps in the RTCP Receiver Report (RR) and measured in seconds.",
         url=W3C + "#dom-rtcremoteinboundrtpstreamstats-roundtriptime"),
 5: none("The specification has no minimum delay or minimum round-trip time field; the only name containing Minimum is jitterBufferMinimumDelay, which belongs to the jitter buffer.", W3C),
 6: none("The specification has no delay ratio field.", W3C),
 7: none("The specification has no \"average delay minus minimum delay\" field.", W3C),
 8: dict(name="totalInterFrameDelay", context="RTCInboundRtpStreamStats (video only)",
         unit="seconds (original text \"in seconds\")", cumulative="cumulative (sum; combined with framesRendered to compute the average)",
         relation=KIN,
         reason="It is the sum of the intervals between consecutively rendered video frames, at the frame level and on the rendering side, not the arrival interval of network packets; the specification has no packet arrival interval field, and lastPacketReceivedTimestamp only records the time of the last packet.",
         quote="Sum of the interframe delays in seconds between consecutively rendered frames, recorded just after a frame has been rendered.",
         url=W3C + "#dom-rtcinboundrtpstreamstats-totalinterframedelay"),
 9: dict(name="jitter", context="RTCReceivedRtpStreamStats",
         unit="seconds (original text \"measured in seconds\")", cumulative="Instantaneous (current value of the RFC 3550 smoothed estimate)",
         relation=KIN,
         reason="Exponentially smoothed with a 1/16 gain per RFC 3550 §6.4.1, it is a continuously updated estimate, not a statistic over a short window.",
         quote="Packet Jitter measured in seconds for this SSRC. Calculated as defined in section 6.4.1. of [RFC3550].",
         url=W3C + "#dom-rtcreceivedrtpstreamstats-jitter"),
 10: dict(name="fractionLost", context="RTCRemoteInboundRtpStreamStats",
          unit="ratio (IDL type double; the specification does not state units, inferred as lost count/expected count from \"computed per RFC 3550 §6.4.1\")",
          cumulative="Interval (since the previous RTCP RR)", relation=SAME,
          reason="The quantity itself is the interval loss ratio. Note that it is attached to the remote-inbound object and is the loss of the local sending stream reported by the peer; the local receiving stream only has the cumulative count packetsLost.",
          quote="The fraction packet loss reported for this SSRC. Calculated as defined in [RFC3550] section 6.4.1 and Appendix A.3.",
          url=W3C + "#dom-rtcremoteinboundrtpstreamstats-fractionlost"),
 11: none("The specification has no packet loss event or packet loss burst length field (concealmentEvents is an audio concealment event).", W3C),
 12: dict(name="kind", context="RTCRtpStreamStats",
          unit="string, either \"audio\" or \"video\"", cumulative="not applicable (attribute label)", relation=NONE,
          reason="There is no proportion field, only the media type label of each stream; the proportion must be computed by grouping streams by kind and using each stream's packetsReceived.",
          quote="Either \"audio\" or \"video\". This MUST match the kind attribute of the related MediaStreamTrack.",
          url=W3C + "#dom-rtcrtpstreamstats-kind"),
 13: dict(name="kind", context="RTCRtpStreamStats",
          unit="string, either \"audio\" or \"video\"", cumulative="not applicable (attribute label)", relation=NONE,
          reason="Same as above; the specification has no audio packet ratio field.",
          quote="Either \"audio\" or \"video\". This MUST match the kind attribute of the related MediaStreamTrack.",
          url=W3C + "#dom-rtcrtpstreamstats-kind"),
 14: none("The specification has no concept of \"probing\". Padding bytes are counted only in headerBytesReceived, retransmissions in retransmittedPacketsReceived, and FEC in fecPacketsReceived; none of these are bandwidth probing.", W3C),
}

# ---------------------------------------------------------------- 2 webrtc-internals
CR = "https://github.com/chromium/chromium/blob/289a12e1f0beff39b6515449e10cb8f73e230d00/content/browser/webrtc/resources/stats_rates_calculator.js"
CRG = "https://github.com/chromium/chromium/blob/main/content/browser/webrtc/resources/stats_graph_helper.js"
s2 = {
 0: dict(name="[bytesReceived_in_bits/s]", context="inbound-rtp (same name on transport, candidate-pair)", derived=True,
         unit="bit/s (inferred from _in_bits and /s in the name; the code multiplies by 8 via kBytesToBits and rounds, then divides by the timestamp difference in seconds)",
         cumulative="Interval (between two adjacent getStats reports)", relation=SAME,
         reason="The byte difference between two adjacent reports multiplied by 8 and divided by the time difference is the average receive rate within the window; the window length is the report interval, and the source code comment calls it \"the last second\". Only payload bytes are counted; headers are counted separately as [headerBytesReceived_in_bits/s].",
         quote="\"in chrome://webrc-internals/ we also want graphs for the average rate over the last second\"; \"bytesReceived: new RateCalculator('bytesReceived', 'timestamp', CalculatorModifier.kBytesToBits)\"",
         url=CR + "#L447-L450"),
 1: dict(name="[packetsReceived/s]", context="inbound-rtp (same name on transport, candidate-pair)", derived=True,
         unit="packets/s (inferred from the /s in the name and the denominator being timestamp; kRounded is rounded)",
         cumulative="interval", relation=KIN,
         reason="It is packets per second rather than packets within the window; the two differ by a window-length factor. The raw cumulative value packetsReceived is also plotted under its original name.",
         quote="\"if (this.samplesMetric === 'timestamp') { return '[' + accumulativeMetric + '/s]'; }\"",
         url=CR + "#L122-L124"),
 2: dict(name="bytesReceived", context="inbound-rtp (raw quantity, not derived)", derived=False,
         unit="bytes", cumulative="cumulative", relation=SAME,
         reason="There is no such derived quantity as \"bytes within the window\"; the figure plots the raw getStats values (all numeric fields are plotted), and subtracting two readings gives the bytes within the window.",
         quote="\"Each graph represents a series of stats report for a PeerConnection, e.g. 1234-0-ssrc-abcd123-bytesSent is the graph for the series of bytesSent\"",
         url=CRG + "#L7-L9"),
 3: dict(name="[jitterBufferDelay/jitterBufferEmittedCount_in_ms]", context="inbound-rtp", derived=True,
         unit="ms (name suffix _in_ms; kMillisecondsFromSeconds multiplies by 1000)",
         cumulative="Interval (average of new buffer samples between two reports)", relation=NONE,
         reason="It is the interval average of the time spent in the jitter buffer, not the network queuing delay. It is listed only because its name and unit are the most similar.",
         quote="\"jitterBufferDelay: new RateCalculator('jitterBufferDelay', 'jitterBufferEmittedCount', CalculatorModifier.kMillisecondsFromSeconds)\"",
         url=CR + "#L516-L518"),
 4: dict(name="[totalRoundTripTime/roundTripTimeMeasurements]", context="remote-inbound-rtp (on candidate-pair it is [totalRoundTripTime/responsesReceived])", derived=True,
         unit="seconds (the name has no unit suffix; the modifier is the default kNone and the multiplier is 1, and the original field is measured in seconds)",
         cumulative="Interval (average of new RTT measurements between two reports)", relation=KIN,
         reason="interval average of round-trip time, not one-way delay.",
         quote="\"totalRoundTripTime: new RateCalculator('totalRoundTripTime', 'roundTripTimeMeasurements')\"",
         url=CR + "#L537-L538"),
 5: none("stats_rates_calculator.js has no minimum-delay derived quantities.", CR),
 6: none("There is no delay ratio derived quantity.", CR),
 7: none("There is no \"average minus minimum\" derived quantity.", CR),
 8: dict(name="[totalInterFrameDelay/framesDecoded_in_ms]", context="inbound-rtp (video only)", derived=True,
         unit="ms (name suffix _in_ms)", cumulative="interval", relation=KIN,
         reason="It is the interval average of the video frame interval (the denominator uses framesDecoded), not the packet arrival interval; the same group also has the frame interval standard deviation [interFrameDelayStDev_in_ms].",
         quote="\"totalInterFrameDelay: new RateCalculator('totalInterFrameDelay', 'framesDecoded', CalculatorModifier.kMillisecondsFromSeconds)\"",
         url=CR + "#L493-L495"),
 9: dict(name="jitter", context="inbound-rtp (raw quantity, not derived)", derived=False,
         unit="seconds", cumulative="Instantaneous (current value of the RFC 3550 smoothed estimate)", relation=KIN,
         reason="webrtc-internals does not derive jitter; the chart shows the raw getStats value. The literally closest derived quantity is [interFrameDelayStDev_in_ms], which is the standard deviation of rendered frame intervals.",
         quote="\"totalSquaredInterFrameDelay: new StandardDeviationCalculator('totalSquaredInterFrameDelay', 'totalInterFrameDelay', 'framesDecoded', 'interFrameDelay')\"; \"return '[' + this.label + 'StDev_in_ms]';\"",
         url=CR + "#L496-L498"),
 10: dict(name="[packetsReportedAsLost/s]", context="inbound-rtp and remote-inbound-rtp", derived=True,
          unit="packets/s", cumulative="interval", relation=KIN,
          reason="The number of packets reported as lost per second, not a ratio, and the original field exists only when RFC 8888 ccfb feedback is negotiated. The ratio form is only the raw fractionLost (remote-inbound-rtp), with no derivation performed.",
          quote="\"packetsReportedAsLost: new RateCalculator('packetsReportedAsLost', 'timestamp', CalculatorModifier.kRounded)\"",
          url=CR + "#L469-L470"),
 11: none("There is no loss-event derived quantity.", CR),
 12: none("There is no proportion derived quantity classified by audio and video; audio and video belong to different inbound-rtp objects (the kind field), so plot them separately.", CR),
 13: none("Same as above.", CR),
 14: none("There is no probing derived quantity.", CR),
}

# ---------------------------------------------------------------- 3 RFC 3550 / 3611
R50 = "https://www.rfc-editor.org/rfc/rfc3550.html"
R611 = "https://www.rfc-editor.org/rfc/rfc3611.html"
s3 = {
 0: dict(name="sender's octet count", context="RFC 3550 SR sender information block",
         unit="octets (payload bytes)", cumulative="cumulative", relation=KIN,
         reason="The receiver report block has no received bytes or received rate field. The closest is the sender cumulative payload bytes; RFC 3550 Section 6.4.1 says the average payload rate can be obtained by dividing the difference of two SRs by the NTP time difference.",
         quote="The total number of payload octets (i.e., not including header or padding) transmitted in RTP data packets by the sender since starting transmission up until the time this SR packet was generated.",
         url=R50 + "#section-6.4.1"),
 1: dict(name="received_interval", context="RFC 3550 Appendix A.3 example code variables (not packet fields)",
         unit="packet", cumulative="Interval (between two reports)", relation=SAME,
         reason="The receiver report block does not directly carry the number of packets received; the algorithm given by the RFC uses received_interval to denote the number of packets received between two reports. The message only has extended highest sequence number received and cumulative number of packets lost, which can be subtracted to derive it.",
         quote="received_interval = s->received - s->received_prior; (Appendix A.3); \"The number of packets received is the number of packets expected minus the number lost.\" (§6.4.1)",
         url=R50 + "#appendix-A.3"),
 2: dict(name="sender's octet count", context="RFC 3550 SR sender information block",
         unit="octets (payload bytes)", cumulative="cumulative", relation=KIN,
         reason="RTCP receiver reports have no received byte count; the closest is the sender cumulative payload bytes, in the opposite direction.",
         quote="The total number of payload octets (i.e., not including header or padding) transmitted in RTP data packets by the sender since starting transmission up until the time this SR packet was generated.",
         url=R50 + "#section-6.4.1"),
 3: dict(name="jitter buffer nominal delay (JB nominal)", context="RFC 3611 VoIP Metrics Report Block (BT=7)",
         unit="milliseconds", cumulative="instantaneous (original text \"most recently obtained values\")", relation=NONE,
         reason="It is the nominal delay of the jitter buffer, not the network queuing delay; neither RFC has a network queuing delay field. It is listed only because its name and unit are the most similar.",
         quote="This is the current nominal jitter buffer delay in milliseconds, which corresponds to the nominal jitter buffer delay for packets that arrive exactly on time.",
         url=R611 + "#section-4.7.7"),
 4: dict(name="round trip delay", context="RFC 3611 VoIP Metrics Report Block (BT=7)",
         unit="milliseconds", cumulative="instantaneous (most recently computed value)", relation=KIN,
         reason="round-trip time, not one-way delay; can be computed from RTCP LSR and DLSR (the DLSR unit in RFC 3550 is 1/65536 second). The RFC 3611 Packet Receipt Times block explicitly states that the difference between send and receive times cannot be expected to equal the one-way delay.",
         quote="The most recently calculated round trip time between RTP interfaces, expressed in milliseconds.",
         url=R611 + "#section-4.7.3"),
 5: none("There is no minimum delay field. The min_jitter in the Statistics Summary block is minimum jitter per erratum 2262, not minimum delay.",
         "https://www.rfc-editor.org/errata/eid2262",
         quote="(min_jitter after erratum 2262 revision) \"The minimum jitter measured for a pair of packets in the above sequence number interval.\""),
 6: none("There is no delay ratio field.", R611),
 7: none("There is no \"average minus minimum\" field.", R611),
 8: dict(name="Packet i receipt time", context="RFC 3611 Packet Receipt Times Report Block (BT=3)",
         unit="the same unit as the RTP packet timestamp", cumulative="Per packet", relation=KIN,
         reason="It gives the arrival time of each sequence number; only subtracting adjacent ones yields the inter-arrival time; the block itself is not an interval statistic.",
         quote="The receipt time of the packet with sequence number i at the receiver. … Units and format are the same as for the timestamp in RTP data packets.",
         url=R611 + "#section-4.3"),
 9: dict(name="mean_jitter", context="RFC 3611 Statistics Summary Report Block (BT=6)",
         unit="RTP timestamp units (original text \"rounded to the nearest value expressible as an RTP timestamp\"; erratum 2262 writes \"measured in timestamp units\")",
         cumulative="Interval (sequence number interval from begin_seq to end_seq)", relation=SAME,
         reason="averaging the jitter over a sequence number interval is an interval statistic; the same block also has min_jitter, max_jitter and dev_jitter. The RFC 3550 interarrival jitter is a snapshot of a 1/16 gain smoothed estimate, different definition. Errata 2262 (Held for Document Update) changes the definition of this group of fields to reference the jitter of RFC 3550 section 6.4.1.",
         quote="The mean relative transit time between each two packet series in the above sequence number interval, rounded to the nearest value expressible as an RTP timestamp.",
         url=R611 + "#section-4.6"),
 10: dict(name="fraction lost", context="RFC 3550 receiver report block (SR/RR)",
          unit="8-bit fixed point, binary point at the leftmost position (equal to the integer part of the loss ratio times 256)",
          cumulative="Interval (since the previous SR or RR)", relation=SAME,
          reason="the definition is exactly the number of lost packets in the interval divided by the expected number of packets, differing only by the 1/256 fixed-point encoding.",
          quote="The fraction of RTP data packets from source SSRC_n lost since the previous SR or RR packet was sent, expressed as a fixed point number with the binary point at the left edge of the field.",
          url=R50 + "#section-6.4.1"),
 11: dict(name="run length", context="RFC 3611 Loss RLE Report Block Run Length Chunk (run type 0 indicates a consecutive loss segment)",
          unit="Packets (values 1 to 16,383)", cumulative="Per segment (one entry per consecutive segment)", relation=KIN,
          reason="Record the length of each consecutive loss segment per segment; the average within the window must be computed manually. 0 indicates the loss is inferred from the example in §4.1 (the bit corresponding to \"of which the 22nd and 24th have been lost\" is 0). The burst duration of the VoIP Metrics block is the average duration (in milliseconds) of burst segments defined by Gmin, a more distant definition.",
          quote="run type (R): 1 bit — Zero indicates a run of 0s. One indicates a run of 1s. run length: 14 bits — A value between 1 and 16,383.",
          url=R611 + "#section-4.1.1"),
 12: none("RTCP reports are counted separately by SSRC, with no media type proportion field; the payload type in the RTP header only identifies the payload format.", R50 + "#section-5.1",
          quote="(RTP header payload type) \"This field identifies the format of the RTP payload and determines its interpretation by the application.\""),
 13: none("Same as above.", R50 + "#section-5.1"),
 14: none("Neither RFC has the concept of a probing packet.", R611),
}

# ---------------------------------------------------------------- 4 qlog
QE = "https://datatracker.ietf.org/doc/html/draft-ietf-quic-qlog-quic-events-13"
QM = "https://datatracker.ietf.org/doc/html/draft-ietf-quic-qlog-main-schema-14"
s4 = {
 0: dict(name="length", context="the raw field of the quic:packet_received event (type RawInfo, defined in main-schema-14 §10)",
         unit="bytes (original text \"the full byte length of the entity\")", cumulative="Per event (one entry per packet)", relation=KIN,
         reason="qlog has no received rate field; one can only sum the raw.length of each packet in the window and divide by the window length. The pacing_rate of quic:recovery_metrics_updated has unit bit/s (comment \"in bits per second\"), but it is the sender's packet pacing, not the measured received rate.",
         quote="; the full byte length of the entity (e.g., packet or frame), including possible headers and trailers ? length: uint64",
         url=QM + "#section-10"),
 1: dict(name="quic:packet_received", context="event name (one record per QUIC packet received); there is also a count field of quic:udp_datagrams_received",
         unit="number of events", cumulative="per event", relation=KIN,
         reason="qlog is a per-packet event log with no counters; the number of packets in a window must be counted from events; one UDP datagram can merge multiple QUIC packets, and to count by UDP datagram use the count of udp_datagrams_received.",
         quote="The packet_received event indicates a QUIC-level packet was received.",
         url=QE + "#section-5.6"),
 2: dict(name="length", context="quic:packet_received → raw (RawInfo)",
         unit="bytes", cumulative="per event", relation=KIN,
         reason="Per-packet byte count; only the sum within the window is the received byte count; RawInfo separately has payload_length (excluding header and trailer).",
         quote="; the full byte length of the entity (e.g., packet or frame), including possible headers and trailers ? length: uint64",
         url=QM + "#section-10"),
 3: none("There is no queueing delay field.", QE + "#section-7.2"),
 4: dict(name="smoothed_rtt", context="quic:recovery_metrics_updated",
         unit="ms (CDDL comment \"all following rtt fields are expressed in ms\")", cumulative="Instantaneous (record an event when the value changes)", relation=KIN,
         reason="According to the comment, it corresponds to the smoothed round-trip time in RFC 9002 Appendix A.3; it is a sender-side estimate, not one-way delay; the same event also has latest_rtt.",
         quote="; Loss detection, see RFC 9002 Appendix A.3 ; all following rtt fields are expressed in ms ? min_rtt: float32 ? smoothed_rtt: float32",
         url=QE + "#section-7.2"),
 5: dict(name="min_rtt", context="quic:recovery_metrics_updated",
         unit="ms (same comment as above)", cumulative="Instantaneous (current value given by the event)", relation=KIN,
         reason="minimum round-trip time, not the minimum one-way delay.",
         quote="; all following rtt fields are expressed in ms ? min_rtt: float32",
         url=QE + "#section-7.2"),
 6: none("There is no delay ratio field.", QE),
 7: none("There is no \"average minus minimum\" field.", QE),
 8: dict(name="time", context="common fields of all qlog events", unit="Usually ms (main-schema §7.1)",
         cumulative="per event", relation=NONE,
         reason="qlog does not give arrival intervals; one can only subtract the time of adjacent quic:packet_received events.",
         quote="The time field is a float64 and it is typically used to represent a duration in milliseconds, with a fractional component to microsecond or nanosecond resolution.",
         url=QM + "#section-7.1"),
 9: dict(name="rtt_variance", context="quic:recovery_metrics_updated",
         unit="ms (same comment as above)", cumulative="instantaneous", relation=KIN,
         reason="fluctuation of round-trip time (the variable corresponding to RFC 9002 Appendix A.3 per the comment), not inter-packet delay variation.",
         quote="; all following rtt fields are expressed in ms … ? rtt_variance: float32",
         url=QE + "#section-7.2"),
 10: dict(name="quic:packet_lost", context="event name", unit="number of events", cumulative="per event", relation=KIN,
          reason="Recorded once when the sender's loss detection determines that a packet is lost; it is not a ratio, nor a receiver-side statistic.",
          quote="The packet_lost event is emitted when a packet is deemed lost by loss detection.",
          url=QE + "#section-7.4"),
 11: none("There is no loss event length field.", QE),
 12: none("QUIC events do not distinguish media type.", QE),
 13: none("Same as above.", QE),
 14: dict(name="cc_bandwidth_probe", context="one of the values of the trigger field of quic:packet_sent; the same event also has a boolean field is_mtu_probe_packet",
          unit="enumerated string (per-packet label)", cumulative="per event", relation=KIN,
          reason="The trigger reason the sender assigned to a packet, expressed as sent for bandwidth probing; the proportion must be computed per window. is_mtu_probe_packet marks path MTU probe packets.",
          quote="; needed for some CCs to figure out bandwidth allocations ; when there are no normal sends \"cc_bandwidth_probe\"",
          url=QE + "#section-5.5"),
}

# ---------------------------------------------------------------- 5 iperf3
IA = "https://github.com/esnet/iperf/blob/f9901828236c487fbe45807371866abeeb54a242/src/iperf_api.c"
IU = "https://github.com/esnet/iperf/blob/f9901828236c487fbe45807371866abeeb54a242/src/iperf_udp.c"
CTX5 = "intervals[].streams[] (receiver UDP) and intervals[].sum"
s5 = {
 0: dict(name="bits_per_second", context=CTX5,
         unit="bit/s (the name itself says so; the code divides the interval byte count by the interval duration and multiplies by 8)", cumulative="interval", relation=SAME,
         reason="Bytes received within the interval times 8 divided by the interval duration is the interval average receive rate.",
         quote="bandwidth = (double) irp->bytes_transferred / (double) irp->interval_duration; …\"bits_per_second: %f\" … bandwidth * 8",
         url=IA + "#L4881-L4883"),
 1: dict(name="packets", context=CTX5, unit="packet", cumulative="interval", relation=KIN,
         reason="The receiver packets is the increment of the highest sequence number within the interval, that is, the expected packet count, including lost packets; actually received = packets - lost_packets.",
         quote="\"sp->packet_count is the highest sequence number seen so far\" (iperf_udp.c comment); temp.interval_packet_count = sp->packet_count - irp->packet_count; (iperf_api.c line 3956)",
         url=IU + "#L170-L175"),
 2: dict(name="bytes", context=CTX5, unit="bytes (the name carries no unit; inferred from the code bytes_transferred)",
         cumulative="interval", relation=SAME,
         reason="UDP payload bytes received by recv within the interval (the receiver takes bytes_received_this_interval).",
         quote="sp->result->bytes_received_this_interval += r; (iperf_udp.c); temp.bytes_transferred = sp->sender ? rp->bytes_sent_this_interval : rp->bytes_received_this_interval; (iperf_api.c)",
         url=IU + "#L124"),
 3: none("The UDP test JSON has no queueing delay field.", IA + "#L4926"),
 4: none("JSON does not output one-way delay. In the code, transit = arrival time - in-packet send time (that is, one-way delay including clock offset) is used only to compute jitter and is not written into JSON.", IU + "#L221-L223",
         quote="iperf_time_diff(&arrival_time, &sent_time, &temp_time); transit = iperf_time_in_secs(&temp_time);"),
 5: none("The UDP output has no minimum delay field.", IA + "#L4926"),
 6: none("There is no delay ratio field.", IA + "#L4926"),
 7: none("There is no \"average minus minimum\" field.", IA + "#L4926"),
 8: none("There is no packet inter-arrival field.", IA + "#L4926"),
 9: dict(name="jitter_ms", context=CTX5,
         unit="ms (the name itself says so; the code multiplies seconds by 1000)",
         cumulative="instantaneous (snapshot of the smoothed estimate at the end of the interval; in sum, the average of the per-flow jitter)", relation=KIN,
         reason="Smoothed with a 1/16 gain per RFC 1889, it is a continuously updated estimate, not a statistic within an interval.",
         quote="\"This computation is based on RFC 1889 (specifically sections 6.3.1 and A.8).\"; sp->jitter += (d - sp->jitter) / 16.0;",
         url=IU + "#L210-L232"),
 10: dict(name="lost_percent", context=CTX5,
          unit="Percentage (0-100; code multiplies by 100.0)", cumulative="interval", relation=SAME,
          reason="Interval lost packet count divided by interval expected packet count times 100, differing only by the percentage conversion.",
          quote="lost_percent = 100.0 * irp->interval_cnt_error / irp->interval_packet_count;",
          url=IA + "#L4920"),
 11: none("Only the number of lost packets in the interval, lost_packets, no count of loss events.", IA + "#L4926"),
 12: none("iperf3 does not distinguish media type.", IA + "#L4926"),
 13: none("Same as above.", IA + "#L4926"),
 14: none("There is no probing packet field.", IA + "#L4926"),
}

# ---------------------------------------------------------------- 6 tcp_info / ss
LH = "https://github.com/torvalds/linux/blob/4fa4ac5e584841c0f9b01c2f7dd0c2e3caa8bca0/include/uapi/linux/tcp.h"
LC = "https://github.com/torvalds/linux/blob/125755776bc6d4dd53eaf551c87e3d460625d638/net/ipv4/tcp.c"
SS8 = "https://git.kernel.org/pub/scm/network/iproute2/iproute2.git/tree/man/man8/ss.8"
SSC = "https://git.kernel.org/pub/scm/network/iproute2/iproute2.git/tree/misc/ss.c"
SYS = "https://github.com/torvalds/linux/blob/master/Documentation/networking/ip-sysctl.rst"
s6 = {
 0: dict(name="tcpi_delivery_rate", ss_name="delivery_rate", ss_unit="bps (the code multiplies by 8, the output has a bps suffix)",
         context="struct tcp_info",
         unit="bytes/s (unit not stated in the header; inferred from tcp_compute_delivery_rate: delivered packets x mss_cache x USEC_PER_SEC / rate_interval_us)",
         cumulative="instantaneous (most recent rate sample)", relation=KIN,
         reason="It is the delivery rate measured by the sender from ACKs, not the receive rate measured by the receiver.",
         quote="rate64 = (u64)rate * tp->mss_cache * USEC_PER_SEC; (tcp.c); out(\" delivery_rate %sbps\", sprint_bw(b1, s->delivery_rate)); (ss.c)",
         url=LC + "#L388-L399"),
 1: dict(name="tcpi_data_segs_in", ss_name="data_segs_in", ss_unit="segments (count)",
         context="struct tcp_info", unit="segments (count; include/linux/tcp.h comment \"total number of data segments in.\")",
         cumulative="cumulative", relation=SAME,
         reason="The difference between two readings is the number of data segments received within the window; there is also tcpi_segs_in (ss: segs_in), commented as \"total number of segments in.\", counting all segments.",
         quote="__u32 tcpi_data_segs_in; /* RFC4898 tcpEStatsDataSegsIn */",
         url=LH + "#L298"),
 2: dict(name="tcpi_bytes_received", ss_name="bytes_received", ss_unit="bytes (manual: \"bytes received\")",
         context="struct tcp_info", unit="bytes (based on the RFC4898 name HCThruOctetsReceived and the include/linux/tcp.h comment)",
         cumulative="cumulative", relation=SAME,
         reason="The difference between two readings is the number of bytes received within the window. The comment says sum(delta(rcv_nxt)), that is, accumulated by the forward movement of the receive sequence number, from which it is inferred that only in-order newly arrived payload bytes are counted, excluding duplicate data and headers.",
         quote="__u64 tcpi_bytes_received; /* RFC4898 tcpEStatsAppHCThruOctetsReceived */; include/linux/tcp.h: \"sum(delta(rcv_nxt)), or how many bytes were acked.\"",
         url=LH + "#L292"),
 3: none("There is no queueing delay field.", LH + "#L247"),
 4: dict(name="tcpi_rtt", ss_name="rtt", ss_unit="milliseconds (manual: \"their units are millisecond\"; output format rtt:<rtt>/<rttvar>)",
         context="struct tcp_info",
         unit="microseconds (not stated in the header; inferred from tcpi_rtt = srtt_us >> 3, srtt_us commented \"smoothed round trip time << 3 in usecs\")",
         cumulative="instantaneous (current value of the smoothed RTT)", relation=KIN,
         reason="Sender smoothed round-trip time, not one-way delay; the receiver has a separate tcpi_rcv_rtt (ss: rcv_rtt).",
         quote="info->tcpi_rtt = tp->srtt_us >> 3; (tcp.c); \"rtt is the average round trip time, rttvar is the mean deviation of rtt, their units are millisecond\" (ss.8)",
         url=LC + "#L4296"),
 5: dict(name="tcpi_min_rtt", ss_name="minrtt", ss_unit="millisecond (not listed in the manual; the code is tcpi_min_rtt / 1000)",
         context="struct tcp_info",
         unit="microseconds (not stated in the header; inferred from the minimum filter updated with rtt_us returned by tcp_min_rtt())",
         cumulative="instantaneous (current value of the window minimum filter, window length sysctl tcp_min_rtt_wlen, default 300 seconds)", relation=KIN,
         reason="minimum round-trip time, not the minimum one-way delay; moreover it is taken from a 300-second window, not a short-window statistic.",
         quote="\"The window length of the windowed min filter to track the minimum RTT.\" ... \"Default: 300\" (ip-sysctl.rst, tcp_min_rtt_wlen)",
         url=SYS),
 6: none("There is no delay ratio field.", LH + "#L247"),
 7: none("There is no \"average minus minimum\" field.", LH + "#L247"),
 8: dict(name="tcpi_last_data_recv", ss_name="lastrcv", ss_unit="milliseconds (manual: \"the unit is millisecond\")",
         context="struct tcp_info", unit="millisecond (tcp_get_info converts using jiffies_to_msecs)",
         cumulative="instantaneous", relation=NONE,
         reason="It is the time elapsed since the arrival of the previous data packet, not a statistic of the arrival interval between adjacent packets.",
         quote="\"how long it has been since the last packet received, the unit is millisecond\" (ss.8)",
         url=SS8 + "#n261"),
 9: dict(name="tcpi_rttvar", ss_name="rtt (the rttvar after the slash in rtt:<rtt>/<rttvar>)", ss_unit="millisecond",
         context="struct tcp_info",
         unit="microseconds (inferred from tcpi_rttvar = mdev_us >> 2, mdev_us commented \"mean deviation of RTT, scaled by 4 (<< 2) in usecs\")",
         cumulative="instantaneous", relation=KIN,
         reason="The mean deviation of RTT is the fluctuation of round-trip time, not inter-packet delay jitter.",
         quote="info->tcpi_rttvar = tp->mdev_us >> 2;",
         url=LC + "#L4297"),
 10: dict(name="tcpi_lost", ss_name="lost", ss_unit="packet",
          context="struct tcp_info", unit="Packets (taken from tp->lost_out, comment \"Lost packets\")",
          cumulative="instantaneous (current value, not cumulative)", relation=KIN,
          reason="The number of packets the sender currently marks as lost, not a ratio; for cumulative retransmissions see tcpi_total_retrans.",
          quote="info->tcpi_lost = tp->lost_out;",
          url=LC + "#L4286"),
 11: none("There is no loss event length field.", LH + "#L247"),
 12: none("TCP does not distinguish media type.", LH + "#L247"),
 13: none("Same as above.", LH + "#L247"),
 14: dict(name="tcpi_probes", ss_name="(ss -i does not output)", ss_unit="—",
          context="struct tcp_info", unit="count (number of unanswered probes)", cumulative="instantaneous", relation=NONE,
          reason="Taken from icsk_probes_out, annotated as unanswered zero-window probes, not bandwidth probes. It is listed only because its name looks the most similar.",
          quote="info->tcpi_probes = icsk->icsk_probes_out; (tcp.c); \"@icsk_probes_out: unanswered 0 window probes\" (inet_connection_sock.h)",
          url=LC + "#L4253"),
}

# ---------------------------------------------------------------- 7 GStreamer
GS = "https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/e27d76382a679c6f338b579e8f01a508ec9b551c/subprojects/gst-plugins-good/gst/rtpmanager/rtpsource.c"
GJ = "https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/8d279edd98f4f6ffc08e6bc86516dfd01edf7210/subprojects/gst-plugins-good/gst/rtpmanager/gstrtpjitterbuffer.c"
GSS = "https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/82a68b2f7919125f1f393f0846dea45bbe254b0d/subprojects/gst-plugins-good/gst/rtpmanager/gstrtpsession.c"
GST = "https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/5ff769d731e97fa05796f3ea32e039d267ad4f2f/subprojects/gst-plugins-good/gst/rtpmanager/rtpstats.c"
s7 = {
 0: dict(name="bitrate-recv", context="the twcc-stats property of the rtpsession element (structure name RTPTWCCStats)",
         unit="bit/s (the documentation does not state the unit; the code multiplies packet length by 8 and accumulates, then converts to per second using the remote duration)",
         cumulative="Interval (300 ms sliding window)", relation=SAME,
         reason="Use the receiver arrival time in the TWCC feedback, count the number of bits received within a 300 ms window divided by the window length; computed at the sender from the feedback. RTPSource's bitrate (\"bitrate in bits per second\") is a receiver-side measurement, but takes an interval of no less than 2 seconds and applies exponential smoothing at 3:1, which is a different definition.",
         quote="\"bitrate-recv\" G_TYPE_UINT The estimated bitrate for the receiver. (gstrtpsession.c); stats->window_size = 300 * GST_MSECOND; (rtpstats.c)",
         url=GSS + "#L787"),
 1: dict(name="packets-received", context="RTPSource stats property (application/x-rtp-source-stats)",
         unit="Packets (original text \"total number of packets received\")", cumulative="cumulative", relation=SAME,
         reason="The difference between two readings is the number of packets received within the window; counted by SSRC.",
         quote="\"packets-received\" G_TYPE_UINT64 total number of packets received",
         url=GS + "#L176"),
 2: dict(name="bytes-received", context="RTPSource stats property (application/x-rtp-source-stats)",
         unit="bytes, including lower level protocol headers (original text \"including lower level headers overhead\")", cumulative="cumulative", relation=SAME,
         reason="The difference between two readings is the number of bytes received within the window; the payload-only one is octets-received.",
         quote="\"bytes-received\" G_TYPE_UINT64 total number of bytes received including lower level headers overhead",
         url=GS + "#L177"),
 3: none("None of the statistics structures of rtpjitterbuffer, RTPSource, or rtpsession has a network queuing delay field.", GJ + "#L936-L947"),
 4: dict(name="rb-round-trip", context="RTPSource stats property (internal source, taken from received RR)",
         unit="seconds, NTP short format 16.16 fixed point (original text \"seconds in NTP Short Format, 16.16 fixed point\")",
         cumulative="instantaneous (computed from the most recent RB)", relation=KIN,
         reason="round-trip time, not one-way delay; rtx-rtt in rtpjitterbuffer is the average round-trip time per retransmission.",
         quote="\"rb-round-trip\" G_TYPE_UINT the round-trip time (seconds in NTP Short Format, 16.16 fixed point)",
         url=GS + "#L222"),
 5: none("There is no minimum delay field.", GS + "#L136-L246"),
 6: none("There is no delay ratio field.", GS + "#L136-L246"),
 7: none("There is no \"average minus minimum\" field.", GS + "#L136-L246"),
 8: dict(name="avg-delta-of-delta", context="the twcc-stats property of the rtpsession element",
         unit="nanoseconds (original text \"In nanoseconds\")", cumulative="Interval (sliding window average)", relation=KIN,
         reason="It is the average over the window of the difference in packet intervals between the sender and the receiver (delay gradient), not the arrival interval at the receiver itself; there is no arrival interval field in the statistics structure.",
         quote="\"avg-delta-of-delta\", G_TYPE_INT64 In nanoseconds, a moving window average of the difference in inter-packet spacing between sender and receiver.",
         url=GSS + "#L796-L798"),
 9: dict(name="avg-jitter", context="the stats property of rtpjitterbuffer (application/x-rtp-jitterbuffer-stats)",
         unit="nanoseconds (original text \"the average jitter in nanoseconds\")",
         cumulative="Instantaneous (current value of 1/16 gain exponential smoothing)", relation=KIN,
         reason="The name is average, but the code is the exponential smoothing avg = (diff + 15*avg) >> 4, not the within-window mean. The jitter of RTPSource is also RFC 3550 style smoothing, in clock rate units (\"in clock rate units\").",
         quote="#guint64 `avg-jitter`: the average jitter in nanoseconds.; priv->avg_jitter = (diff + (15 * priv->avg_jitter)) >> 4;",
         url=GJ + "#L942"),
 10: dict(name="packet-loss-pct", context="the twcc-stats property of the rtpsession element",
          unit="Percentage (name suffix -pct; code multiplies by 100)", cumulative="Interval (300 ms sliding window)", relation=SAME,
          reason="in-window (sent packets - received packets) / sent packets x 100; the documentation notes that out-of-order packets may be counted as lost. The receiver-side RR measure is RTPSource's sent-rb-fractionlost (8-bit fixed point).",
          quote="\"packet-loss-pct\" G_TYPE_DOUBLE Packetloss percentage, based on packets reported as lost from the receiver.",
          url=GSS + "#L790"),
 11: none("There is no loss event length field; rtpjitterbuffer only has the cumulative loss count num-lost.", GJ + "#L939"),
 12: none("The statistics structure does not distinguish media type.", GS + "#L136-L246"),
 13: none("Same as above.", GS + "#L136-L246"),
 14: none("There is no probing packet field.", GSS + "#L780-L800"),
}

SOURCES = [
 ("W3C webrtc-stats", s1),
 ("Chrome webrtc-internals", s2),
 ("RFC 3550 / RFC 3611", s3),
 ("QUIC qlog (draft-ietf-quic-qlog-quic-events-13)", s4),
 ("iperf3 JSON (UDP)", s5),
 ("Linux tcp_info / ss", s6),
 ("GStreamer rtpmanager", s7),
]

# --------------------------------------------------------------- JSON
out = {}
for key, d in SOURCES:
    assert sorted(d) == list(range(15)), key
    out[key] = {}
    for i in range(15):
        e = d[i]
        rec = {"name": e["name"], "unit": e["unit"], "cumulative": e["cumulative"],
               "relation": e["relation"], "quote": e["quote"], "url": e["url"],
               "context": e["context"], "reason": e["reason"]}
        for k in ("derived", "ss_name", "ss_unit"):
            if k in e:
                rec[k] = e[k]
        out[key][str(i)] = rec
with open(os.path.join(OUT, "field_transcription.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# --------------------------------------------------------------- counts
counts = {}
for key, d in SOURCES:
    c = {SAME: [], KIN: [], NONE: []}
    for i in range(15):
        c[d[i]["relation"]].append(i)
    counts[key] = c
with open(os.path.join(OUT, "counts.json"), "w", encoding="utf-8") as f:
    json.dump(counts, f, ensure_ascii=False, indent=1)

# --------------------------------------------------------------- markdown tables
def esc(s):
    s = str(s).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("*", "\\*").replace("__", "\\_\\_")
    return s

def table(key, d):
    six = key.startswith("Linux")
    two = key.startswith("Chrome")
    head = ["#", "our feature", "Real field name"]
    if six:
        head += ["ss output name", "ss unit"]
    if two:
        head += ["derived quantity"]
    head += ["containing structure/event", "unit", "cumulative/interval", "relation", "Reason", "original text quotation", "Link"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for i in range(15):
        e = d[i]
        nm = "`" + e["name"] + "`" if e["name"] != NF else NF
        row = [str(i), FEATS[i], nm]
        if six:
            ssn = e.get("ss_name", "—")
            row += [esc(ssn), esc(e.get("ss_unit", "—"))]
        if two:
            row += ["yes" if e.get("derived") else ("no (raw quantity)" if "derived" in e else "—")]
        row += [esc(e["context"]), esc(e["unit"]), esc(e["cumulative"]), e["relation"],
                esc(e["reason"]), esc(e["quote"]), "[link](" + e["url"] + ")"]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)

tables = {key: table(key, d) for key, d in SOURCES}
with open(os.path.join(OUT, "tables.json"), "w", encoding="utf-8") as f:
    json.dump(tables, f, ensure_ascii=False)
print(json.dumps({k: {r: v for r, v in c.items()} for k, c in counts.items()}, ensure_ascii=False, indent=1))
