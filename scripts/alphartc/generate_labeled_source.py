#!/usr/bin/env python3
"""Generate a reproducible raw YUV source with fixed-position frame labels."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument(
        "--font",
        type=Path,
        default=Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
    )
    args = parser.parse_args()
    if args.frames <= 0 or args.fps <= 0:
        parser.error("frames and fps must be positive")
    for path in (args.input, args.font):
        if not path.is_file():
            parser.error(f"missing input: {path}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    label_y = int(args.height * 2 / 3)
    font_size = max(24, int(args.height * 0.217))
    filter_graph = (
        f"fps={args.fps},scale={args.width}:{args.height},"
        f"drawbox=x=0:y={label_y}:w=iw:h=ih-{label_y}:color=black@1:t=fill,"
        f"drawtext=fontfile={args.font}:text='%{{eif\\:n+1\\:d\\:6}}':"
        f"fontcolor=white:fontsize={font_size}:x=(w-text_w)/2:y={label_y + 10}"
    )
    command = [
        "ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(args.input),
        "-vf", filter_graph, "-frames:v", str(args.frames), "-pix_fmt", "yuv420p",
        "-f", "rawvideo", str(args.output),
    ]
    subprocess.run(command, check=True)
    expected_bytes = args.frames * args.width * args.height * 3 // 2
    actual_bytes = args.output.stat().st_size
    if actual_bytes != expected_bytes:
        raise RuntimeError(f"unexpected output size: {actual_bytes} != {expected_bytes}")
    metadata = {
        "input": str(args.input.resolve()),
        "input_sha256": sha256(args.input),
        "output": str(args.output.resolve()),
        "output_sha256": sha256(args.output),
        "width": args.width,
        "height": args.height,
        "pixel_format": "yuv420p",
        "fps": args.fps,
        "frames": args.frames,
        "label": "six-digit one-based frame number, fixed bottom black band",
        "font": str(args.font.resolve()),
        "ffmpeg_command": command,
    }
    args.metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
