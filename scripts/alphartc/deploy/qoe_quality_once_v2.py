#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Video quality of one run as qoe_quality_once_v1.py, with optional parallelism: --ocr-jobs N runs frame OCR in parallel through audit_frame_label_ocr_v2.py and --vmaf-threads N
sets vmaf threads. Per-frame computation and aggregation are unchanged; without the two options it behaves as v1.
Copy of v1. The scorer (quality_script of parallel_testbed_v1.py) of the 320x240 batches: obsschema-closedloop-v2, obsschema-closedloop-nl-v1, the 100 to 400 kbit/s batches
of Fig. 4(c) and content320-ch-gcc-v1.
Usage: qoe_quality_once_v2.py DECODED.y4m SOURCE.yuv OUT.json [--keep] [--step N] [--ocr-jobs N] [--vmaf-threads N]
"""
import json, subprocess, sys, tempfile
from pathlib import Path
import statistics as st
ROOT = Path(__file__).resolve().parents[3]; W, H, ROI = 320, 240, 160
OCR_JOBS = int(sys.argv[sys.argv.index("--ocr-jobs") + 1]) if "--ocr-jobs" in sys.argv else 1
VMAF_THREADS = int(sys.argv[sys.argv.index("--vmaf-threads") + 1]) if "--vmaf-threads" in sys.argv else 1
VMAF_BIN = Path("/path/to/tools/vmaf-3.2.0-f85a853-install/bin/vmaf"); VMAF_MODEL = Path("/path/to/tools/vmaf-f85a853/model/vmaf_v0.6.1.json")


def read_source(src):
    return src.read_bytes()


def ocr_map(decoded, tmp, step):
    c, j = tmp / "ocr.csv", tmp / "ocr.json"
    src = decoded
    if step > 1:
        src = tmp / "sub.y4m"; subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(decoded), "-vf", "select=not(mod(n\\,%d))" % step, "-vsync", "0", "-pix_fmt", "yuv420p", str(src)], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/alphartc/audit_frame_label_ocr_v2.py"), "--jobs", str(OCR_JOBS), "--decoded", str(src), "--width", str(W), "--height", str(H), "--reference-frames", "630", "--out-csv", str(c), "--out-json", str(j)], check=True, stdout=subprocess.DEVNULL)
    globals()["_SUB"] = src
    import csv
    rows = list(csv.DictReader(open(c))); info = json.loads(j.read_text()); out = []
    for r in rows:
        v = r.get("ocr_label") or r.get("label") or r.get("ocr") or ""
        out.append(int(v) if str(v).strip().isdigit() else None)
    return out, info


def metric(ref, dist, name, tmp):
    stats = tmp / f"{name}.log"
    graph = f"[0:v]crop={W}:{ROI}:0:0[r];[1:v]crop={W}:{ROI}:0:0[d];[r][d]{name}=stats_file={stats}"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}", "-i", str(ref), "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}", "-i", str(dist), "-lavfi", graph, "-f", "null", "-"], check=True)
    key = "All:" if name == "ssim" else "psnr_avg:"
    vals = []
    for line in stats.read_text().splitlines():
        for tok in line.split():
            if tok.startswith(key):
                v = tok.split(":")[1].split("(")[0]
                try: vals.append(float(v))
                except ValueError: pass
    return (st.mean(vals) if vals else None), len(vals)


def vmaf(ref, dist, n, tmp):
    if not (VMAF_BIN.is_file() and VMAF_MODEL.is_file()): return None
    up = []
    for src, dst in ((ref, tmp / "ref1080.yuv"), (dist, tmp / "dist1080.yuv")):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}", "-i", str(src), "-vf", f"crop={W}:{ROI}:0:0,scale=1920:1080:flags=bicubic", "-pix_fmt", "yuv420p", "-f", "rawvideo", str(dst)], check=True); up.append(dst)
    out = tmp / "vmaf.json"
    subprocess.run([str(VMAF_BIN), "-r", str(up[0]), "-d", str(up[1]), "-w", "1920", "-h", "1080", "-p", "420", "-b", "8", "--model", f"path={VMAF_MODEL}:name=v", "--json", "-o", str(out)] + (["--threads", str(VMAF_THREADS)] if VMAF_THREADS > 1 else []), check=True, stdout=subprocess.DEVNULL)
    fr = json.loads(out.read_text())["frames"]; return st.mean(f["metrics"]["v"] for f in fr) if fr else None


def main():
    decoded, source, outp = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]); keep = "--keep" in sys.argv
    step = int(sys.argv[sys.argv.index("--step") + 1]) if "--step" in sys.argv else 4
    res = {"decoded": decoded.name, "source": source.name, "frame_step": step}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            labels, info = ocr_map(decoded, tmp, step); res["ocr"] = {k: info[k] for k in ("decoded_frames", "ocr_in_range_fraction", "ocr_in_range_frames") if k in info}
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(_SUB), "-pix_fmt", "yuv420p", "-f", "rawvideo", "pipe:1"], stdout=subprocess.PIPE, check=True).stdout
            fs = W * H * 3 // 2; src = read_source(source); ref_b, dist_b, used, seq = bytearray(), bytearray(), 0, []
            for i, lab in enumerate(labels):
                if lab is None or lab < 1 or lab * fs > len(src) or (i + 1) * fs > len(raw): continue
                ref_b += src[(lab - 1) * fs: lab * fs]; dist_b += raw[i * fs:(i + 1) * fs]; used += 1; seq.append(lab)
            res["paired_frames"] = used
            if used >= 30:
                rp, dp = tmp / "ref.yuv", tmp / "dist.yuv"; rp.write_bytes(ref_b); dp.write_bytes(dist_b)
                res["ssim"], _ = metric(rp, dp, "ssim", tmp); res["psnr"], _ = metric(rp, dp, "psnr", tmp); res["vmaf"] = vmaf(rp, dp, used, tmp)
                gaps = [b - a - step for a, b in zip(seq, seq[1:]) if b > a]
                res["skipped_source_frames_per_100"] = 100.0 * sum(g for g in gaps if g > 0) / max(len(gaps), 1) / step
                res["skip_events_gt2"] = sum(1 for g in gaps if g >= 2 * step); res["n_wraps"] = sum(1 for a, b in zip(seq, seq[1:]) if b < a)
                res["rendered_fps"] = round(info.get("decoded_frames", used) * step / 129.0, 2)
                res["label_span"] = [min(seq), max(seq)]
            else: res["error"] = "Fewer than 30 pairable frames"
        except Exception as e: res["error"] = f"{type(e).__name__}: {e}"
    outp.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if not keep and decoded.is_file() and "error" not in res: decoded.unlink()
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
