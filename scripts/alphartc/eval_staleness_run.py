#!/usr/bin/env python3
"""Evaluate one testbed run; the run scripts call it in the receiver container after each call.

The AlphaRTC bandwidth-estimator log contains video RTP packets.  SDP FID
groups identify the primary video and RTX SSRCs.  Network utility is computed
from the primary video stream so retransmissions are not rewarded as useful
rate.  The evaluator also audits the realised age of every bandwidth decision.
"""
import argparse
import gzip
import json
import math
import os
import re
import statistics


FID = re.compile(r"a=ssrc-group:FID\s+(\d+)\s+(\d+)")


def percentile(values, q):
    values = sorted(float(x) for x in values)
    if not values:
        return None
    pos = (len(values) - 1) * q / 100.0
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def mean(values):
    return statistics.fmean(values) if values else None


def read_lines(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", errors="replace") as f:
        yield from f


def json_from_line(line):
    start, end = line.find("{"), line.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(line[start:end + 1])
    except (TypeError, ValueError):
        return None


def load_packets(path):
    packets = []
    for line in read_lines(path):
        row = json_from_line(line)
        if not isinstance(row, dict) or "packetInfo" not in row:
            continue
        packet = row.get("packetInfo", {})
        header = packet.get("header", {})
        try:
            packets.append({
                "arrival_ms": float(packet["arrivalTimeMs"]),
                "send_ms": float(header["sendTimestamp"]),
                "ssrc": int(header["ssrc"]),
                "seq": int(header["sequenceNumber"]),
                "payload_type": int(header.get("payloadType", -1)),
                "payload_bytes": int(packet.get("payloadSize", 0)),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(packets, key=lambda x: x["arrival_ms"])


def load_fid_groups(path):
    """Return unique (primary video SSRC, RTX SSRC) pairs declared in SDP."""
    groups = []
    seen = set()
    for line in read_lines(path):
        for primary, rtx in FID.findall(line):
            pair = (int(primary), int(rtx))
            if pair not in seen:
                seen.add(pair)
                groups.append(pair)
    return groups


def load_jsonl(path, event=None):
    if not path or not os.path.exists(path):
        return []
    rows = []
    for line in read_lines(path):
        row = json_from_line(line)
        if isinstance(row, dict) and (event is None or row.get("event") == event):
            rows.append(row)
    return rows


def target_at(controls, wall_ms):
    target = None
    for row in controls:
        if float(row["wall_time_ms"]) > wall_ms:
            break
        target = float(row["rate_kbps"])
    return target


def count_loss(packets):
    by_ssrc = {}
    for packet in packets:
        by_ssrc.setdefault(packet["ssrc"], []).append(packet)
    lost = received = duplicates = reordered = 0
    per_ssrc = {}
    for ssrc, rows in by_ssrc.items():
        last = None
        seen = set()
        stream_lost = stream_received = 0
        for row in rows:
            seq = row["seq"] & 0xFFFF
            if seq in seen:
                duplicates += 1
                continue
            seen.add(seq)
            stream_received += 1
            if last is None:
                last = seq
                continue
            step = (seq - last) & 0xFFFF
            if 1 < step < 32768:
                stream_lost += step - 1
                last = seq
            elif step == 1:
                last = seq
            elif step >= 32768:
                reordered += 1
        lost += stream_lost
        received += stream_received
        per_ssrc[str(ssrc)] = {
            "received_unique": stream_received,
            "inferred_lost": stream_lost,
        }
    denominator = received + lost
    return {
        "received_unique": received,
        "inferred_lost": lost,
        "loss_rate": lost / denominator if denominator else None,
        "duplicates": duplicates,
        "reordered": reordered,
        "per_ssrc": per_ssrc,
    }


def analyze(network_log, decision_trace=None, control_log=None, warmup_s=6.0,
            max_queue_ms=500.0, source_ceiling_kbps=240.0):
    all_packets = load_packets(network_log)
    fid_groups = load_fid_groups(network_log)
    if len(all_packets) < 2:
        raise ValueError("network log contains fewer than two packet records")
    controls = sorted(load_jsonl(control_log, "apply"),
                      key=lambda x: float(x["wall_time_ms"]))
    # AlphaRTC occasionally emits an initial packet with a non-wall-clock
    # arrival timestamp.  A single such row otherwise creates decades of empty
    # one-second bins.  Keep the dominant wall-clock cluster, and when controls
    # exist require packet timestamps to be near that run's control events.
    median_arrival = statistics.median(x["arrival_ms"] for x in all_packets)
    all_packets = [x for x in all_packets
                   if abs(x["arrival_ms"] - median_arrival) <= 3_600_000.0]
    if controls:
        lower = float(controls[0]["wall_time_ms"]) - 30_000.0
        upper = float(controls[-1]["wall_time_ms"]) + 120_000.0
        all_packets = [x for x in all_packets if lower <= x["arrival_ms"] <= upper]
    if len(all_packets) < 2:
        raise ValueError("fewer than two valid wall-clock packet records")
    start_ms = all_packets[0]["arrival_ms"] + warmup_s * 1000.0
    if controls:
        # In the two-container topology ICE is established before shaping.
        # Warm-up starts at the first applied network control, not at the first
        # unshaped media packet.
        start_ms = max(start_ms, float(controls[0]["wall_time_ms"]) + warmup_s * 1000.0)
    packets = [x for x in all_packets if x["arrival_ms"] >= start_ms]
    if len(packets) < 2:
        raise ValueError("fewer than two packets remain after warm-up")
    end_ms = packets[-1]["arrival_ms"]
    duration_s = (end_ms - start_ms) / 1000.0
    if duration_s <= 0:
        raise ValueError("non-positive measurement duration")

    observed_ssrcs = {x["ssrc"] for x in packets}
    primary_ssrcs = {primary for primary, _ in fid_groups if primary in observed_ssrcs}
    rtx_ssrcs = {rtx for _, rtx in fid_groups if rtx in observed_ssrcs}
    primary_packets = [x for x in packets if x["ssrc"] in primary_ssrcs]
    rtx_packets = [x for x in packets if x["ssrc"] in rtx_ssrcs]
    # Keep enough output for diagnosis if SDP parsing fails; the validity gate
    # will reject the run because no declared primary video SSRC was observed.
    metric_packets = primary_packets or packets

    # Clock offset is stream-specific.  Subtract each SSRC's minimum raw delay.
    raw_min = {}
    for p in all_packets:
        raw = p["arrival_ms"] - p["send_ms"]
        raw_min[p["ssrc"]] = min(raw_min.get(p["ssrc"], raw), raw)
    queue_delays = [
        max(0.0, p["arrival_ms"] - p["send_ms"] - raw_min[p["ssrc"]])
        for p in metric_packets
    ]
    primary_payload_bytes = sum(p["payload_bytes"] for p in primary_packets)
    rtx_payload_bytes = sum(p["payload_bytes"] for p in rtx_packets)
    observed_payload_bytes = sum(p["payload_bytes"] for p in packets)
    primary_payload_rate_kbps = primary_payload_bytes * 8.0 / duration_s / 1000.0
    rtx_payload_rate_kbps = rtx_payload_bytes * 8.0 / duration_s / 1000.0
    observed_payload_rate_kbps = observed_payload_bytes * 8.0 / duration_s / 1000.0
    loss = count_loss(metric_packets)
    all_video_loss = count_loss(packets)

    # One-second bins make the rate score sensitive to outages as well as to the mean rate.
    bin_scores = []
    bin_start = start_ms
    while bin_start + 1000.0 <= end_ms:
        nbytes = sum(p["payload_bytes"] for p in primary_packets
                     if bin_start <= p["arrival_ms"] < bin_start + 1000.0)
        measured = nbytes * 8.0 / 1000.0
        target = target_at(controls, bin_start + 500.0) if controls else None
        if target and target > 0:
            ideal = min(target, source_ceiling_kbps)
            bin_scores.append(min(1.0, measured / ideal))
        bin_start += 1000.0
    rate_score = mean(bin_scores)
    delay_score = max(0.0, 1.0 - mean(queue_delays) / max_queue_ms)
    network_utility = None
    if rate_score is not None and loss["loss_rate"] is not None:
        network_utility = 100.0 * (
            0.4 * rate_score + 0.4 * delay_score + 0.2 * (1.0 - loss["loss_rate"])
        )

    postwarm_decisions = [
        x for x in load_jsonl(decision_trace, "bwe_decision")
        if float(x.get("applied_wall_ms", 0)) >= start_ms
    ]
    decisions = [x for x in postwarm_decisions if not x.get("startup_fallback")]
    state_ages = [float(x["state_age_ms"]) for x in decisions]
    wall_ages = [float(x["wall_age_ms"]) for x in decisions]
    compute = [float(x["current_compute_ms"]) for x in decisions]
    age_requested = float(decisions[0]["requested_delay_ms"]) if decisions else None
    excess_ages = [x - age_requested for x in state_ages] if age_requested is not None else []
    decision_gaps = [
        float(postwarm_decisions[i]["applied_wall_ms"])
        - float(postwarm_decisions[i - 1]["applied_wall_ms"])
        for i in range(1, len(postwarm_decisions))
    ]
    age_not_younger = bool(
        state_ages and age_requested is not None
        and all(x + 1e-6 >= age_requested for x in state_ages)
    )
    exposure_valid = bool(postwarm_decisions and
                          len(decisions) == len(postwarm_decisions) and
                          age_not_younger)

    tracking = []
    for row in decisions:
        cap = target_at(controls, float(row["applied_wall_ms"])) if controls else None
        if cap and cap > 0:
            estimate = float(row["applied_bandwidth_bps"]) / 1000.0
            tracking.append({
                "estimate_kbps": estimate,
                "capacity_kbps": cap,
                "over_ratio": max(0.0, estimate - cap) / cap,
                "under_ratio": max(0.0, cap - estimate) / cap,
            })

    return {
        "schema": "staleness-run-v2",
        "measurement": {
            "warmup_s": warmup_s,
            "duration_s": duration_s,
            "packets": len(packets),
            "ssrcs": len(observed_ssrcs),
            "sdp_fid_groups": [list(x) for x in fid_groups],
            "observed_ssrcs": sorted(observed_ssrcs),
            "primary_video_ssrcs": sorted(primary_ssrcs),
            "rtx_video_ssrcs": sorted(rtx_ssrcs),
            "unclassified_ssrcs": sorted(observed_ssrcs - primary_ssrcs - rtx_ssrcs),
            "primary_video_packets": len(primary_packets),
            "rtx_video_packets": len(rtx_packets),
        },
        "network": {
            "primary_video_payload_rate_kbps": primary_payload_rate_kbps,
            "rtx_video_payload_rate_kbps": rtx_payload_rate_kbps,
            "observed_video_payload_rate_kbps": observed_payload_rate_kbps,
            "queue_delay_mean_ms": mean(queue_delays),
            "queue_delay_p95_ms": percentile(queue_delays, 95),
            "queue_delay_p99_ms": percentile(queue_delays, 99),
            "loss": loss,
            "all_video_ssrc_loss": all_video_loss,
            "rate_score_1s": rate_score,
            "delay_score": delay_score,
            "utility": network_utility,
        },
        "decisions": {
            "n": len(decisions),
            "requested_delay_ms": age_requested,
            "state_age_p50_ms": percentile(state_ages, 50),
            "state_age_p95_ms": percentile(state_ages, 95),
            "state_age_min_ms": min(state_ages) if state_ages else None,
            "state_age_max_ms": max(state_ages) if state_ages else None,
            "excess_age_p50_ms": percentile(excess_ages, 50),
            "excess_age_p95_ms": percentile(excess_ages, 95),
            "wall_age_p50_ms": percentile(wall_ages, 50),
            "compute_p50_ms": percentile(compute, 50),
            "compute_p95_ms": percentile(compute, 95),
            "decision_gap_p50_ms": percentile(decision_gaps, 50),
            "decision_gap_p95_ms": percentile(decision_gaps, 95),
            "startup_fallback_after_warmup": len(postwarm_decisions) - len(decisions),
            "state_age_never_younger_than_requested": age_not_younger,
            "exposure_valid": exposure_valid,
            "mean_over_ratio": mean([x["over_ratio"] for x in tracking]),
            "mean_under_ratio": mean([x["under_ratio"] for x in tracking]),
        },
        "controls": {"n_applies": len(controls)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--network-log", required=True)
    ap.add_argument("--decision-trace")
    ap.add_argument("--control-log")
    ap.add_argument("--warmup-s", type=float, default=6.0)
    ap.add_argument("--max-queue-ms", type=float, default=500.0)
    ap.add_argument("--source-ceiling-kbps", type=float, default=240.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    result = analyze(args.network_log, args.decision_trace, args.control_log,
                     args.warmup_s, args.max_queue_ms, args.source_ceiling_kbps)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
