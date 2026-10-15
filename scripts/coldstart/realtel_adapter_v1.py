#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Designer test on real client telemetry (registered experiment realtel-adapter-v1).
Seven real sources: W3C webrtc-stats, Chrome webrtc-internals, RFC 3550/3611, QUIC qlog, iperf3, Linux tcp_info, GStreamer rtpmanager. A method sees the source header, real field names, each field's location and the official text, but no values.
For each of the 15 interface features it returns one field plus a transform (difference of consecutive readings, scale factor), or missing.
Scoring: a same-quantity feature needs the right field, diff and scale (within 2%); a feature with no counterpart must be answered missing; same-kind fields with another definition are reported, not scored.
Usage: realtel_adapter_v1.py build | llm dev|test [ARM] | freeze | base | judge [--selftest]
build writes dev and test sources, ground truth and three field orders; llm calls the model (test checks the frozen template hash); freeze stores that hash;
base computes the NAME and TFIDF baselines with thresholds tuned on dev sources only; judge scores, bootstraps by source and records the verdict.
"""
import hashlib, json, math, random, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
OUT = ROOT / "experiments/results/realtel_adapter_v1"; ID = "realtel-adapter-v1"
DELTA = 0.15; FALSE_MAP_MAX = 0.15; NPRES = 3; SEED = 20261003
FEAT = ["receiving rate (bits per second over the window)", "number of packets received in the window", "number of bytes received in the window",
        "queuing delay (ms): mean one-way delay minus the minimum one-way delay seen so far, non-negative",
        "mean one-way delay (ms), measured between unsynchronized sender and receiver clocks, so it contains an unknown constant offset and can be negative",
        "minimum one-way delay seen so far (ms), with the same unknown clock offset as feature 4",
        "delay ratio: mean one-way delay divided by the minimum delay (dimensionless, close to 1; 0 when no packet arrived)",
        "mean one-way delay minus the minimum one-way delay within the window (ms, non-negative)", "mean packet inter-arrival time (ms)",
        "packet jitter (ms)", "packet loss ratio (fraction between 0 and 1)", "mean number of lost packets per loss event", "share of video packets (fraction)",
        "share of audio packets (fraction)", "share of probing packets (fraction)"]
SHORT = ["receiving rate (bit/s)", "packets received", "bytes received", "queuing delay (ms)", "mean one-way delay (ms, clock offset)", "minimum one-way delay (ms, clock offset)",
         "delay ratio", "mean minus minimum delay (ms)", "packet inter-arrival time (ms)", "jitter (ms)", "loss ratio (fraction)", "mean lost packets per loss event",
         "video packet share (fraction)", "audio packet share (fraction)", "probing packet share (fraction)"]

W3C_BYTES = "Total number of bytes received for this SSRC. This includes retransmissions. Calculated as defined in [RFC3550] section 6.4.1."
W3C_JITTER = "Packet Jitter measured in seconds for this SSRC. Calculated as defined in section 6.4.1. of [RFC3550]."
# Test sources: documentation text is quoted from the specifications, RFCs, source code or manuals; nothing is inferred.
TEST = {
 "w3c_webrtc_stats": {"header": "W3C WebRTC Statistics API (RTCPeerConnection.getStats()), receiving side of a video call. The application polls getStats() periodically and every stats object carries a timestamp. Spec guideline (Section 4.1): \"For stats that are measured against time, such as byte counts, no separate counter is needed; one can instead divide by the difference in the timestamps.\"",
  "fields": [("packetsReceived", "RTCReceivedRtpStreamStats", "Total number of RTP packets received for this SSRC. This includes retransmissions."),
             ("bytesReceived", "RTCInboundRtpStreamStats", W3C_BYTES),
             ("jitterBufferDelay", "RTCInboundRtpStreamStats", "It is the sum of the time, in seconds, each audio sample or a video frame takes from the time the first packet is received by the jitter buffer (ingest timestamp) to the time it exits the jitter buffer (emit timestamp)."),
             ("roundTripTime", "RTCRemoteInboundRtpStreamStats", "Estimated round trip time for this SSRC based on the RTCP timestamps in the RTCP Receiver Report (RR) and measured in seconds."),
             ("totalInterFrameDelay", "RTCInboundRtpStreamStats (video only)", "Sum of the interframe delays in seconds between consecutively rendered frames, recorded just after a frame has been rendered."),
             ("jitter", "RTCReceivedRtpStreamStats", W3C_JITTER),
             ("fractionLost", "RTCRemoteInboundRtpStreamStats", "The fraction packet loss reported for this SSRC. Calculated as defined in [RFC3550] section 6.4.1 and Appendix A.3."),
             ("kind", "RTCRtpStreamStats", "Either \"audio\" or \"video\". This MUST match the kind attribute of the related MediaStreamTrack.")],
  "same": {1: ("packetsReceived", True, 1.0), 2: ("bytesReceived", True, 1.0)}, "kind": [0, 4, 8, 9, 10]},
 "chrome_webrtc_internals": {"header": "chrome://webrtc-internals page of Chrome, graphs of getStats() series for an inbound video stream. Raw getStats() members are shown under their own names; names in square brackets are values the page derives between two consecutive stats reports.",
  "fields": [("[bytesReceived_in_bits/s]", "inbound-rtp", "Page source: \"in chrome://webrtc-internals/ we also want graphs for the average rate over the last second\"; \"bytesReceived: new RateCalculator('bytesReceived', 'timestamp', CalculatorModifier.kBytesToBits)\""),
             ("[packetsReceived/s]", "inbound-rtp", "Page source: \"if (this.samplesMetric === 'timestamp') { return '[' + accumulativeMetric + '/s]'; }\""),
             ("bytesReceived", "inbound-rtp (raw getStats() member)", "Raw getStats() member plotted as a series. W3C definition: \"" + W3C_BYTES + "\""),
             ("[jitterBufferDelay/jitterBufferEmittedCount_in_ms]", "inbound-rtp", "Page source: \"jitterBufferDelay: new RateCalculator('jitterBufferDelay', 'jitterBufferEmittedCount', CalculatorModifier.kMillisecondsFromSeconds)\""),
             ("[totalRoundTripTime/roundTripTimeMeasurements]", "remote-inbound-rtp", "Page source: \"totalRoundTripTime: new RateCalculator('totalRoundTripTime', 'roundTripTimeMeasurements')\""),
             ("[totalInterFrameDelay/framesDecoded_in_ms]", "inbound-rtp (video only)", "Page source: \"totalInterFrameDelay: new RateCalculator('totalInterFrameDelay', 'framesDecoded', CalculatorModifier.kMillisecondsFromSeconds)\""),
             ("jitter", "inbound-rtp (raw getStats() member)", "Raw getStats() member plotted as a series. W3C definition: \"" + W3C_JITTER + "\""),
             ("[packetsReportedAsLost/s]", "inbound-rtp and remote-inbound-rtp", "Page source: \"packetsReportedAsLost: new RateCalculator('packetsReportedAsLost', 'timestamp', CalculatorModifier.kRounded)\"")],
  "same": {0: ("[bytesReceived_in_bits/s]", False, 1.0), 2: ("bytesReceived", True, 1.0)}, "kind": [1, 4, 8, 9, 10]},
 "rfc3550_rfc3611": {"header": "RTCP-based statistics of an RTP video session at the receiver: RFC 3550 sender and receiver reports (with the Appendix A.3 example code for receiver report statistics), RTCP XR report blocks from RFC 3611, and the RTP header. Video RTP clock rate: 90 kHz.",
  "fields": [("sender's octet count", "RFC 3550 sender report, sender info", "The total number of payload octets (i.e., not including header or padding) transmitted in RTP data packets by the sender since starting transmission up until the time this SR packet was generated."),
             ("received_interval", "RFC 3550 Appendix A.3 (computing receiver report statistics)", "Example code: \"received_interval = s->received - s->received_prior;\". Section 6.4.1: \"The number of packets received is the number of packets expected minus the number lost.\""),
             ("jitter buffer nominal delay (JB nominal)", "RFC 3611 VoIP Metrics Report Block", "This is the current nominal jitter buffer delay in milliseconds, which corresponds to the nominal jitter buffer delay for packets that arrive exactly on time."),
             ("round trip delay", "RFC 3611 VoIP Metrics Report Block", "The most recently calculated round trip time between RTP interfaces, expressed in milliseconds."),
             ("min_jitter", "RFC 3611 Statistics Summary Report Block", "The minimum jitter measured for a pair of packets in the above sequence number interval."),
             ("Packet i receipt time", "RFC 3611 Packet Receipt Times Report Block", "The receipt time of the packet with sequence number i at the receiver. ... Units and format are the same as for the timestamp in RTP data packets."),
             ("mean_jitter", "RFC 3611 Statistics Summary Report Block", "The mean relative transit time between each two packet series in the above sequence number interval, rounded to the nearest value expressible as an RTP timestamp."),
             ("fraction lost", "RFC 3550 report block (in SR and RR)", "fraction lost: 8 bits. The fraction of RTP data packets from source SSRC_n lost since the previous SR or RR packet was sent, expressed as a fixed point number with the binary point at the left edge of the field."),
             ("run length", "RFC 3611 Loss RLE Report Block, run length chunk", "run type (R): 1 bit - Zero indicates a run of 0s. One indicates a run of 1s. run length: 14 bits - A value between 1 and 16,383."),
             ("payload type", "RTP fixed header", "This field identifies the format of the RTP payload and determines its interpretation by the application.")],
  "same": {1: ("received_interval", False, 1.0), 9: ("mean_jitter", False, 1000.0 / 90000.0), 10: ("fraction lost", False, 1.0 / 256.0)}, "kind": [0, 2, 4, 8, 11]},
 "quic_qlog": {"header": "qlog event log of a QUIC connection on the receiving endpoint (draft-ietf-quic-qlog-quic-events-13 with the main schema draft -14). Every event carries a time field.",
  "fields": [("time", "common field of all events", "The time field is a float64 and it is typically used to represent a duration in milliseconds, with a fractional component to microsecond or nanosecond resolution."),
             ("quic:packet_received", "event name", "The packet_received event indicates a QUIC-level packet was received."),
             ("raw.length", "quic:packet_received event, raw field (RawInfo)", "the full byte length of the entity (e.g., packet or frame), including possible headers and trailers. length: uint64"),
             ("smoothed_rtt", "quic:recovery_metrics_updated event", "Loss detection, see RFC 9002 Appendix A.3; all following rtt fields are expressed in ms. smoothed_rtt: float32"),
             ("min_rtt", "quic:recovery_metrics_updated event", "all following rtt fields are expressed in ms. min_rtt: float32"),
             ("rtt_variance", "quic:recovery_metrics_updated event", "all following rtt fields are expressed in ms. rtt_variance: float32"),
             ("quic:packet_lost", "event name", "The packet_lost event is emitted when a packet is deemed lost by loss detection."),
             ("trigger = \"cc_bandwidth_probe\"", "quic:packet_sent event, trigger field", "needed for some CCs to figure out bandwidth allocations when there are no normal sends: \"cc_bandwidth_probe\"")],
  "same": {}, "kind": [0, 1, 2, 4, 5, 9, 10, 14]},
 "iperf3_udp_json": {"header": "iperf3 --json output of a UDP test, receiving side; one record per reporting interval in intervals[].streams[] (default interval 1 s). Field meanings come from the iperf3 source code.",
  "fields": [("bits_per_second", "intervals[].streams[]", "Source: \"bandwidth = (double) irp->bytes_transferred / (double) irp->interval_duration;\" ... \"bits_per_second\": bandwidth * 8"),
             ("packets", "intervals[].streams[]", "Source comment: \"sp->packet_count is the highest sequence number seen so far\"; \"temp.interval_packet_count = sp->packet_count - irp->packet_count;\""),
             ("bytes", "intervals[].streams[]", "Source: \"sp->result->bytes_received_this_interval += r;\"; \"temp.bytes_transferred = sp->sender ? rp->bytes_sent_this_interval : rp->bytes_received_this_interval;\""),
             ("jitter_ms", "intervals[].streams[]", "Source: \"This computation is based on RFC 1889 (specifically sections 6.3.1 and A.8).\"; \"sp->jitter += (d - sp->jitter) / 16.0;\""),
             ("lost_percent", "intervals[].streams[]", "Source: \"lost_percent = 100.0 * irp->interval_cnt_error / irp->interval_packet_count;\"")],
  "same": {0: ("bits_per_second", False, 1.0), 2: ("bytes", False, 1.0), 10: ("lost_percent", False, 0.01)}, "kind": [1, 9]},
 "linux_tcp_info": {"header": "Linux TCP_INFO socket option (struct tcp_info) read on the receiving host; the same values are printed by ss -i. Field meanings come from kernel headers, kernel source and the ss manual.",
  "fields": [("tcpi_delivery_rate", "struct tcp_info", "Kernel: \"rate64 = (u64)rate * tp->mss_cache * USEC_PER_SEC;\" (tcp.c); ss: \"out(\\\" delivery_rate %sbps\\\", sprint_bw(b1, s->delivery_rate));\" (ss.c)"),
             ("tcpi_data_segs_in", "struct tcp_info", "Header: \"__u32 tcpi_data_segs_in; /* RFC4898 tcpEStatsDataSegsIn */\"; comment: \"total number of data segments in.\""),
             ("tcpi_bytes_received", "struct tcp_info", "Header: \"__u64 tcpi_bytes_received; /* RFC4898 tcpEStatsAppHCThruOctetsReceived */\"; include/linux/tcp.h: \"sum(delta(rcv_nxt)), or how many bytes were acked.\""),
             ("tcpi_rtt", "struct tcp_info", "Kernel: \"info->tcpi_rtt = tp->srtt_us >> 3;\" (tcp.c); ss manual: \"rtt is the average round trip time, rttvar is the mean deviation of rtt, their units are millisecond\""),
             ("tcpi_min_rtt", "struct tcp_info", "ip-sysctl (tcp_min_rtt_wlen): \"The window length of the windowed min filter to track the minimum RTT.\" ... \"Default: 300\""),
             ("tcpi_last_data_recv", "struct tcp_info", "ss manual: \"how long it has been since the last packet received, the unit is millisecond\""),
             ("tcpi_rttvar", "struct tcp_info", "Kernel: \"info->tcpi_rttvar = tp->mdev_us >> 2;\""),
             ("tcpi_lost", "struct tcp_info", "Kernel: \"info->tcpi_lost = tp->lost_out;\""),
             ("tcpi_probes", "struct tcp_info", "Kernel: \"info->tcpi_probes = icsk->icsk_probes_out;\"; \"@icsk_probes_out: unanswered 0 window probes\"")],
  "same": {1: ("tcpi_data_segs_in", True, 1.0), 2: ("tcpi_bytes_received", True, 1.0)}, "kind": [0, 4, 5, 9, 10]},
 "gstreamer_rtpmanager": {"header": "GStreamer rtpmanager on the receiving side of an RTP video session: rtpsession twcc-stats (RTPTWCCStats), RTPSource stats (application/x-rtp-source-stats) and rtpjitterbuffer stats. Field meanings come from the element documentation and source.",
  "fields": [("bitrate-recv", "rtpsession twcc-stats", "\"bitrate-recv\" G_TYPE_UINT The estimated bitrate for the receiver. Source: \"stats->window_size = 300 * GST_MSECOND;\" (rtpstats.c)"),
             ("packets-received", "RTPSource stats", "\"packets-received\" G_TYPE_UINT64 total number of packets received"),
             ("bytes-received", "RTPSource stats", "\"bytes-received\" G_TYPE_UINT64 total number of bytes received including lower level headers overhead"),
             ("rb-round-trip", "RTPSource stats", "\"rb-round-trip\" G_TYPE_UINT the round-trip time (seconds in NTP Short Format, 16.16 fixed point)"),
             ("avg-delta-of-delta", "rtpsession twcc-stats", "\"avg-delta-of-delta\", G_TYPE_INT64 In nanoseconds, a moving window average of the difference in inter-packet spacing between sender and receiver."),
             ("avg-jitter", "rtpjitterbuffer stats", "#guint64 avg-jitter: the average jitter in nanoseconds. Source: \"priv->avg_jitter = (diff + (15 * priv->avg_jitter)) >> 4;\""),
             ("packet-loss-pct", "rtpsession twcc-stats", "\"packet-loss-pct\" G_TYPE_DOUBLE Packetloss percentage, based on packets reported as lost from the receiver.")],
  "same": {0: ("bitrate-recv", False, 1.0), 1: ("packets-received", True, 1.0), 2: ("bytes-received", True, 1.0), 10: ("packet-loss-pct", False, 0.01)}, "kind": [4, 8, 9]},
}
# Dev sources are invented; they only freeze the prompt and tune baseline thresholds and are never scored.
DEV = {
 "dev_acme_sdk": {"header": "AcmeRTC mobile SDK, per-second statistics callback (JSON), receiving side of a video call.",
  "fields": [("rxBitrateKbps", "stats.inbound", "Receive bitrate in kbit/s, averaged over the last callback interval."),
             ("rxPacketsTotal", "stats.inbound", "Total number of RTP packets received since the call started."),
             ("rxBytesTotal", "stats.inbound", "Total number of payload bytes received since the call started."),
             ("owdMeanMs", "stats.network", "Mean one-way delay of the packets received in the last interval, in milliseconds. Sender and receiver clocks are not synchronized."),
             ("owdMinMs", "stats.network", "Lowest one-way delay observed since the call started, in milliseconds, with the same clock offset as owdMeanMs."),
             ("rttMs", "stats.network", "Smoothed round-trip time from RTCP, in milliseconds."),
             ("jitterSec", "stats.inbound", "Interarrival jitter in seconds, RFC 3550 estimator."),
             ("lossRatePct", "stats.inbound", "Packets lost in the last interval as a percentage of packets expected."),
             ("renderDelayMs", "stats.video", "Time from frame decode to display, in milliseconds."),
             ("fps", "stats.video", "Frames rendered per second.")],
  "same": {0: ("rxBitrateKbps", False, 1000.0), 1: ("rxPacketsTotal", True, 1.0), 2: ("rxBytesTotal", True, 1.0), 4: ("owdMeanMs", False, 1.0), 5: ("owdMinMs", False, 1.0), 10: ("lossRatePct", False, 0.01)}, "kind": [9]},
 "dev_netmon": {"header": "netmon probe daemon on the receiving host, one JSON line every 500 ms.",
  "fields": [("rx_bytes_interval", "record", "Bytes received during the reporting interval."),
             ("rx_pkts_interval", "record", "Packets received during the reporting interval."),
             ("rx_rate_mbps", "record", "Receive throughput over the reporting interval, Mbit/s."),
             ("tx_rate_mbps", "record", "Send throughput of the local endpoint over the reporting interval, Mbit/s."),
             ("qdelay_us", "record", "Estimated queuing delay: one-way delay above the path minimum, in microseconds."),
             ("iat_mean_ns", "record", "Mean packet inter-arrival time in the reporting interval, nanoseconds."),
             ("loss_events", "record", "Number of loss events (runs of consecutive lost packets) in the reporting interval."),
             ("lost_pkts", "record", "Packets lost in the reporting interval."),
             ("video_pkt_ratio", "record", "Fraction of received packets that carry video."),
             ("cpu_util", "record", "Receiver CPU utilisation, percent.")],
  "same": {0: ("rx_rate_mbps", False, 1e6), 1: ("rx_pkts_interval", False, 1.0), 2: ("rx_bytes_interval", False, 1.0), 3: ("qdelay_us", False, 1e-3), 8: ("iat_mean_ns", False, 1e-6), 12: ("video_pkt_ratio", False, 1.0)}, "kind": [10, 11]},
}

TEMPLATE = """A learned bandwidth estimator for real-time video calls reads, every 60 ms, an observation of 15 interface features, each measured over 10 windows (windows 1 to 5: five 60 ms windows; windows 6 to 10: five 600 ms windows). The interface specification:
{spec}

A new client stack is being connected. Its telemetry source:
{header}

The fields it exposes, with where they live and the documentation or source text that defines them:
{fields}

Write the adapter from this source to the interface. For every interface feature decide one of two things.
(a) Map it: one field measures the same quantity, possibly after taking the difference of two consecutive readings (for cumulative counters) and multiplying by a constant (for units). Give the field index, "diff" (true if the difference of two consecutive readings is used) and "scale" (interface value = field value, or its difference, times scale). Differences in the length of the reporting interval are acceptable.
(b) Missing: no single field measures the same quantity this way, for example the quantity would need a different definition, a combination of several fields, or another computation. Give "source": null.
A field may be used for more than one feature. Answer as JSON in a single ```json code block: {{"mapping": [{{"feature": 0, "source": j or null, "diff": true or false, "scale": a}}, ... one entry for each feature 0 to 14]}}. Keep your reasoning brief."""


def tmpl_hash(): return hashlib.sha256((TEMPLATE + json.dumps(FEAT)).encode()).hexdigest()


def present(src, k):
    """Return the k-th presentation of a source: fields shuffled with a fixed seed (k=0 keeps the transcribed order), plus a name-to-index map."""
    f = list(src["fields"])
    if k: random.Random(SEED + 97 * k + sum(map(ord, src["header"][:20]))).shuffle(f)
    return f, {n: j for j, (n, _, _) in enumerate(f)}


def build_prompt(src, k):
    f, _ = present(src, k)
    spec = "\n".join(f"{i}. {s}" for i, s in enumerate(FEAT))
    fields = "\n".join(f"field {j}: {n} | {w} | {d}" for j, (n, w, d) in enumerate(f))
    return TEMPLATE.format(spec=spec, header=src["header"], fields=fields)


def truth(src):
    """Return the per-feature ground truth: ("same", field, diff, scale), ("kind",) or ("none",)."""
    out = []
    for k in range(15):
        if k in src["same"]: n, d, s = src["same"][k]; out.append(("same", n, d, s))
        elif k in src["kind"]: out.append(("kind",))
        else: out.append(("none",))
    return out


def cmd_build():
    import obsrepair_llm_v1 as OR
    assert FEAT == OR.FEAT, "interface feature descriptions differ from those of obsrepair_llm_v1.py"
    OUT.mkdir(parents=True, exist_ok=True)
    for tag, S in (("dev", DEV), ("test", TEST)):
        for name, src in S.items():
            names = [n for n, _, _ in src["fields"]]; assert len(set(names)) == len(names), name
            for k, (n, d, s) in src["same"].items(): assert n in names, (name, n)
            assert not (set(src["same"]) & set(src["kind"])), name
        json.dump({name: {"truth": truth(src), "fields": src["fields"], "header": src["header"]} for name, src in S.items()}, open(OUT / f"sources_{tag}.json", "w"), ensure_ascii=False, indent=1)
    cnt = lambda S, c: sum(t[0] == c for s in S.values() for t in truth(s))
    print("test source", len(TEST), "Same", cnt(TEST, "same"), "none", cnt(TEST, "none"), "different definition", cnt(TEST, "kind"), "; development source", len(DEV), "Same", cnt(DEV, "same"), "none", cnt(DEV, "none"))
    print("template hash", tmpl_hash()[:12])


def parse(txt, nf):
    m = re.findall(r"```json\s*(.*?)```", txt, re.S); body = re.sub(r"//[^\n]*", "", m[-1])
    body = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\w.])", lambda q: repr(float(q.group(1)) / float(q.group(2))), body)
    js = json.loads(body); mp = [None] * 15
    for e in js["mapping"]:
        k = int(e["feature"]); s = e.get("source")
        mp[k] = None if s is None or not 0 <= int(s) < nf else {"source": int(s), "diff": bool(e.get("diff", False)), "scale": float(e.get("scale", 1.0))}
    return mp


def cmd_llm(phase, arm="DEEPSEEK"):
    import coldstart_rule_v1 as CR
    th = tmpl_hash()
    if phase == "test": assert th == (OUT / "prompt_hash_frozen.txt").read_text().strip(), "prompt template differs from the frozen version"
    S = DEV if phase == "dev" else TEST; cache = OUT / f"llm_{phase}_{arm.lower()}.jsonl"; done = {}
    if cache.exists(): done = {(j["source"], j["pres"]): j for j in map(json.loads, open(cache)) if j.get("ok")}
    jobs = [(n, k) for n in S for k in range(NPRES) if (n, k) not in done]; lock = threading.Lock(); print("to run", len(jobs), "template hash", th[:12], flush=True)
    def work(job):
        n, k = job; p = build_prompt(S[n], k); r = CR.ask(p, 48000); txt = r["choices"][0]["message"].get("content") or ""
        try: mp = parse(txt, len(S[n]["fields"])); ok = True
        except Exception: mp, ok = None, False
        rec = {"source": n, "pres": k, "arm": arm, "mapping": mp, "ok": ok, "tail": txt[-400:], "usage": r.get("usage", {}), "prompt_sha": hashlib.sha256(p.encode()).hexdigest()[:12]}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); done[(n, k)] = rec; print(n, k, "parsed" if ok else "parse failure", r.get("usage", {}).get("completion_tokens"), flush=True)
    if not CR.AR.ok_to_send(): print("peak hours, not sending"); return
    bal = CR.AR.balance(CR.AR.KEY.read_text().strip())
    if bal < CR.AR.MIN_BALANCE: print("balance", bal, "below MIN_BALANCE, stopping"); return
    with ThreadPoolExecutor(5) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


# Non-LLM baselines use generic name similarity and common unit spellings only; thresholds come from dev sources.
UNIT_TARGET = {0: "bps", 1: "count", 2: "byte", 3: "ms", 4: "ms", 5: "ms", 6: "ratio", 7: "ms", 8: "ms", 9: "ms", 10: "frac", 11: "count", 12: "frac", 13: "frac", 14: "frac"}


def unit_scale(k, name, doc):
    """Guess the scale to the interface unit from unit words in a field's name and text; return 1 if none is recognized."""
    t = (name + " " + doc).lower(); tgt = UNIT_TARGET[k]
    if tgt == "ms":
        if re.search(r"nanosecond|_ns\b|\bns\b", t): return 1e-6
        if re.search(r"microsecond|usec|_us\b|\bus\b", t): return 1e-3
        if re.search(r"millisecond|_ms\b|\bms\b", t): return 1.0
        if re.search(r"second|_sec\b|\bsec\b|_s\b", t): return 1000.0
    if tgt == "frac" and re.search(r"percent|_pct|-pct|pct\b|%", t): return 0.01
    if tgt == "bps":
        if re.search(r"mbit|mbps", t): return 1e6
        if re.search(r"kbit|kbps", t): return 1e3
        if re.search(r"byte", t) and not re.search(r"bit", t): return 8.0
    if tgt == "byte" and re.search(r"\bbits\b|_bits", t) and not re.search(r"byte|octet", t): return 1 / 8
    return 1.0


def is_cum(doc): return bool(re.search(r"\btotal\b|\bsum of\b|since (the call started|starting|start)", doc.lower()))


def toks(s):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s); return [w for w in re.split(r"[^a-z0-9]+", s.lower()) if w and w not in {"the", "of", "in", "a", "an", "and", "or", "for", "to", "is", "by", "as", "this", "with", "be", "it", "on", "at"}]


def sim_name(k, n):
    import difflib
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum()); return difflib.SequenceMatcher(None, norm(SHORT[k]), norm(n)).ratio()


def tfidf_matrix(src):
    docs = [toks(n + " " + d) for n, _, d in src["fields"]]; qs = [toks(FEAT[k]) for k in range(15)]; allt = docs + qs; N = len(allt)
    df = {}
    for d in allt:
        for w in set(d): df[w] = df.get(w, 0) + 1
    vec = lambda d: {w: d.count(w) * math.log((1 + N) / (1 + df[w])) for w in set(d)}
    cos = lambda a, b: sum(a[w] * b.get(w, 0) for w in a) / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())) + 1e-12)
    D = [vec(d) for d in docs]; Q = [vec(q) for q in qs]; return [[cos(Q[k], D[j]) for j in range(len(docs))] for k in range(15)]


def base_map(src, kind, tau):
    f = src["fields"]; S = [[sim_name(k, n) for n, _, _ in f] for k in range(15)] if kind == "NAME" else tfidf_matrix(src); mp = []
    for k in range(15):
        j = max(range(len(f)), key=lambda j: S[k][j])
        if S[k][j] < tau: mp.append(None); continue
        n, _, d = f[j]; mp.append({"source": j, "diff": is_cum(d), "scale": unit_scale(k, n, d)})
    return mp


def score(src_truth, fields, mp):
    """Score one mapping against ground truth: per-feature hits for same and none features, and the number of false mappings."""
    same, none, fm = [], [], 0
    for k, t in enumerate(src_truth):
        m = mp[k] if mp else None
        if t[0] == "same":
            ok = m is not None and fields[m["source"]][0] == t[1] and bool(m["diff"]) == bool(t[2]) and abs(m["scale"] - t[3]) <= 0.02 * abs(t[3]); same.append(int(ok))
        elif t[0] == "none":
            none.append(int(m is None)); fm += int(m is not None)
    return {"same": same, "none": none, "false_map": fm}


def ba(rows):
    s = [x for r in rows for x in r["same"]]; n = [x for r in rows for x in r["none"]]
    return 0.5 * (sum(s) / len(s) if s else 1.0) + 0.5 * (sum(n) / len(n) if n else 1.0)


def cmd_base():
    dev = {n: s for n, s in DEV.items()}; res = {}
    for kind in ("NAME", "TFIDF"):
        grid = [round(0.05 * i, 2) for i in range(1, 20)]
        devba = {t: ba([score(truth(s), s["fields"], base_map(s, kind, t)) for s in dev.values()]) for t in grid}
        tau = max(grid, key=lambda t: (devba[t], -t)); res[kind] = {"tau": tau, "dev_ba": devba[tau], "maps": {n: base_map(s, kind, tau) for n, s in TEST.items()}}
        print(kind, "best dev threshold", tau, "dev BA", round(devba[tau], 3))
    json.dump(res, open(OUT / "baselines.json", "w"), ensure_ascii=False, indent=1)


def rows_for(maps_by_source_pres):
    """Score mappings keyed by (source, presentation) on the test sources and return one row per key."""
    out = []
    for (n, k), mp in maps_by_source_pres.items():
        f, _ = present(TEST[n], k); r = score(truth(TEST[n]), f, mp); r.update({"source": n, "pres": k}); out.append(r)
    return out


def judge(R_llm, R_base, seed=SEED, B=5000):
    """Apply the registered criterion to delta = BA(LLM) - best baseline BA (source-block bootstrap, 90% interval, false-mapping safety line); return verdict and metrics."""
    srcs = sorted({r["source"] for r in R_llm}); best = max(R_base, key=lambda b: ba(R_base[b])); bl = R_base[best]
    def d(sel): return ba([r for s in sel for r in R_llm if r["source"] == s]) - ba([r for s in sel for r in bl if r["source"] == s])
    D = d(srcs); rng = random.Random(seed); boots = sorted(d([rng.choice(srcs) for _ in srcs]) for _ in range(B))
    lo, hi = boots[int(0.05 * B)], boots[int(0.95 * B) - 1]
    nn = sum(len(r["none"]) for r in R_llm); fmr = sum(r["false_map"] for r in R_llm) / nn if nn else 0.0; safe = fmr <= FALSE_MAP_MAX
    v = "does not hold" if (not D > 0 or not safe) else ("holds" if lo > 0 and D >= DELTA else "direction only")
    return v, {"delta": D, "ci90": [lo, hi], "best_base": best, "ba_llm": ba(R_llm), "ba_base": {b: ba(R_base[b]) for b in R_base}, "false_map_rate": fmr, "safe": safe}


def selftest():
    def mk(p_same, p_none, p_fm, rng):
        rows = []
        for n in TEST:
            t = truth(TEST[n]); same = [int(rng.random() < p_same) for x in t if x[0] == "same"]; none = [int(rng.random() < p_none) for x in t if x[0] == "none"]
            rows.append({"source": n, "pres": 0, "same": same, "none": none, "false_map": sum(1 - x for x in none) if p_fm else 0})
        return rows
    rng = random.Random(1)
    assert judge(mk(0.95, 0.97, 1, rng), {"A": mk(0.4, 0.6, 1, rng)})[0] == "holds"
    assert judge(mk(0.5, 0.6, 1, rng), {"A": mk(0.9, 0.95, 1, rng)})[0] == "does not hold"
    assert judge(mk(0.95, 0.5, 1, rng), {"A": mk(0.2, 0.5, 1, rng)})[0] == "does not hold"
    for n, s in TEST.items():
        f, idx = present(s, 1); t = truth(s)
        perfect = [({"source": idx[x[1]], "diff": x[2], "scale": x[3]} if x[0] == "same" else None) for x in t]
        r = score(t, f, perfect); assert all(r["same"]) and all(r["none"]) and r["false_map"] == 0, n
        r0 = score(t, f, [None] * 15); assert not any(r0["same"]) and all(r0["none"]), n
    print("Decision and scoring self-test passed (holds, does not hold, safety line, all correct, all missing)")


def cmd_judge():
    L = [json.loads(l) for l in open(OUT / "llm_test_deepseek.jsonl")]; L = {(j["source"], j["pres"]): j["mapping"] for j in L if j.get("ok")}
    for n in TEST:
        for k in range(NPRES): L.setdefault((n, k), None)
    R_llm = rows_for(L); Bj = json.load(open(OUT / "baselines.json"))
    R_base = {b: rows_for({(n, 0): Bj[b]["maps"][n] for n in TEST}) for b in Bj}
    v, m = judge(R_llm, R_base)
    per = {n: {"LLM_same": sum(sum(r["same"]) for r in R_llm if r["source"] == n), "LLM_none": sum(sum(r["none"]) for r in R_llm if r["source"] == n),
               **{f"{b}_same": sum(R_base[b][i]["same"].count(1) for i in range(len(R_base[b])) if R_base[b][i]["source"] == n) for b in R_base}} for n in TEST}
    json.dump({"verdict": v, **m, "per_source": per, "rows_llm": R_llm, "rows_base": R_base}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    ns = sum(len(r["same"]) for r in R_llm); nn = sum(len(r["none"]) for r in R_llm)
    basis = (f"7 real sources, {NPRES} field orders per source: DeepSeek same quantity {sum(sum(r['same']) for r in R_llm)}/{ns}, no-counterpart features answered missing {sum(sum(r['none']) for r in R_llm)}/{nn}, balanced accuracy {m['ba_llm']:.3f}; control {', '.join(f'{b} {x:.3f}' for b, x in m['ba_base'].items())} (best: {m['best_base']}); Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; mis-mapping rate {m['false_map_rate']:.3f}. Per source see judge.json.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m[k] for k in ("delta", "ci90", "ba_llm", "ba_base", "false_map_rate")}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template)." + basis, "--basis", basis,
       "--limitations", "Uses only the field descriptions of the specification or source code, no values; seven sources, so the source-resampled intervals are wide; ground truth transcribed from the original text, with one direction error caught by an LLM check; decisions of different definition are not scored; only two generic baselines.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "build": cmd_build()
    elif c == "llm": cmd_llm(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "DEEPSEEK")
    elif c == "freeze": (OUT / "prompt_hash_frozen.txt").write_text(tmpl_hash()); print("freeze", tmpl_hash()[:12])
    elif c == "base": cmd_base()
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
