#!/usr/bin/env python3
"""Validity check of one testbed run; a failed check marks the run invalid."""
import argparse
import gzip
import json
import re
import sys


def read_text(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", errors="replace") as f:
        return f.read()


def build_checks(row, expected_controls, min_duration_s,
                 transport_text=None, shape_text=None):
    measurement = row["measurement"]
    checks = {
        "all_control_stages": row["controls"]["n_applies"] == expected_controls,
        "measurement_duration": measurement["duration_s"] >= min_duration_s,
        # The estimator hook logs video RTP only.  A second observed SSRC is
        # normally RTX and may be absent in a clean run, so count is not a
        # media-presence gate.  Require an SDP-declared primary video SSRC.
        "primary_video_stream_present": bool(
            measurement.get("primary_video_ssrcs")
            and measurement.get("primary_video_packets", 0) > 0
        ),
        "exposure_valid": bool(row["decisions"].get("exposure_valid")),
    }
    if transport_text is not None:
        selected = re.findall(r"New selected connection:.*?:(udp|tcp):", transport_text)
        checks["final_transport_udp"] = bool(selected and selected[-1] == "udp")
    if shape_text is not None:
        packets = [int(x) for x in re.findall(r"Sent\s+\d+\s+bytes\s+(\d+)\s+pkt", shape_text)]
        checks["shaped_packets_nonzero"] = bool(packets and max(packets) > 0)
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("summary")
    ap.add_argument("--expected-controls", type=int, required=True)
    ap.add_argument("--min-duration-s", type=float, required=True)
    ap.add_argument("--transport-log")
    ap.add_argument("--shape-log")
    args = ap.parse_args()
    with open(args.summary) as f:
        row = json.load(f)
    transport_text = read_text(args.transport_log) if args.transport_log else None
    shape_text = read_text(args.shape_log) if args.shape_log else None
    checks = build_checks(row, args.expected_controls, args.min_duration_s,
                          transport_text, shape_text)
    print(json.dumps(checks, sort_keys=True))
    if not all(checks.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
