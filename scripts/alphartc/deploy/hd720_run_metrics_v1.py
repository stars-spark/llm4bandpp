#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-run readings shared by the 720p and competition judges; reads run directories only.
Validity: run-script check passed, OCR frame-number hit rate at least 0.9, decoded frame rate at least 25 for non-LLM arms at hd_c8, LLM-arm decision interval p95 at most 200 ms, package temperature below 95 °C.
Utility is 100 x (0.4R + 0.4D + 0.2(1 - L)) after the first 6 s; freezes are counted three ways (decoded-file W3C rule, WebRTC receiver stats, frame-gap proxy).
"""
import csv, gzip, json, math, re, statistics as st, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); sys.path.insert(0, str(ROOT / "scripts/alphartc")); sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy"))
import eval_staleness_run as E  # noqa: E402
import frame_gap_proxy_v1 as FG  # noqa: E402
LLM_ARMS = ("arm_llm4bandpp_x", "arm_llm4band_conf_x")
WEBRTC_KEYS = ("NumberFreezesPerMinute", "MeanFreezeDurationMs", "HarmonicFrameRate", "TimeInHdPercentage", "ReceivedWidthInPixels", "ReceivedHeightInPixels", "MeanTimeBetweenFreezesMs")


def first(d, pat):
    fs = sorted(Path(d).glob(pat)); return fs[0] if fs else None


def opn(p): return gzip.open(p, "rt", errors="replace") if str(p).endswith(".gz") else open(p, errors="replace")


def jl(p):
    if p is None: return []
    out = []
    with opn(p) as f:
        for l in f:
            l = l.strip()
            if l.startswith("{"):
                try: out.append(json.loads(l))
                except ValueError: pass
    return out


def pct(xs, q):
    return E.percentile(list(xs), q) if xs else None


def webrtc_stats(netlog):
    out = {}
    if netlog is None: return out
    pat = re.compile(r"WebRTC\.Video\.(" + "|".join(WEBRTC_KEYS) + r") (-?\d+)\s*$")
    with opn(netlog) as f:
        for l in f:
            m = pat.search(l.rstrip("\n"))
            if m and m.group(1) not in out: out[m.group(1)] = int(m.group(2))
    return out


def per_second_video(netlog, t0_ms, ssrc_set=None):
    pk = E.load_packets(str(netlog)); fid = E.load_fid_groups(str(netlog)); prim = {p for p, _ in fid}
    vp = [p for p in pk if (p["ssrc"] in prim if prim else True) and p["arrival_ms"] >= t0_ms]; per = {}
    for p in vp:
        k = int((p["arrival_ms"] - t0_ms) // 1000); per[k] = per.get(k, 0) + p["payload_bytes"]
    if not per: return []
    return [per.get(s, 0) * 8 / 1000.0 for s in range(0, max(per) + 1)]


def capacity_series(control_log, t0_ms, n):
    ctl = sorted(jl(control_log), key=lambda r: float(r.get("wall_time_ms", 0))); ctl = [c for c in ctl if c.get("event") == "apply"]
    return [E.target_at(ctl, t0_ms + 1000.0 * s + 500.0) for s in range(n)]


def time_to_ceiling(rate, cap, ceiling, frac=0.9, win=5):
    for s in range(win - 1, len(rate)):
        c = cap[s] if s < len(cap) else None
        if not c: continue
        if st.mean(rate[s - win + 1:s + 1]) >= frac * min(c, ceiling): return s + 1
    return None


def decoded_file_freezes(csv_path, t_start_ms, hist=30, mult=3.0, margin=150.0):
    """W3C-style freeze count on the times frames became complete in the decoded file (polled every 5 ms), after t_start_ms only."""
    if csv_path is None: return {}
    times = []; prev = 0
    with opn(csv_path) as f:
        for r in csv.DictReader(f):
            c = int(r["complete_frames"]); t = int(r["wall_time_ns"]) / 1e6
            if c > prev: times += [t] * (c - prev); prev = c
    times = [t for t in times if t >= t_start_ms]
    if len(times) < hist + 10: return {"decoded_frames_window": len(times)}
    gaps = [b - a for a, b in zip(times, times[1:])]; fz, fz_ms = 0, 0.0
    for i in range(hist, len(gaps)):
        m = sum(gaps[i - hist:i]) / hist
        if gaps[i] >= max(mult * m, m + margin): fz += 1; fz_ms += gaps[i]
    dur = (times[-1] - times[0]) / 1000.0
    return {"decoded_frames_window": len(times), "decoded_fps": (len(times) - 1) / dur if dur > 0 else None, "file_freeze_count": fz, "file_freeze_per_min": fz / dur * 60 if dur > 0 else None,
            "file_freeze_time_share": fz_ms / 1000.0 / dur if dur > 0 else None, "file_gap_p95_ms": pct(gaps, 95), "file_gap_max_ms": max(gaps)}


def envelope_stats(obs_path):
    O = [o for o in jl(obs_path) if "est_bps" in o]
    if not O: return {}
    states = {}
    for o in O: s = (o.get("envelope") or {}).get("state", "none"); states[s] = states.get(s, 0) + 1
    return {"obs_steps": len(O), "envelope_rewrite_frac": sum(1 for o in O if abs(float(o["est_bps"]) - float(o.get("model_bps", o["est_bps"]))) > 1.0) / len(O),
            "envelope_state_share": {k: v / len(O) for k, v in sorted(states.items())}, "obs_compute_p50_ms": pct([o.get("compute_ms", 0) for o in O], 50), "obs_compute_p95_ms": pct([o.get("compute_ms", 0) for o in O], 95)}


def cpu_stats(cpu_path):
    C = [c for c in jl(cpu_path) if c.get("roles")]
    if not C: return {}
    roles = sorted({k for c in C for k in c["roles"]})
    return {"host_busy_pct_median": st.median(c["host_busy_pct"] for c in C), "mem_avail_mb_min": min(c.get("mem_avail_mb", 0) for c in C),
            "cpu_pct_median": {r: st.median(c["roles"][r]["cpu_pct"] for c in C if r in c["roles"]) for r in roles},
            "cpu_pct_p95": {r: pct([c["roles"][r]["cpu_pct"] for c in C if r in c["roles"]], 95) for r in roles},
            "rss_mb_max": {r: max(c["roles"][r]["rss_mb"] for c in C if r in c["roles"]) for r in roles}}


def sender_resolution(sl):
    if sl is None: return {}
    up = down = 0
    with opn(sl) as f:
        for l in f:
            if "Scaling down resolution" in l: down += 1
            elif "Scaling up resolution" in l: up += 1
    return {"sender_scale_down_events": down, "sender_scale_up_events": up}


def run_metrics(d, tag, arm, cond, ceiling_kbps, light_fps_gate=False):
    """Return all readings and validity for one run directory; ceiling_kbps is the sequence's measured rate ceiling and light_fps_gate enables the hd_c8 frame-rate gate for non-LLM arms."""
    d = Path(d); r = {"tag": tag, "arm": arm, "cond": cond, "invalid_reasons": []}
    meta = json.load(open(d / "run_meta.json")) if (d / "run_meta.json").is_file() else {}
    r.update({"pair": meta.get("pair"), "rc": meta.get("rc"), "rep": meta.get("rep"), "video_id": meta.get("video_id"), "platform_profile": meta.get("platform_profile"),
              "cpu_temp_start": meta.get("cpu_temp_start"), "cpu_temp_end": meta.get("cpu_temp_end"), "start": meta.get("start"), "end": meta.get("end"), "decoded_duration_s": meta.get("decoded_duration_s")})
    summ = d / f"{tag}.json"
    if not meta: r["invalid_reasons"].append("missing run_meta")
    if not summ.is_file() or list(d.glob("invalid_*")): r["invalid_reasons"].append("run script validity check did not pass or has no result")
    s = json.load(open(summ)) if summ.is_file() else None
    if s:
        r.update({"decision_gap_p50_ms": s["decisions"]["decision_gap_p50_ms"], "decision_gap_p95_ms": s["decisions"]["decision_gap_p95_ms"], "compute_p50_ms": s["decisions"]["compute_p50_ms"],
                  "compute_p95_ms": s["decisions"]["compute_p95_ms"], "measure_duration_s": s["measurement"]["duration_s"], "n_applies": s["controls"]["n_applies"]})
        if arm in LLM_ARMS and (s["decisions"]["decision_gap_p95_ms"] or 0) > 200: r["invalid_reasons"].append("LLM arm decision interval 95th percentile exceeds 200 milliseconds")
    q = d / f"quality_{tag}.json"; Q = json.load(open(q)) if q.is_file() else {}
    r.update({"vmaf": Q.get("vmaf"), "ssim": Q.get("ssim"), "psnr": Q.get("psnr"), "ocr_in_range_fraction": (Q.get("ocr") or {}).get("ocr_in_range_fraction"), "paired_frames": Q.get("paired_frames"),
              "rendered_fps": Q.get("rendered_fps"), "skipped_source_frames_per_100": Q.get("skipped_source_frames_per_100"), "quality_error": Q.get("error")})
    if s is not None:
        if not Q: r["invalid_reasons"].append("Missing quality score")
        elif (r["ocr_in_range_fraction"] or 0) < 0.9: r["invalid_reasons"].append("OCR in-range fraction below 0.9")
        elif r["vmaf"] is None: r["invalid_reasons"].append("VMAF not computed")
    temps = [x for x in (meta.get("cpu_temp_start"), meta.get("cpu_temp_end")) if x is not None]
    if temps and max(temps) >= 95: r["invalid_reasons"].append("package temperature reached 95 °C")
    net = first(d, f"network_{tag}.log*"); ctl = first(d, f"control_{tag}.log"); dec = first(d, f"decision_{tag}.jsonl*")
    if net is not None and ctl is not None:
        try:
            a = E.analyze(str(net), str(dec) if dec else None, str(ctl), warmup_s=6.0, max_queue_ms=500.0, source_ceiling_kbps=ceiling_kbps)
            r.update({"utility": a["network"]["utility"], "rate_score": a["network"]["rate_score_1s"], "delay_score": a["network"]["delay_score"], "video_kbps": a["network"]["primary_video_payload_rate_kbps"],
                      "loss_rate": a["network"]["loss"]["loss_rate"], "queue_delay_mean_ms": a["network"]["queue_delay_mean_ms"], "queue_delay_p95_ms": a["network"]["queue_delay_p95_ms"]})
            t0 = float(sorted(jl(ctl), key=lambda x: float(x.get("wall_time_ms", 0)))[0]["wall_time_ms"]); r["shape_t0_ms"] = t0
            rate = per_second_video(net, t0); cap = capacity_series(ctl, t0, len(rate)); r["video_kbps_per_s"] = [round(x, 1) for x in rate]
            r["time_to_ceiling_s"] = time_to_ceiling(rate, cap, ceiling_kbps)
            r["video_kbps_after6s_median"] = st.median(rate[6:]) if len(rate) > 7 else None
        except Exception as e: r["analyze_error"] = repr(e)[:200]
        r.update({f"webrtc_{k}": v for k, v in webrtc_stats(net).items()})
        try:
            fg = FG.analyse(str(net), 30.0); r.update({"proxy_" + k: fg.get(k) for k in ("freeze_per_min", "frozen_time_share", "arrival_fps", "gap_p95_ms", "gap_max_ms")})
        except Exception as e: r["proxy_error"] = repr(e)[:120]
    dts = first(d, f"decoded_timestamps_{tag}.csv*")
    if dts is not None and r.get("shape_t0_ms"): r.update(decoded_file_freezes(dts, r["shape_t0_ms"] + 6000.0))
    if light_fps_gate and arm not in LLM_ARMS and s is not None and (r.get("decoded_fps") is None or r["decoded_fps"] < 25): r["invalid_reasons"].append("decoded frame rate below 25 (light arm at C8)")
    r.update(envelope_stats(first(d, f"obs_{tag}.jsonl*"))); r.update(cpu_stats(first(d, f"cpu_{tag}.jsonl")))
    r.update(sender_resolution(first(d, f"senderwebrtc_{tag}.log*")))
    cf = first(d, f"code_{tag}.sha256")
    if cf is not None:
        m = {}
        for l in cf.read_text().splitlines():
            if not l.strip(): continue
            h, p = l.split(None, 1); p = re.sub(r"^/path/to/testbed/p\d+", "APP", p.strip()); m[p] = h
        r["code_hash"] = {k: v for k, v in m.items() if "staleness_profiles" not in k and "testmedia" not in k}
    r["valid"] = not r["invalid_reasons"]
    return r


def code_audit(runs):
    """Take each arm's majority code hash in the batch as reference and return the tags of runs that differ."""
    by = {}
    for r in runs:
        if r.get("code_hash"): by.setdefault(r["arm"], []).append(r)
    bad = []
    for arm, rs in by.items():
        keys = [json.dumps(r["code_hash"], sort_keys=True) for r in rs]; ref = max(set(keys), key=keys.count)
        for r, k in zip(rs, keys):
            if k != ref: r["invalid_reasons"].append("Code hash inconsistent with other runs of the same arm in this batch"); r["valid"] = False; bad.append(r["tag"])
    return bad
