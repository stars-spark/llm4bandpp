#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Video quality of one 720p run: OCR (audit_frame_label_ocr_v3.py) reads the burned-in source frame number, the matching source frame is paired and only the top label_y rows
are compared; ffmpeg computes SSIM and PSNR, vmaf 3.2.0 with vmaf_v0.6.1 computes VMAF after bicubic upscaling to 1920x1080; hit rate, skipped frames and per-frame VMAF are recorded.
Copy of v2 with the same metrics and pairing; frame size, label row, source frames, step, OCR scale and temporary directory are arguments (v2 fixed 320x240), the input is the
subsequence the v2 scheduler extracts, frames are read one at a time and fed to vmaf through named pipes, and the rendered frame rate uses --duration-s.
The scorer of parallel_testbed_v2.py, so of every 720p batch (Tables IV and V, Fig. 4(a)). --selftest scores a synthetic source, with two cases that must fail.
Usage: qoe_quality_once_v3.py SUB.y4m SOURCE.yuv OUT.json --width 1280 --height 720 --label-y 576 --ref-frames 300 --step 8 [--duration-s D] [--ocr-jobs N] [--vmaf-threads N] [--ocr-scale 0.5] [--tmpdir DIR] [--keep]
"""
import argparse, json, os, statistics as st, subprocess, sys, tempfile, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]; sys.path.insert(0, str(ROOT / "scripts/alphartc"))
import audit_frame_label_ocr_v3 as OCR  # noqa: E402
VMAF_BIN = Path("/path/to/tools/vmaf-3.2.0-f85a853-install/bin/vmaf"); VMAF_MODEL = Path("/path/to/tools/vmaf-f85a853/model/vmaf_v0.6.1.json")


def roi_bytes(frame, W, H, R):
    """Full yuv420p frame -> yuv420p frame of its top R rows (R even)."""
    y = frame[:W * R]; u0 = W * H; v0 = u0 + (W // 2) * (H // 2); cw = W // 2
    return y + frame[u0:u0 + cw * (R // 2)] + frame[v0:v0 + cw * (R // 2)]


def metric(ref, dist, name, tmp, W, R):
    stats = tmp / f"{name}.log"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{R}", "-i", str(ref), "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{R}", "-i", str(dist),
                    "-lavfi", f"[0:v][1:v]{name}=stats_file={stats}", "-f", "null", "-"], check=True)
    key = "All:" if name == "ssim" else "psnr_avg:"; vals = []
    for line in stats.read_text().splitlines():
        for tok in line.split():
            if tok.startswith(key):
                try: vals.append(float(tok.split(":")[1].split("(")[0]))
                except ValueError: pass
    return (st.mean(vals) if vals else None), len(vals)


def vmaf(ref, dist, tmp, W, R, threads):
    if not (VMAF_BIN.is_file() and VMAF_MODEL.is_file()): return None
    fifos = [tmp / "ref1080.fifo", tmp / "dist1080.fifo"]; procs = []
    for f in fifos:
        if f.exists(): f.unlink()
        os.mkfifo(f)
    for src, f in zip((ref, dist), fifos):
        procs.append(subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{R}", "-i", str(src), "-vf", "scale=1920:1080:flags=bicubic",
                                       "-pix_fmt", "yuv420p", "-f", "rawvideo", str(f)], stdin=subprocess.DEVNULL))
    out = tmp / "vmaf.json"
    r = subprocess.run([str(VMAF_BIN), "-r", str(fifos[0]), "-d", str(fifos[1]), "-w", "1920", "-h", "1080", "-p", "420", "-b", "8", "--model", f"path={VMAF_MODEL}:name=v", "--json", "-o", str(out)]
                       + (["--threads", str(threads)] if threads > 1 else []), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=1800)
    for p in procs:
        try: p.wait(timeout=60)
        except subprocess.TimeoutExpired: p.kill()
    if r.returncode != 0: raise RuntimeError(f"vmaf exit code {r.returncode}: {r.stderr.decode(errors='replace')[-300:]}")
    fr = json.loads(out.read_text())["frames"]; return (st.mean(f["metrics"]["v"] for f in fr) if fr else None), len(fr), [f["metrics"]["v"] for f in fr]


def score(sub, source, W, H, R, ref_frames, step, duration_s=None, ocr_jobs=1, vmaf_threads=1, ocr_scale=0.5, tmpdir=None, ocr_csv=None):
    res = {"decoded_sub": sub.name, "source": source.name, "frame_step": step, "width": W, "height": H, "eval_rows": R, "ref_frames": ref_frames, "schema": "qoe-quality-v3"}
    fs = W * H * 3 // 2
    if tmpdir: Path(tmpdir).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmpdir) as td:
        tmp = Path(td)
        rows, info = OCR.run(sub, W, H, R, ref_frames, jobs=ocr_jobs, scale=ocr_scale)
        res["ocr"] = {k: info[k] for k in ("decoded_frames", "ocr_in_range_fraction", "ocr_in_range_frames")}
        if ocr_csv:
            import csv
            with open(ocr_csv, "w", newline="", encoding="utf-8") as h:
                w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        offs, _ = OCR.frame_offsets(sub, fs); rp, dp = tmp / "ref.yuv", tmp / "dist.yuv"; used, seq, idx = 0, [], []
        src_size = source.stat().st_size
        with open(sub, "rb") as fd, open(source, "rb") as fsrc, open(rp, "wb") as fr, open(dp, "wb") as fdst:
            for i, r in enumerate(rows):
                lab = r["ocr_label"]
                if lab is None or lab < 1 or lab > ref_frames or lab * fs > src_size: continue
                fd.seek(offs[i]); d = fd.read(fs); fsrc.seek((lab - 1) * fs); s = fsrc.read(fs)
                if len(d) != fs or len(s) != fs: continue
                fr.write(roi_bytes(s, W, H, R)); fdst.write(roi_bytes(d, W, H, R)); used += 1; seq.append(lab); idx.append(i)
        res["paired_frames"] = used
        if used >= 30:
            res["ssim"], _ = metric(rp, dp, "ssim", tmp, W, R); res["psnr"], _ = metric(rp, dp, "psnr", tmp, W, R)
            v = vmaf(rp, dp, tmp, W, R, vmaf_threads); res["vmaf"], res["vmaf_frames"], pf = (v if v else (None, 0, []))
            res["per_frame"] = [[i, lab, round(x, 3)] for i, lab, x in zip(idx, seq, pf)] if len(pf) == len(idx) else None
            gaps = [b - a - step for a, b in zip(seq, seq[1:]) if b > a]
            res["skipped_source_frames_per_100"] = 100.0 * sum(g for g in gaps if g > 0) / max(len(gaps), 1) / step
            res["skip_events_gt2"] = sum(1 for g in gaps if g >= 2 * step); res["n_wraps"] = sum(1 for a, b in zip(seq, seq[1:]) if b < a)
            res["rendered_fps"] = round(info["decoded_frames"] * step / duration_s, 2) if duration_s else None
            res["duration_s"] = duration_s; res["label_span"] = [min(seq), max(seq)]
        else: res["error"] = "Fewer than 30 pairable frames"
    return res


def selftest():
    W, H, R, N = 640, 360, 288, 160; step = 4
    with tempfile.TemporaryDirectory(dir="/path/to/storage") as td:
        d = Path(td); src = d / "src.yuv"
        vf = (f"drawbox=x=0:y={R}:w=iw:h=ih-{R}:color=black@1:t=fill,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf:"
              f"text='%{{eif\\:n+1\\:d\\:6}}':fontcolor=white:fontsize=56:x=(w-text_w)/2:y={R}+(72-th)/2")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={W}x{H}:rate=30", "-frames:v", str(N), "-vf", vf, "-pix_fmt", "yuv420p", "-f", "rawvideo", str(src)], check=True)
        sub = d / "sub.y4m"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}", "-r", "30", "-i", str(src), "-c:v", "libvpx", "-b:v", "2M", "-f", "webm", str(d / "x.webm")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(d / "x.webm"), "-vf", f"select=not(mod(n\\,{step}))", "-fps_mode", "passthrough", "-pix_fmt", "yuv420p", str(sub)], check=True)
        good = score(sub, src, W, H, R, N, step, duration_s=N / 30.0, ocr_jobs=4, vmaf_threads=2, ocr_scale=1.0, tmpdir=str(d))
        assert good["ocr"]["ocr_in_range_fraction"] >= 0.9 and good["paired_frames"] == N // step and good["vmaf"] and good["vmaf"] > 60 and good["psnr"] > 30, good
        assert good["skipped_source_frames_per_100"] == 0.0 and good["rendered_fps"] == 30.0, good
        assert len(good["per_frame"]) == good["paired_frames"] and good["per_frame"][1][:2] == [1, 1 + step], good["per_frame"][:3]
        bad = score(sub, src, W, H, H - 16, N, step, ocr_jobs=4, ocr_scale=1.0, tmpdir=str(d))
        assert bad["ocr"]["ocr_in_range_fraction"] < 0.5 and "error" in bad, bad
        shuf = d / "shuf.y4m"
        fs = W * H * 3 // 2; raw = src.read_bytes(); cw = W // 2
        with open(shuf, "wb") as h:
            h.write(f"YUV4MPEG2 W{W} H{H} F30:1 Ip A1:1 C420jpeg\n".encode())
            for k in range(0, N, step):
                a, b = raw[k * fs:(k + 1) * fs], raw[((k + 60) % N) * fs:((k + 60) % N + 1) * fs]
                y = b[:W * R] + a[W * R:W * H]; u0 = W * H; v0 = u0 + cw * (H // 2); ch = R // 2
                u = b[u0:u0 + cw * ch] + a[u0 + cw * ch:v0]; v = b[v0:v0 + cw * ch] + a[v0 + cw * ch:fs]
                h.write(b"FRAME\n" + y + u + v)
        sh = score(shuf, src, W, H, R, N, step, ocr_jobs=4, vmaf_threads=2, ocr_scale=1.0, tmpdir=str(d))
        assert sh["psnr"] < good["psnr"] - 5, (sh["psnr"], good["psnr"])
    print(f"Quality v3 self-test passed: VMAF {good['vmaf']:.1f}, PSNR {good['psnr']:.1f}, {good['paired_frames']} paired frames; wrong label band rejected (hit rate {bad['ocr']['ocr_in_range_fraction']:.2f}), shifted frames rejected (PSNR {sh['psnr']:.1f})")


def main():
    if "--selftest" in sys.argv: selftest(); return
    ap = argparse.ArgumentParser()
    ap.add_argument("sub", type=Path); ap.add_argument("source", type=Path); ap.add_argument("out", type=Path)
    ap.add_argument("--width", type=int, required=True); ap.add_argument("--height", type=int, required=True); ap.add_argument("--label-y", type=int, required=True)
    ap.add_argument("--ref-frames", type=int, required=True); ap.add_argument("--step", type=int, required=True); ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--ocr-jobs", type=int, default=1); ap.add_argument("--vmaf-threads", type=int, default=1); ap.add_argument("--ocr-scale", type=float, default=0.5)
    ap.add_argument("--tmpdir", default=None); ap.add_argument("--keep", action="store_true"); ap.add_argument("--ocr-csv", default=None)
    a = ap.parse_args()
    try: res = score(a.sub, a.source, a.width, a.height, a.label_y, a.ref_frames, a.step, a.duration_s, a.ocr_jobs, a.vmaf_threads, a.ocr_scale, a.tmpdir, a.ocr_csv)
    except Exception as e: res = {"decoded_sub": a.sub.name, "error": f"{type(e).__name__}: {e}"}
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if not a.keep and a.sub.is_file() and "error" not in res: a.sub.unlink()
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
