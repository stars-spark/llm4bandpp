# -*- coding: utf-8 -*-
import json, os
OUT = os.path.dirname(os.path.abspath(__file__))
tables = json.load(open(os.path.join(OUT, "tables.json"), encoding="utf-8"))
counts = json.load(open(os.path.join(OUT, "counts.json"), encoding="utf-8"))

INTRO = {
"W3C webrtc-stats": """**Source text captured**: W3C Candidate Recommendation Draft, 2025-09-25 (<https://www.w3.org/TR/webrtc-stats/>); the editor's draft <https://w3c.github.io/webrtc-stats/> (most recent repository commit 2026-10-02) was also captured for comparison. The five dictionaries used in the table below, RTCReceivedRtpStreamStats, RTCInboundRtpStreamStats, RTCRemoteInboundRtpStreamStats, RTCTransportStats, RTCIceCandidatePairStats, have identical members and definitions in both versions.""",
"Chrome webrtc-internals": """**Source text captured**: Chromium source code `content/browser/webrtc/resources/stats_rates_calculator.js` (most recent commit of that file 289a12e, 2026-07-21) and `stats_graph_helper.js` in the same directory. No official Google webrtc-internals naming document was found; everything below is based on the source code.

Note: webrtc-internals plots every numeric field returned by getStats under its original name, then appends derived quantities named with square brackets on the same object. In the table below, the \"derived quantity\" column marks \"yes\" for square-bracket derived quantities and \"no\" for getStats raw fields plotted directly on the graph (the raw field is listed only when the feature has no derived quantity).""",
"RFC 3550 / RFC 3611": """**Source text captured**: RFC 3550 (2003-07) <https://www.rfc-editor.org/rfc/rfc3550.txt>; RFC 3611 (2003-11) <https://www.rfc-editor.org/rfc/rfc3611.txt>; RFC 3611 errata page <https://www.rfc-editor.org/errata/rfc3611> (errata 2262 modified the definitions of the four jitter fields in the Statistics Summary block, status Held for Document Update).

Note: the \"field names\" of the RFC are the English phrases in the packet format diagrams and field descriptions, transcribed as is in the table (including spaces and parenthesized abbreviations). The `received_interval` used by feature 1 is a variable in the example code of RFC 3550 Appendix A.3, not a packet field, and this is noted in the table.""",
"QUIC qlog (draft-ietf-quic-qlog-quic-events-13)": """**Source text captured**: draft-ietf-quic-qlog-quic-events-13 (2026-07-06, current latest version on datatracker); RawInfo and time field definitions are in draft-ietf-quic-qlog-main-schema-14.

Note: the `metrics_updated` written in the task has been renamed in the new version. Original change record: \"Renamed recovery:metrics_updated to quic:recovery_metrics_updated\" (since -08 all events are merged into a single `quic` namespace). The table transcribes the names from -13.""",
"iperf3 JSON (UDP)": """**Source text captured**: esnet/iperf mainline `src/iperf_api.c` and `src/iperf_udp.c` (most recent commit f990182, 2026-09-29; version 3.22 released the same day). The official website <https://software.es.net/iperf/> has no per-field JSON description; the key names below are taken from the `iperf_json_printf` format strings that generate JSON in the source code.

The keys of `intervals[].streams[]` on the UDP receiver side are: `socket start end seconds bytes bits_per_second jitter_ms lost_packets packets lost_percent omitted sender`; `intervals[].sum` is the same but without `socket` (line 4226). `end.streams[].udp` additionally has `out_of_order` (line 4488).""",
"Linux tcp_info / ss": """**Source text captured**: Linux mainline `include/uapi/linux/tcp.h` (struct tcp_info, most recent commit 4fa4ac5, 2026-01-31), `tcp_get_info()` in `net/ipv4/tcp.c` (used to infer units), field comments in `include/linux/tcp.h` and `include/net/sock.h`, `Documentation/networking/ip-sysctl.rst`; `man/man8/ss.8` and `misc/ss.c` of iproute2 (mainline on git.kernel.org).

Note: the \"true field name\" in the table is the tcp_info member name; the other two columns are the name and unit printed by `ss -i`. The struct tcp_info header almost never writes units; wherever \"inferred\" is written, the basis is in the unit column.""",
"GStreamer rtpmanager": """**Source text captured**: in the GStreamer main repository, `rtpsource.c` under `subprojects/gst-plugins-good/gst/rtpmanager/` (documentation comment of RTPSource:stats and `rtp_source_create_stats`), `gstrtpjitterbuffer.c` (rtpjitterbuffer:stats), `rtpsession.c` and `gstrtpsession.c` (rtpsession:stats, rtpsession:twcc-stats), `rtpstats.c` (computation of TWCC statistics); and it was verified that the official documentation pages RTPSource.html, rtpjitterbuffer.html, rtpsession.html do contain these fields.

Note: the `stats` of rtpsession itself only has `rtx-drop-count`, `sent-nack-count`, `recv-nack-count`, `recv-rtx-req-count`, `sent-rtx-req-count`, `source-stats` (an array of RTPSource:stats); the quantities related to the 15 features are in `source-stats` and another property `twcc-stats`.""",
}

NAMING = {
"W3C webrtc-stats": """- **Case**: lower camel case. Original: \"The new members of the stats dictionary need to be named according to standard practice (camelCase)\". Names ending in `Id` are references to other stats objects, names ending in `Ids` are reference sequences; identifiers within the protocol instead end in `identifier` (such as `dataChannelIdentifier`).
- **Separator**: none, word splitting relies on case (`packetsReceived`, `jitterBufferEmittedCount`).
- **Time unit**: durations are always in seconds, written in the description and not in the name (`jitter`, `roundTripTime`, `totalRoundTripTime`, `jitterBufferDelay`, `totalInterFrameDelay` are all \"in seconds\"); instants use DOMHighResTimeStamp (`timestamp`, `lastPacketReceivedTimestamp`), with names ending in `Timestamp`. Rates are only the congestion control estimates `availableIncomingBitrate`/`availableOutgoingBitrate`, in bit/s, likewise written only in the description.
- **Units in names**: no.
- **Cumulative quantities**: the spec explicitly requires not giving averages, only \"sum + count\". Original: \"letting the implementation compute \\\"average\\\" rates is not a good idea … the recommended approach is to count the number of measurements of a value and sum the measurements\". There are three naming forms: past participle verb counts (`packetsReceived`, `bytesReceived`, `packetsLost`), `total` prefixed sums (`totalRoundTripTime`, `totalInterFrameDelay`, `totalDecodeTime`), and `Count`/`Measurements` suffixed counts (`nackCount`, `jitterBufferEmittedCount`, `roundTripTimeMeasurements`). Instantaneous quantities carry no prefix (`jitter`, `roundTripTime`, `fractionLost`).""",
"Chrome webrtc-internals": """- **Derived quantities are wrapped in square brackets**, raw fields are not bracketed and keep their original getStats names. Source comment example: \"[framesReceived/s] and [framesReceived-framesDecoded]\".
- **Rates**: when a cumulative quantity is differenced over time it is written `[original_name/s]` (`[packetsReceived/s]`); when the denominator is another counter it is written `[original_name/denominator_name]` (`[totalRoundTripTime/roundTripTimeMeasurements]`).
- **Units written into the name**: when bytes are converted to bits, `_in_bits` is appended to the original name (`[bytesReceived_in_bits/s]`); when seconds are converted to milliseconds, `_in_ms` is appended to the end of the whole name (`[jitterBufferDelay/jitterBufferEmittedCount_in_ms]`, `[totalInterFrameDelay/framesDecoded_in_ms]`); when no conversion is done no unit is added, so `[totalRoundTripTime/roundTripTimeMeasurements]` is still in seconds.
- **Other forms**: differences `[A-B-C]` (`[framesReceived-framesDecoded-framesDropped]`); standard deviation `[labelStDev_in_ms]` (`[interFrameDelayStDev_in_ms]`); ratios `[packetsReceivedWithCe/totalEct1Packets]`; special cases `[codec]`, `[Audio_Level_in_RMS]`, `[PSNR_y]`; instant fields keep their original name in brackets to indicate conversion to a readable date (`[lastPacketReceivedTimestamp]`).
- **Cumulative quantities**: raw cumulative fields are plotted under their original names, and derived quantities are all interval values between two adjacent reports, no longer cumulative values.""",
"RFC 3550 / RFC 3611": """- **Case and separator**: the VoIP Metrics block of RFC 3550 and RFC 3611 uses lowercase English phrases, space separated, with abbreviations in parentheses (`fraction lost`, `cumulative number of packets lost`, `interarrival jitter`, `extended highest sequence number received`, `delay since last SR (DLSR)`, `round trip delay`, `jitter buffer nominal delay (JB nominal)`); the RFC 3611 Statistics Summary block and sequence number fields use lowercase with underscores (`lost_packets`, `dup_packets`, `min_jitter`, `max_jitter`, `mean_jitter`, `dev_jitter`, `min_ttl_or_hl`, `begin_seq`, `end_seq`).
- **Statistic prefixes**: `min_`, `max_`, `mean_`, `dev_` (standard deviation).
- **Time unit**: not in the name, written in the description, and it differs per field: jitter and arrival instants use RTP timestamp units, DLSR/DLRR use 1/65536 seconds, and the delays and burst durations of the VoIP block use milliseconds.
- **Ratios**: 8 bit fixed point numbers, with the binary point at the far left (`fraction lost`, `loss rate`, `discard rate`, `burst density`, `gap density`).
- **Cumulative and interval**: distinguished by wording in the name or description. Cumulative quantities write `cumulative` in the name, or write \"since the beginning of reception\" in the description (the VoIP block `loss rate` is also since the beginning of reception, not reflected in the name); interval quantities write \"since the previous SR or RR packet was sent\" or are limited to the sequence number interval from `begin_seq` to `end_seq`.""",
"QUIC qlog (draft-ietf-quic-qlog-quic-events-13)": """- **Case and separator**: all lowercase, underscore separated (`smoothed_rtt`, `bytes_in_flight`, `is_mtu_probe_packet`). main-schema-14 §11.1: \"all qlog field names MUST be lowercase when serialized to JSON\".
- **Event names**: `namespace:event_type`, such as `quic:packet_received`, `quic:recovery_metrics_updated`, `quic:packet_lost`.
- **Time unit**: milliseconds. main-schema-14 changelog: \"All times are now in ms instead\"; the recovery metrics comment in quic-events-13: \"all following rtt fields are expressed in ms\".
- **Units in names**: no, units are written in CDDL comments (`; in bytes`, `; in bits per second`).
- **Booleans**: `is_` prefix (`is_mtu_probe_packet`); trigger reasons use a `trigger` field taking an enum string (`\"cc_bandwidth_probe\"`, `\"pto_probe\"`).
- **Cumulative quantities**: basically none. qlog is an event log, with one event recorded per packet and per loss; `recovery_metrics_updated` records the current value only when the value changes (original: \"emitted when one or more of the observable recovery metrics changes value\").""",
"iperf3 JSON (UDP)": """- **Case and separator**: all lowercase, underscore separated.
- **Units in names**: some have them, some do not. With units: `bits_per_second`, `jitter_ms`, `lost_percent`; without: `bytes`, `packets`, `lost_packets`, `seconds`, `start`, `end`.
- **Time unit**: `start`, `end`, `seconds` are seconds (the seconds of the interval start and end relative to the test start, and the interval duration); jitter is converted to milliseconds and written into the name (`jitter_ms`).
- **Cumulative and interval**: distinguished by position rather than by name. In `intervals[]` are interval values, and the `streams` and `sum` under `end` are whole run summaries; `sum` is the sum over multiple streams (jitter takes the average of the streams). The same set of key names is reused in intervals and summaries.
- **Other**: ratios use percentages and end in `_percent`; send and receive directions are marked with the boolean key `sender`.""",
"Linux tcp_info / ss": """- **tcp_info**: member names uniformly use the `tcpi_` prefix, followed by lowercase with underscores (`tcpi_bytes_received`, `tcpi_min_rtt`). Units do not go into the name, and the header mostly does not write them either; a few comments do (`tcpi_busy_time` commented \"Time (usec)\", `tcpi_total_rto_time` commented \"in milliseconds\", `tcpi_snd_wnd` commented \"(bytes)\"). From `tcp_get_info()`, the RTT class (`tcpi_rtt`, `tcpi_rttvar`, `tcpi_min_rtt`, `tcpi_rcv_rtt`, `tcpi_rto`) is in microseconds, `tcpi_last_*` is in milliseconds, and the rate class (`tcpi_pacing_rate`, `tcpi_delivery_rate`) is in bytes/second. Cumulative quantities often give the RFC 4898 name in comments (`tcpEStatsPerfSegsOut`, `tcpEStatsAppHCThruOctetsReceived`); the \"current value/cumulative value\" of the same quantity is distinguished by the `total_` prefix (`tcpi_retrans` and `tcpi_total_retrans`).
- **ss -i**: the output is space-separated `name:value` tokens; the name drops the `tcpi_` prefix and some are rewritten (`tcpi_min_rtt`->`minrtt`, `tcpi_last_data_recv`->`lastrcv`, `tcpi_rtt`/`tcpi_rttvar` combined into `rtt:<rtt>/<rttvar>`). Time is converted to milliseconds (manual: \"their units are millisecond\"), units do not go into the name; the rate class is changed to space-separated and `bps` is appended after the value (the format strings in ss.c are `\" delivery_rate %sbps\"`, `\" pacing_rate %sbps\"`, `\" send %sbps\"`, and the values are formatted by sprint_bw).""",
"GStreamer rtpmanager": """- **Case and separator**: GstStructure field names are all lowercase, hyphen separated (`packets-received`, `avg-jitter`, `packet-loss-pct`). Structure names are MIME style or type names: `application/x-rtp-source-stats`, `application/x-rtp-jitterbuffer-stats`, `application/x-rtp-session-stats`, `RTPTWCCStats`.
- **Prefix**: direction uses `sent-`/`recv-` (`sent-nack-count`, `recv-packet-rate`); received report block contents use `rb-` (received) and `sent-rb-` (sent); some counters use the `num-` prefix (`num-lost`, `num-pushed`), others use the `-count` suffix (`rtx-count`, `sent-pli-count`); averages use `avg-` (but `avg-jitter` is actually exponentially smoothed).
- **Units in names**: basically no, the only exception is the percentage `-pct`. Units are written in the documentation comments, and they differ per field: nanoseconds (`avg-jitter`, `avg-delta-of-delta`, which are GstClockTime), clock rate units (`jitter`), NTP short format 16.16 seconds (`rb-round-trip`, `rb-lsr`, `rb-dlsr`), bit/s (`bitrate`). The RTPSource:stats documentation opens with a specific reminder: \"Take note of each respective field's units\".
- **Payload and header-inclusive bytes**: `octets-` means payload bytes, `bytes-` means bytes including lower layer protocol headers (`octets-received` versus `bytes-received`).
- **Cumulative quantities**: not marked in the name, judged from \"total number of …\" in the documentation (`packets-received`, `bytes-received`); the twcc-stats quantities are values within a 300 ms sliding window.""",
}

ORDER = list(tables.keys())
lines = []
lines.append("# Transcription of real client telemetry fields (15 interface features x 7 sources)\n")
lines.append("Transcription date 2026-10-02. Only transcribe original text from public specifications, RFCs, official documentation, and official source code; all original text was fetched with curl and then checked, not filled in from memory. Write \"not found\" for anything that cannot be found. No design, no evaluation.\n")
lines.append("## How to read these tables\n")
lines.append("""- **Real field name**: Transcribe exactly as written; case, underscores, hyphens, and spaces are unchanged. When the same feature has multiple candidates, put only the closest one in the table and write the rest in \"reason\". When the field name is \"not found\", the \"reason\" states where it was searched and what is the closest match.
- **Unit**: When the documentation states it explicitly, transcribe the original text; when inference is needed, write the basis for the inference in parentheses.
- **Cumulative/interval**: cumulative = accumulated from the start of the session, requiring two readings to be subtracted to obtain an interval value; interval = a value defined by the documentation over a period of time or a range of sequence numbers; instantaneous = a smoothed estimate or the current value of the most recent measurement; per-event/per-packet = one raw record per packet or per event, with no aggregation.
- Criteria for determining **relationship** (fixed in advance before filling in, so that the seven sources are consistent):
  - **Same quantity**: the field itself, or the difference between two of its readings, equals our feature, differing at most by unit conversion (bytes and bits, seconds and milliseconds, ratio and percentage, fixed-point encoding) and statistical window length.
  - **different definition**: the same category of physical quantity, but additional computation is needed to obtain our feature (computing a rate, computing an average, aggregating by event), or the definition differs (round trip rather than one way, frame rather than packet, exponential smoothing rather than within-window statistics, sender rather than receiver, expected packet count rather than actually received packet count).
  - **None**: the documentation has no field measuring this quantity. If there is a field whose name or unit is easily confused, still list it in \"real field name\" and explain in the reason why it does not count.
- Our 15 features are given only names and units, with no formulas, so any source documentation that specifies an algorithm different from \"short-window statistics\" (for example exponential smoothing) is uniformly judged \"different definition\".
""")

lines.append("## Summary: number of features with a direct correspondence (same quantity) per source\n")
lines.append("| source | same quantity | different definition | none |")
lines.append("|---|---|---|---|")
for k in ORDER:
    c = counts[k]
    fmt = lambda xs: f"{len(xs)} ({', '.join(map(str, xs))})" if xs else "0"
    lines.append(f"| {k} | {fmt(c['same quantity'])} | {fmt(c['different definition'])} | {fmt(c['none'])} |")
lines.append("")
lines.append("""Supplementary notes:
- Of the 2 in webrtc-internals, feature 0 is a bracket-derived quantity, and feature 2 is the raw cumulative field drawn directly on the graph.
- Of the 3 in RFC 3550/3611, feature 1's `received_interval` is a variable in the RFC 3550 Appendix A.3 example code, not an RTCP packet field.
- Of the seven sources, features 3 (queueing delay), 6 (delay ratio), 7 (average minus minimum), 12, and 13 (audio-video proportion) all have none; feature 5 (minimum one-way delay) has only two \"same quantity\" matches, qlog's `min_rtt` and tcp_info's `tcpi_min_rtt` (both round-trip time); feature 14 (probing packet proportion) has only one \"same quantity\" match, qlog's `cc_bandwidth_probe` (per-packet marking); feature 11 has only one \"same quantity\" match, RFC 3611's Loss RLE `run length` (per-segment recording).
""")

for n, k in enumerate(ORDER, 1):
    lines.append(f"## {n}. {k}\n")
    lines.append(INTRO[k] + "\n")
    lines.append(tables[k] + "\n")
    lines.append("**Naming conventions**\n")
    lines.append(NAMING[k] + "\n")

open(os.path.join(OUT, "field_transcription.md"), "w", encoding="utf-8").write("\n".join(lines))
print("ok")
