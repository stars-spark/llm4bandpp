#!/usr/bin/env python3
"""Build the paired AlphaRTC sender and receiver configs for one testbed run; called by the run scripts (staleness in the name: docs/GLOSSARY.md)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(
    sender_template: Path, receiver_template: Path, receiver_ip: str,
    source_file: str, fps: int, width: int, height: int,
    capture_media: bool, decoded_video: str,
) -> tuple[dict, dict]:
    if fps <= 0 or width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("fps and dimensions must be positive; yuv420p dimensions must be even")
    sender = json.loads(sender_template.read_text())
    receiver = json.loads(receiver_template.read_text())
    sender["serverless_connection"]["sender"]["dest_ip"] = receiver_ip
    source = sender["video_source"]["video_file"]
    source.update({"file_path": source_file, "fps": fps, "width": width, "height": height})
    receiver["save_to_file"] = {
        "enabled": capture_media,
        "audio": {"file_path": "/tmp/staleness_unused.wav"},
        "video": {
            "width": width, "height": height, "fps": fps,
            "file_path": decoded_video,
        },
    }
    return sender, receiver


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sender-template", type=Path, required=True)
    parser.add_argument("--receiver-template", type=Path, required=True)
    parser.add_argument("--receiver-ip", required=True)
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--capture-media", choices=("0", "1"), required=True)
    parser.add_argument("--decoded-video", required=True)
    parser.add_argument("--sender-out", type=Path, required=True)
    parser.add_argument("--receiver-out", type=Path, required=True)
    args = parser.parse_args()
    sender, receiver = build(
        args.sender_template, args.receiver_template, args.receiver_ip,
        args.source_file, args.fps, args.width, args.height,
        args.capture_media == "1", args.decoded_video,
    )
    args.sender_out.write_text(json.dumps(sender, indent=2, sort_keys=True) + "\n")
    args.receiver_out.write_text(json.dumps(receiver, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
