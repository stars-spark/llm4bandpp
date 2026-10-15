#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cell-by-cell adjudication of the disagreements in registered experiment gt-blind-expert-v1 (the engineer's blind labels of the ground truth).
Scope fixed in advance: the 16 scored cells where the engineer disagrees (ground truth same quantity 14, no counterpart 2) and the 22 cells where
the engineer chose same quantity and the ground truth did not. The 127 cells with ground truth different definition and label no counterpart are
only reported; their effect is bounded by the sensitivity analysis that scores every different definition as no counterpart.
Each cell gets a verdict (ground truth correct, engineer correct, or reclassify as different definition and drop from scoring), an error category
and its basis in the official documentation or source code. Asserts that the verdicts cover exactly the disagreement cells of result.json.
Writes experiments/results/gt_blind_expert_v1/adjudication.json and a Markdown report. Usage: python3 scripts/paper/gt_blind_adjudicate_v1.py
"""
import json
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; OUT = ROOT / "experiments/results/gt_blind_expert_v1"
KEEP = "The current answer is correct"
AGORA_PKG = "Agora Web SDK npm package agora-rtc-sdk-ng-4.24.8.tgz (sha256 3afd4b17de80b38e100f7f0fa86eb4186ab462677d28179b67af6ea2efe41034, downloaded from registry.npmjs.org on 2026-10-04, not committed to the repository)"
AGORA = "SDK 4.24.8 source code"
JIT = ("The description states that jitter is determined by the standard deviation of packet arrival gaps within the window, and the collector scripts/alphartc/deploy/spec_collector.py lines 120 to 123 computes exactly the population standard deviation of arrival gaps within the window. This field is RFC 3550-style interarrival jitter, that is, exponential smoothing with a 1/16 gain applied to the absolute value of the transmission time difference between adjacent packets; it is a smoothed estimate and not a standard deviation, and multiplying by a constant cannot convert it into feature 9.")
R = {
    ("S08", 0): (KEEP, "Total field", f"{AGORA}: RecvBitrate is the sum of the audio and video receiveBitrate of all remote users, receiveBitrate = 8 × max(0, this receiveBytes − previous), updated every 1000 milliseconds, that is, the most recent one-second receiving rate measured locally. Feature 0 counts all inbound packets, including audio (collector v6 adds back exactly this audio that the testbed underreported), and the audio plus video total is exactly the definition of feature 0. That sentence in the description says that fields covering only a single stream also count as the same quantity, and does not exclude aggregate fields."),
    ("S08", 1): (KEEP, "Difference allowed", f"The description allows a cumulative counter to take the difference between two adjacent readings; the number of packets in the window does not need to be divided by time again. {AGORA}: receivePackets directly takes the packets from the browser inbound-rtp statistics, measured locally."),
    ("S08", 2): (KEEP, "Difference allowed", f"{AGORA}: RecvBytes is the sum of the audio and video receiveBytes of all remote users, measured locally; the total covers all inbound bytes, consistent with the definition of feature 2."),
    ("S09", 1): (KEEP, "Missed field", "The candidate F4 on this page is packetsReceived (RemoteTrackStats), original text \"Number of packets received\". The engineer judged none, and the basis column itself also mentions the received packet count."),
    ("S10", 0): (KEEP, "Already has full fields", "Three rate fields on the page: audioRecvBitsPerSecond, recvBitsPerSecond (\"Total incoming bits per second (audio + video)\"), videoRecvBitsPerSecond (video payload only). Feature 0 includes audio; when the full field is available, the full field is the answer; the video-only field systematically omits the audio portion, and the deployment audit of this project found the same thing (the twelfth definition difference, about 41 kbit/s on the testbed). The quantity measured by the engineer's field is similar, but it is not the closest one."),
    ("S12", 1): (KEEP, "Difference allowed", "packetCount is the cumulative number of received packets for this inbound RTP stream, and the description allows differencing; after differencing it is the in-window packet count."),
    ("S14", 0): (KEEP, "Missed field", "The engineer chose bytes and judged the definition different; in the rationale the engineer wrote that the same page also has bytes_lastsec. The original text of bytes_lastsec is \"Bytes sent or received in the last second\"; multiplied by 8 it is bit/s over a one-second window, the same type as precedent chrome_webrtc_internals feature 0."),
    ("S14", 1): (KEEP, "Different quantity", "The engineer filled in bytes_lastsec, which is a byte count, not a packet count. The current answer packets is the cumulative received packet count per inbound media stream; the difference is the packet count within the window."),
    ("S14", 2): (KEEP, "Already has fields closer to", "The bytes difference gives exactly the byte count within the collection window; bytes_lastsec is the byte count of a fixed one-second window, and by \"different window lengths are acceptable\" it also makes sense. When both exist, the difference field that exactly matches the collection window is the answer; the engineer's field is acceptable but not closer."),
    ("S16", 0): (KEEP, "Missed field", "candidate F3 mbpsRecvRate, marked in the SRT official statistics documentation as Interval-based, Receiver, original text \"Receiving rate in Mbps. Receiver side.\", multiplied by 10^6 gives bit/s. The engineer chose the cumulative byteRecvTotal and did not see a ready-made rate field."),
    ("S17", 1): (KEEP, "cumulative within window", "original text \"Total number of received packets for the flow\", FlowStats accumulates from the start of the flow and does not reset per window; the in-window packet count requires subtracting two adjacent values. The engineer judged that differencing is not applied."),
    ("S17", 2): (KEEP, "cumulative within window", "original text \"Total number of received bytes for the flow\", same as above, differencing is required."),
    ("S17", 5): (KEEP, "clock offset", "The definition of feature 5 is the minimum one-way delay so far, containing the same unknown constant offset as feature 4. The unknown constant can be zero; in simulation the sender and receiver share a clock, so the offset is exactly zero, and the quantity is still the minimum one-way delay so far. The collector itself also artificially sets the delay origin to 200 milliseconds for the first packet (spec_collector.py line 113), and the estimator only uses differences. The offset is permitted by the feature, not required by the feature."),
    ("S19", 1): (KEEP, "Difference allowed", "packetsReceived is the cumulative number of received packets for the receiving SSRC, and the description allows differencing."),
    ("S06", 11): (KEEP, "event field", "The description states that feature 11 selects none when there is only a cumulative packet loss count or packet loss rate, and selects different definition only when there are burst or event-type fields. tcpi_lost is the number of segments marked lost in the send direction (tp->lost_out), and tcpi_probes is the number of zero-window probes; neither is a packet loss event or burst record."),
    ("S16", 14): (KEEP, "event field", "mbpsBandwidth is the link bandwidth estimated by the sender from probe packet pairs; no field in the SRT statistics table counts the number of probe packets or their proportion. The appearance of probe packets in the description does not mean there is a related field; the engineer's rationale also states \"not the receiver probe packet proportion\"."),
    ("S01", 0): (KEEP, "divide by time", "bytesReceived difference multiplied by 8 gives the number of bits within the window, not bits per second; it still needs to be divided by the difference of the two timestamps, and the specification text cited by the engineer also says divide by the difference in the timestamps. This is a combination of two fields, so the description column is different definition."),
    ("S01", 9): (KEEP, "jitter definition", JIT),
    ("S02", 9): (KEEP, "jitter definition", JIT + "webrtc-internals plots the raw getStats value and does not derive."),
    ("S03", 1): (KEEP, "example code variable", "received_interval is a local variable in the example code of Appendix A.3, not in any RTCP packet or XR block; the method given by the RFC is the difference of the extended highest sequence numbers of two reports minus the difference of cumulative packets lost (§6.4.4), which is a combination of multiple fields. In the third version, two checkers agreed on this judgment."),
    ("S05", 1): (KEEP, "expected packet count", "The source code cited by the engineer already states: sp->packet_count is the highest sequence number so far, and packets is the increment of the highest sequence number within the interval, that is, the expected packet count, including lost packets; the actual received count must further subtract lost_packets."),
    ("S05", 9): (KEEP, "jitter definition", JIT + "The iperf3 source comments state it is computed per RFC 1889, sp->jitter += (d - sp->jitter)/16."),
    ("S06", 2): (KEEP, "in-order delivered bytes", "Kernel comment \"sum(delta(rcv_nxt)), or how many bytes were acked\"; in tcp_input.c, bytes_received accumulates as rcv_nxt advances: duplicate segments are not counted, and out-of-order bytes that arrive early are counted only after the hole is filled. In a window with loss or reordering, it differs from the bytes received in the window by a time-varying amount that cannot be removed by multiplying by a constant. The third version judges on this basis that the definition is different."),
    ("S07", 0): (KEEP, "Given by the sender or the server", "twcc-stats is updated only at the sender when parsing received TWCC feedback (gstrtpsession.c calls rtp_session_process_twcc only upon receiving RTPFB TWCC), and is not produced at the receiver; the note lists values measured at the sender or reported by the peer as different definition."),
    ("S07", 9): (KEEP, "jitter definition", JIT + "avg-jitter source is avg = (diff + 15*avg) >> 4."),
    ("S08", 10): (KEEP, "Given by the sender or the server", f"The current reason is that the document does not state the value range and the coefficient cannot be fixed; after checking the source code the reason is stronger. {AGORA}: the remote video currentPacketLossRate = B_evlr4/100, B_evlr4 comes from the TRAFFIC_STATS reply packet that the client requests from the Agora gateway via signaling every 3 seconds (peer_delay list, the same entry also has end-to-end delays B_ed, B_vd), not measured by the browser on the received stream; the SDK built-in network test multiplies this value by 100 and uses it as a percentage, which shows the field itself is a ratio from 0 to 1. So it is a value given by the server, and by the description it is judged a different definition; even if counted as the same, the coefficient is 1, and the engineer's 0.01 is wrong."),
    ("S09", 9): (KEEP, "jitter definition", JIT + "The SDK source code getstats.js multiplies the browser statistics jitter by 1000 and rounds."),
    ("S12", 9): (KEEP, "jitter definition", JIT + "The source code cited by the engineer is the 1/16 smoothing."),
    ("S13", 9): (KEEP, "jitter definition", JIT + "Filled in from the interceptor's receive statistics, original text \"packet jitter measured in seconds\", synonymous with W3C."),
    ("S14", 9): (KEEP, "jitter definition", JIT + "The field description is \"RFC 3550 A.8 Interarrival Jitter\"."),
    ("S15", 0): (KEEP, "entire-segment average", "The server source code computes bytes×8÷elapsed; elapsed is the entire statistical period from start_time to end_time, so it is an average over the entire period, not the rate within the window; it is not a cumulative counter, and differencing also cannot yield a within-window value."),
    ("S15", 2): (KEEP, "excluding duplicates and padding", "The server only accumulates bytes on non-duplicate, non-padding-only packets; duplicate and padding bytes are recorded separately in bytes_duplicate and bytes_padding; all bytes received within the window must be the sum of the three, which is a multi-field combination. The engineer's basis cited only the proto declaration and did not look at the algorithm."),
    ("S15", 9): (KEEP, "jitter definition", JIT + "The server applies 1/16 smoothing per RFC 3550 and then converts to microseconds; the engineer's coefficient of 1 is also wrong."),
    ("S15", 10): (KEEP, "entire-segment average", "Cumulative packet loss percentage over the entire segment (packetsLost ÷ packetsExpected × 100); a ratio cannot be differenced, so the within-window ratio cannot be obtained."),
    ("S16", 10): (KEEP, "multi-field combination", "The engineer wrote in the rationale that it should be divided by pktRecvTotal; this is a combination of two fields, which indicates a different definition, so the coefficient 1 filled in does not hold either; the original text also says missing includes out-of-order packets not yet arrived."),
    ("S18", 9): (KEEP, "jitter definition", JIT + "The Teams CQD value is still the whole-session average."),
    ("S18", 10): (KEEP, "entire-segment average", "original text \"Average packet loss rate for stream. Values grouped by range.\": it is the average over the whole session, and the dimension values are grouped by range; after grouping, multiplying by a constant cannot restore the in-window packet loss rate."),
    ("S19", 9): (KEEP, "jitter definition", JIT + "Only the audio receive report carries this value, taken from jitter_ms of the RTP receive statistics."),
}
DEBATABLE = [("S08", 0), ("S08", 2), ("S10", 0), ("S14", 2), ("S17", 5)]


def main():
    res = json.load(open(OUT / "result.json")); cells = {(c["page"], c["k"]): c for c in res["cells"]}
    # Disagreement cells: scored cells without agreement, plus cells labelled same quantity whose ground truth is not.
    dis = [c for c in res["cells"] if (c["truth"] in ("same", "none") and not c["agree"]) or (c["label"] == "same" and c["truth"] != "same")]
    keys = {(c["page"], c["k"]) for c in dis}
    assert keys == set(R), {"missing adjudication": sorted(keys - set(R)), "extra": sorted(set(R) - keys)}
    assert all(v[0] in (KEEP, "The annotator is correct", "changed to different definition, not scored") for v in R.values()) and set(DEBATABLE) <= set(R)
    rows = []
    for (p, k), (verdict, cat, basis) in sorted(R.items()):
        c = cells[(p, k)]
        sec = "one" if c["truth"] == "same" else "two" if c["truth"] == "none" else "three"
        rows.append({"page": p, "page_name": c["page_name"], "k": k, "section": sec, "truth": c["truth"], "truth_field": c.get("truth_field"), "truth_diff": c.get("truth_diff"),
                     "truth_scale": c.get("truth_scale"), "label": c["label"], "label_field": c["field"], "label_diff": c["diff"], "label_scale": c["scale"], "confidence": c["confidence"],
                     "verdict": verdict, "category": cat, "basis": basis})
    vc = Counter(r["verdict"] for r in rows); cc = Counter(r["category"] for r in rows)
    out = {"n": len(rows), "by_section": dict(Counter(r["section"] for r in rows)), "verdicts": dict(vc), "categories": dict(cc), "truth_changes": [r for r in rows if r["verdict"] != KEEP],
           "decided_by": "Adjudicated against the official text and source code by the LLM; rule fixed on 2026-10-04", "scope_note": "The 127 cells where the current ground truth says the definition differs and the engineer chose no counterpart field are reported only, as pre-registered, and were not checked cell by cell", "rows": rows}
    (OUT / "adjudication.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    L = ["# Cell-by-cell adjudication of blind label disagreements (gt-blind-expert-v1, 2026-10-04)", "",
         "Rule fixed on 2026-10-04: where the engineer and the ground truth disagree, the verdict follows the official text and source code. This file is generated by scripts/paper/gt_blind_adjudicate_v1.py; the script asserts that each of the 38 cells in disagreements.md has a verdict.", "",
         f"The SDK 4.24.8 source code referenced by each cell is taken from {AGORA_PKG}, checking AgoraRTC_N-production.js.", "",
         f"## Conclusion", "",
         f"In all 38 cells the current answer stands: no cell is corrected, no method needs to be rescored, and Table III, Figure 5, Figure 6 and Table S6 are unchanged. Main readings, unchanged: agreement on 68 of the 84 scored cells (0.810); three-class agreement over the 285 cells 0.439, kappa 0.222.", "",
         "Error categories:" + ",".join(f"{k} {v}" for k, v in cc.most_common()) + ".", "",
         "Notes:", "",
         f"- The largest category is jitter, {cc['jitter definition']} cells. The explanation states that it is judged by the standard deviation of arrival intervals within the window, while the engineer still judged it the same quantity under the usual RFC 3550 jitter. This concerns how the criterion is applied, not the answer.",
         f"- The second category is cumulative counters, {cc['Difference allowed'] + cc['cumulative within window'] + cc['Different quantity']} cells in total: {cc['Difference allowed']} cells where differencing is allowed but judged different definition, {cc['cumulative within window']} cells where a cumulative value is treated as a within-window value, and another {cc['Different quantity']} cells where a byte field is filled in for a packet count.",
         f"- Fields on the page that the engineer overlooked, {cc['Missed field']} cells: Twilio packetsReceived, Janus bytes_lastsec, SRT mbpsRecvRate.",
         f"- Four questions are genuinely open to discussion, {len(DEBATABLE)} cells, with the reasons given in the cells below: Agora combined audio and video bitrate and bytes, the two Daily rate fields, the two Janus byte fields, and the ns-3 minimum latency without clock offset. Under the existing criteria all keep the current answers; the fields the engineer chose for the Daily and Janus cells measure similar quantities but are not the closest ones.",
         "- Agora currentPacketLossRate one cell; after checking the SDK source code it was found to be a value given by the server, so the reason for the current different definition is changed from \"the coefficient cannot be determined\" to the harder \"it is not measured at the receiver\".", "",
         "Cells not checked one by one: the 127 cells where the current answer is different definition and the engineer chose no counterpart. They are not scored in the first place, and their effect on the method comparison is bounded by the existing sensitivity analysis: when every different-definition cell is scored as none, the seven specifications give Delta +0.201 [+0.094, +0.345], the sensitivity analysis written in advance during the third revision (realtel_adapter_v1/revise_v3.json); the 12 client stacks give Delta +0.268 [+0.160, +0.394], an exploratory reading (realtel_scale_v1/kindmiss_explore.json) not used as evidence. The direction is unchanged in both places.", ""]
    for sec, title in (("one", "Ground truth same quantity, engineer disagrees"), ("two", "The current answer is none, the engineer disagrees"), ("three", "The engineer chose the same quantity, the current answer is a different definition")):
        L += [f"## {sec}, {title}", ""]
        for r in (x for x in rows if x["section"] == sec):
            cur = f"{r['truth_field']}, difference {'yes' if r['truth_diff'] else 'no'}, coefficient {r['truth_scale']:g}" if r["truth"] == "same" else {"none": "none", "kind": "different definition"}[r["truth"]]
            lab = {"same": "same quantity", "kind": "different definition", "none": "none"}.get(r["label"], r["label"])
            if r["label"] == "same":
                lab += f", {r['label_field']}, difference {'yes' if r['label_diff'] else 'no'}, coefficient {r['label_scale']:g}"
            L.append(f"- **{r['page']} {r['page_name']} feature {r['k']}** Current: {cur}; annotation: {lab} (confidence {r['confidence']}). Verdict: {r['verdict']}, {r['category']}. {r['basis']}")
        L.append("")
    (OUT / "adjudication-2026-10-04.md").write_text("\n".join(L))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
