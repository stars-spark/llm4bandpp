#!/usr/bin/env python3
"""Record when complete frames become visible in a growing raw YUV file.
This is a host-side calibration probe for AlphaRTC's ``save_to_file`` output. It observes file growth, not WebRTC render times.
First version: frame size from --frame-bytes (default 320x240), Y4M frames located by reading the whole file. Started by the run scripts up to v11 when media is captured;
v12 and later use monitor_decoded_yuv_v2.py.
"""

import argparse
import bisect
import csv
import json
import signal
import statistics
import time
from pathlib import Path


RUNNING = True


def stop(_signum, _frame):
    global RUNNING
    RUNNING = False


def y4m_frame_end_offsets(path, frame_bytes):
    raw = path.read_bytes()
    header_end = raw.find(b"\n")
    if header_end < 0 or not raw.startswith(b"YUV4MPEG2 "):
        raise ValueError("capture is not a Y4M stream")
    position = header_end + 1
    ends = []
    while position < len(raw):
        marker_end = raw.find(b"\n", position)
        if marker_end < 0 or not raw[position:marker_end].startswith(b"FRAME"):
            break
        frame_end = marker_end + 1 + frame_bytes
        if frame_end > len(raw):
            break
        ends.append(frame_end)
        position = frame_end
    return ends, header_end + 1, len(raw) - position


def apply_framing(rows, capture_path, frame_bytes, capture_format):
    if capture_format == "raw":
        ends = list(range(frame_bytes, (capture_path.stat().st_size // frame_bytes + 1) * frame_bytes, frame_bytes))
        header_bytes = 0
        trailing_bytes = capture_path.stat().st_size % frame_bytes
    else:
        ends, header_bytes, trailing_bytes = y4m_frame_end_offsets(capture_path, frame_bytes)
    previous_complete = 0
    for row in rows:
        complete = bisect.bisect_right(ends, row["file_bytes"])
        row["complete_frames"] = complete
        row["delta_complete_frames"] = complete - previous_complete
        last_end = ends[complete - 1] if complete else header_bytes
        row["partial_frame_bytes"] = max(0, row["file_bytes"] - last_end)
        previous_complete = complete
    return len(ends), header_bytes, trailing_bytes


def summarise(rows, poll_interval_ms, capture_format, parsed_frames, header_bytes, trailing_bytes):
    growth = [row for row in rows if row["delta_complete_frames"] > 0]
    single = [row for row in growth if row["delta_complete_frames"] == 1]
    gaps_ms = [
        (right["monotonic_ns"] - left["monotonic_ns"]) / 1_000_000
        for left, right in zip(growth, growth[1:])
    ]
    return {
        "samples_with_file_change": len(rows),
        "complete_frame_growth_events": len(growth),
        "single_frame_growth_events": len(single),
        "single_frame_growth_fraction": len(single) / len(growth) if growth else 0.0,
        "observed_complete_frames": growth[-1]["complete_frames"] if growth else 0,
        "median_growth_gap_ms": statistics.median(gaps_ms) if gaps_ms else None,
        "p95_growth_gap_ms": (
            sorted(gaps_ms)[max(0, int(0.95 * len(gaps_ms)) - 1)] if gaps_ms else None
        ),
        "poll_interval_ms": poll_interval_ms,
        "capture_format": capture_format,
        "parsed_complete_frames": parsed_frames,
        "header_bytes": header_bytes,
        "trailing_bytes_after_complete_frame": trailing_bytes,
        "interpretation": (
            "Host-observed raw-file growth is a calibration proxy. It is not a "
            "decoder or renderer timestamp and must not be reported as W3C freezeCount."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--out-csv", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--frame-bytes", type=int, default=320 * 240 * 3 // 2)
    parser.add_argument("--poll-interval-ms", type=float, default=5.0)
    parser.add_argument("--capture-format", choices=("raw", "y4m"), default="raw")
    args = parser.parse_args()
    if args.frame_bytes <= 0 or args.poll_interval_ms <= 0:
        parser.error("frame bytes and poll interval must be positive")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    previous_size = 0
    previous_complete = 0
    while RUNNING:
        size = args.path.stat().st_size if args.path.exists() else 0
        if size != previous_size:
            complete = size // args.frame_bytes
            rows.append({
                "wall_time_ns": time.time_ns(),
                "monotonic_ns": time.monotonic_ns(),
                "file_bytes": size,
                "complete_frames": complete,
                "delta_bytes": size - previous_size,
                "delta_complete_frames": complete - previous_complete,
                "partial_frame_bytes": size % args.frame_bytes,
            })
            previous_size = size
            previous_complete = complete
        time.sleep(args.poll_interval_ms / 1000)

    parsed_frames, header_bytes, trailing_bytes = apply_framing(
        rows, args.path, args.frame_bytes, args.capture_format
    )
    fields = [
        "wall_time_ns", "monotonic_ns", "file_bytes", "complete_frames",
        "delta_bytes", "delta_complete_frames", "partial_frame_bytes",
    ]
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = summarise(
        rows, args.poll_interval_ms, args.capture_format,
        parsed_frames, header_bytes, trailing_bytes,
    )
    args.out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
