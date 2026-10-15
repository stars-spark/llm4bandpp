#!/usr/bin/env python3
"""Probe whether frame-number labels survive an AlphaRTC decoded YUV capture: tesseract reads the burned-in number of each decoded frame into a CSV and a JSON summary.
Version 2: copy of audit_frame_label_ocr.py with --jobs N, which runs the per-frame tesseract calls in N threads and collects the results in frame order; --jobs 1 (default)
is the serial v1. Called by qoe_quality_once_v2.py, the scorer of the 320x240 batches.
Usage: audit_frame_label_ocr_v2.py --decoded FILE --width W --height H --reference-frames N --out-csv C --out-json J [--jobs K]
"""

import argparse
import csv
import io
import json
import re
import subprocess
from pathlib import Path

from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded", required=True, type=Path)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--reference-frames", required=True, type=int)
    parser.add_argument("--out-csv", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()

    frame_bytes = args.width * args.height * 3 // 2
    encoded = args.decoded.read_bytes()
    if encoded.startswith(b"YUV4MPEG2 "):
        completed = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(args.decoded), "-pix_fmt", "yuv420p",
             "-f", "rawvideo", "pipe:1"],
            stdout=subprocess.PIPE, check=True,
        )
        raw = completed.stdout
        input_container = "y4m"
    else:
        raw = encoded
        input_container = "raw-i420"
    if len(raw) % frame_bytes:
        raise ValueError("decoded YUV contains a partial frame")
    def ocr_one(index):
        offset = index * frame_bytes
        luma = raw[offset:offset + args.width * args.height]
        image = Image.frombytes("L", (args.width, args.height), luma)
        crop = image.crop((0, int(args.height * 0.6875), args.width, args.height))
        crop = crop.resize((args.width * 2, int(args.height * 0.625)))
        encoded = io.BytesIO()
        crop.save(encoded, format="PNG")
        completed = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "12", "-c",
             "tessedit_char_whitelist=0123456789"],
            input=encoded.getvalue(), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False,
        )
        return completed.stdout.decode(errors="replace").strip()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, args.jobs)) as pool:
        texts = list(pool.map(ocr_one, range(len(raw) // frame_bytes)))
    rows = []
    for index in range(len(raw) // frame_bytes):
        text = texts[index]
        digits = "".join(re.findall(r"\d+", text))
        value = int(digits) if digits else None
        valid = value is not None and 1 <= value <= args.reference_frames
        rows.append({
            "decoded_frame_index": index,
            "ocr_text": text,
            "ocr_label": value,
            "label_in_reference_range": valid,
        })

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    valid_count = sum(row["label_in_reference_range"] for row in rows)
    summary = {
        "decoded_path": str(args.decoded.resolve()),
        "decoded_frames": len(rows),
        "reference_frames": args.reference_frames,
        "input_container": input_container,
        "ocr_in_range_frames": valid_count,
        "ocr_in_range_fraction": valid_count / len(rows),
        "method": "bottom-31.25%-crop, 2x resize, tesseract 5 psm12 digits-only",
        "interpretation": (
            "This is a calibration probe. OCR labels are not render timestamps "
            "and must not be reported as W3C freezeCount."
        ),
    }
    args.out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
