#!/usr/bin/env python3
"""Compute classic ITU-T P.910 SI/TI from an 8-bit raw YUV420p source; acquire_freeze_paper_videos.sh uses it to order the 720p sources of the 320x240 sequences by temporal information (low, medium, high)."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics

import numpy as np


def sobel_sd(luma: np.ndarray) -> float:
    image = luma.astype(np.float32, copy=False)
    gx = (
        image[:-2, 2:] + 2 * image[1:-1, 2:] + image[2:, 2:]
        - image[:-2, :-2] - 2 * image[1:-1, :-2] - image[2:, :-2]
    )
    gy = (
        image[2:, :-2] + 2 * image[2:, 1:-1] + image[2:, 2:]
        - image[:-2, :-2] - 2 * image[:-2, 1:-1] - image[:-2, 2:]
    )
    return float(np.hypot(gx, gy).std())


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def compute(path: Path, width: int, height: int, frames: int) -> tuple[list[dict], dict]:
    luma_bytes = width * height
    frame_bytes = width * height * 3 // 2
    expected_minimum = frame_bytes * frames
    if path.stat().st_size < expected_minimum:
        raise ValueError(f"input has {path.stat().st_size} bytes, needs at least {expected_minimum}")
    rows = []
    previous = None
    with path.open("rb") as handle:
        for frame_index in range(frames):
            luma_raw = handle.read(luma_bytes)
            if len(luma_raw) != luma_bytes:
                raise ValueError(f"short luma read at frame {frame_index}")
            luma = np.frombuffer(luma_raw, dtype=np.uint8).reshape(height, width)
            si = sobel_sd(luma)
            ti = None if previous is None else float(
                (luma.astype(np.int16) - previous.astype(np.int16)).std()
            )
            rows.append({"frame_index": frame_index, "si": si, "ti": ti})
            previous = luma.copy()
            handle.seek(frame_bytes - luma_bytes, 1)
    si_values = [row["si"] for row in rows]
    ti_values = [row["ti"] for row in rows if row["ti"] is not None]
    summary = {
        "schema": "p910-si-ti-v1",
        "input": str(path),
        "width": width,
        "height": height,
        "pixel_format": "yuv420p 8-bit; SI/TI use luma only",
        "frames_analyzed": frames,
        "frame_range": [0, frames - 1],
        "si": {
            "mean": statistics.fmean(si_values),
            "median": statistics.median(si_values),
            "p95_nearest_rank": percentile(si_values, 0.95),
            "max": max(si_values),
        },
        "ti": {
            "mean": statistics.fmean(ti_values),
            "median": statistics.median(ti_values),
            "p95_nearest_rank": percentile(ti_values, 0.95),
            "max": max(ti_values),
        },
        "method": "classic P.910: per-frame Sobel-magnitude spatial SD and successive-luma-difference spatial SD; mean used for 2023-recommended aggregation",
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = compute(args.input, args.width, args.height, args.frames)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("frame_index", "si", "ti"))
        writer.writeheader()
        writer.writerows(rows)
    args.out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
