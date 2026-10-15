#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Frame-number label OCR for the 720p batches (tesseract 5, psm 12, digits only, frame by frame as in v2).
Version 3: copy of v2 with three changes: --label-y gives the first row of the label band (576 or 480 for the 720p sources) and the whole band below it is read (v2 fixed 68.75%
of the height); --scale is the resize factor before tesseract (default 0.5, the 720p band has 144 rows); frames are read one at a time (Y4M frames located by their headers).
--expect-offset reports the exact-hit rate for offline checks. Called by qoe_quality_once_v3.py; --selftest includes a band start set too low, where the hit rate must drop.
Usage: audit_frame_label_ocr_v3.py --decoded FILE(.y4m or headerless yuv) --width W --height H --label-y Y --reference-frames N --out-csv C --out-json J [--jobs K] [--scale S] [--expect-offset 1]
"""
import argparse, csv, io, json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def frame_offsets(path, frame_bytes):
    """Return the byte offset of every frame's data: Y4M frames are found by their frame headers, headerless files are split by frame size."""
    size = path.stat().st_size
    with path.open("rb") as h:
        head = h.read(512)
        if not head.startswith(b"YUV4MPEG2 "):
            if size % frame_bytes: raise ValueError("raw YUV contains a partial frame")
            return [i * frame_bytes for i in range(size // frame_bytes)], "raw-i420"
        pos = head.find(b"\n") + 1; out = []
        while pos < size:
            h.seek(pos); m = h.read(128); e = m.find(b"\n")
            if e < 0 or not m.startswith(b"FRAME"): break
            if pos + e + 1 + frame_bytes > size: break
            out.append(pos + e + 1); pos = pos + e + 1 + frame_bytes
        return out, "y4m"


def ocr_band(luma_band, width, band_h, scale):
    from PIL import Image
    img = Image.frombytes("L", (width, band_h), luma_band)
    if scale != 1.0: img = img.resize((max(1, int(width * scale)), max(1, int(band_h * scale))))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "12", "-c", "tessedit_char_whitelist=0123456789"], input=buf.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return r.stdout.decode(errors="replace").strip()


def run(decoded, width, height, label_y, ref_frames, jobs=1, scale=0.5, expect_offset=None):
    fb = width * height * 3 // 2; offs, kind = frame_offsets(decoded, fb); band_h = height - label_y
    if not (0 < label_y < height): raise ValueError("label_y out of range")

    def one(i):
        with decoded.open("rb") as h:
            h.seek(offs[i] + label_y * width); band = h.read(width * band_h)
        return ocr_band(band, width, band_h, scale)
    with ThreadPoolExecutor(max(1, jobs)) as pool: texts = list(pool.map(one, range(len(offs))))
    rows = []
    for i, t in enumerate(texts):
        d = "".join(re.findall(r"\d+", t)); v = int(d) if d else None
        row = {"decoded_frame_index": i, "ocr_text": t, "ocr_label": v, "label_in_reference_range": v is not None and 1 <= v <= ref_frames}
        if expect_offset is not None: row["expected_label"] = i + expect_offset; row["exact"] = v == i + expect_offset
        rows.append(row)
    n = len(rows); ok = sum(r["label_in_reference_range"] for r in rows)
    summ = {"decoded_path": str(decoded.resolve()), "decoded_frames": n, "reference_frames": ref_frames, "input_container": kind, "ocr_in_range_frames": ok,
            "ocr_in_range_fraction": ok / n if n else 0.0, "label_y": label_y, "scale": scale, "width": width, "height": height,
            "method": f"label band rows {label_y}..{height}, resize x{scale}, tesseract 5 psm12 digits-only"}
    if expect_offset is not None: summ["exact_fraction"] = sum(r["exact"] for r in rows) / n if n else 0.0
    return rows, summ


def selftest():
    import os, tempfile
    d = Path(tempfile.mkdtemp()); src = d / "lab.yuv"; W, H, Y = 640, 360, 288
    vf = (f"drawbox=x=0:y={Y}:w=iw:h=ih-{Y}:color=black@1:t=fill,"
          f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf:text='%{{eif\\:n+1\\:d\\:6}}':fontcolor=white:fontsize=56:x=(w-text_w)/2:y={Y}+(72-th)/2")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={W}x{H}:rate=30", "-frames:v", "12", "-vf", vf, "-pix_fmt", "yuv420p", "-f", "rawvideo", str(src)], check=True)
    _, s = run(src, W, H, Y, 300, jobs=4, scale=1.0, expect_offset=1)
    assert s["exact_fraction"] >= 0.9, s
    _, bad = run(src, W, H, H - 16, 300, jobs=4, scale=1.0, expect_offset=1)
    assert bad["exact_fraction"] < 0.5, bad
    y4m = d / "lab.y4m"; subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}", "-i", str(src), "-pix_fmt", "yuv420p", str(y4m)], check=True)
    _, s2 = run(y4m, W, H, Y, 300, jobs=4, scale=1.0, expect_offset=1)
    assert s2["decoded_frames"] == 12 and s2["exact_fraction"] == s["exact_fraction"], s2
    print(f"OCR self-test passed: hit rate {s['exact_fraction']:.2f} at the correct band start, Y4M equals the headerless file; wrong band start rejected (hit rate {bad['exact_fraction']:.2f})")


def main():
    if "--selftest" in sys.argv: selftest(); return
    ap = argparse.ArgumentParser()
    ap.add_argument("--decoded", required=True, type=Path); ap.add_argument("--width", type=int, required=True); ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--label-y", type=int, required=True); ap.add_argument("--reference-frames", type=int, required=True)
    ap.add_argument("--out-csv", required=True, type=Path); ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=1); ap.add_argument("--scale", type=float, default=0.5); ap.add_argument("--expect-offset", type=int, default=None)
    a = ap.parse_args()
    rows, summ = run(a.decoded, a.width, a.height, a.label_y, a.reference_frames, a.jobs, a.scale, a.expect_offset)
    a.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with a.out_csv.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    a.out_json.write_text(json.dumps(summ, indent=2, sort_keys=True) + "\n", encoding="utf-8"); print(json.dumps(summ, sort_keys=True))


if __name__ == "__main__":
    main()
