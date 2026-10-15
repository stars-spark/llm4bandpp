#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Network-side freeze proxy from frame arrival gaps, computed from archived network logs only.
Main-video packets are grouped into frames by abs-send-time (24-bit, unwrapped); a frame arrives with its last packet and incomplete frames are dropped; a freeze is a gap above max(3 x mean of the last 30 gaps, mean + 150 ms), the W3C freezeCount rule on arrival gaps, not a decoder or renderer count.
Usage: frame_gap_proxy_v1.py NETWORK_LOG[.gz] [SOURCE_FPS] | --selftest
"""
import gzip, json, sys, statistics as st
GAP_MS, HIST, ABS_MARGIN, MULT, WARMUP_S = 20.0, 30, 150.0, 3.0, 6.0


def packets(path):
    op = gzip.open if str(path).endswith(".gz") else open; out = []
    with op(path, "rt", errors="replace") as f:
        for l in f:
            if "remote_estimator_proxy.cc" not in l or '"packetInfo"' not in l: continue
            try: p = json.loads(l[l.index("{"):])["packetInfo"]
            except Exception: continue
            h = p["header"]; out.append((h["ssrc"], h["sequenceNumber"], h["sendTimestamp"], p["arrivalTimeMs"], p["payloadSize"], h["payloadType"]))
    return out


def frames_from(pk):
    by = {}
    for s in pk: by.setdefault(s[0], []).append(s)
    main = max(by.values(), key=lambda v: sum(x[4] for x in v))
    main.sort(key=lambda x: x[3]); fr, cur, last_send, off, prev_raw = [], [], None, 0.0, None
    for ssrc, seq, send, arr, size, pt in main:
        if prev_raw is not None and send < prev_raw - 30000: off += 64000.0
        prev_raw = send; t = send + off
        if last_send is not None and t - last_send > GAP_MS: fr.append(cur); cur = []
        cur.append((seq, arr)); last_send = t
    if cur: fr.append(cur)
    return fr


def analyse(path, fps=15.0):
    fr = frames_from(packets(path)); arrivals, prev_last = [], None; n_incomplete = 0
    for f in fr:
        seqs = sorted(s for s, _ in f); ok = all((b - a) % 65536 == 1 for a, b in zip(seqs, seqs[1:])) and (prev_last is None or (seqs[0] - prev_last) % 65536 == 1)
        prev_last = seqs[-1]
        if ok: arrivals.append(max(a for _, a in f))
        else: n_incomplete += 1
    if len(arrivals) < 40: return {"valid": False, "reason": "too few complete frames", "frames": len(arrivals)}
    t0 = arrivals[0]; arrivals = [a for a in arrivals if a - t0 >= WARMUP_S * 1000]; gaps = [b - a for a, b in zip(arrivals, arrivals[1:])]; dur = (arrivals[-1] - arrivals[0]) / 1000.0
    freezes, frozen_ms = 0, 0.0
    for i, g in enumerate(gaps):
        h = gaps[max(0, i - HIST):i]
        if len(h) >= 5:
            avg = sum(h) / len(h)
            if g > max(MULT * avg, avg + ABS_MARGIN): freezes += 1; frozen_ms += g
    gs = sorted(gaps)
    return {"valid": True, "frames_complete": len(arrivals), "frames_incomplete": n_incomplete, "duration_s": dur, "arrival_fps": len(gaps) / dur if dur > 0 else None, "fps_ratio": (len(gaps) / dur / fps) if dur > 0 else None,
            "freeze_events": freezes, "freeze_per_min": freezes / dur * 60 if dur > 0 else None, "frozen_time_share": frozen_ms / 1000.0 / dur if dur > 0 else None, "gap_p50_ms": st.median(gaps), "gap_p95_ms": gs[int(0.95 * len(gs))], "gap_p99_ms": gs[int(0.99 * len(gs))], "gap_max_ms": gs[-1]}


def selftest():
    import tempfile, os
    def mk(gaps_at):
        lines, t, seq = [], 1_000_000.0, 100
        for i in range(600):
            t += 66.7 + (1000.0 if i in gaps_at else 0.0)
            for k in range(2):
                lines.append('(remote_estimator_proxy.cc:151): ' + json.dumps({"packetInfo": {"arrivalTimeMs": int(t + 3 * k), "header": {"headerLength": 28, "paddingLength": 0, "payloadType": 125, "sendTimestamp": int((t - 50) % 64000), "sequenceNumber": seq % 65536, "ssrc": 7}, "lossRates": 0.0, "payloadSize": 900}})); seq += 1
        p = os.path.join(tempfile.mkdtemp(), "n.log"); open(p, "w").write("\n".join(lines)); return p
    a = analyse(mk(set())); assert a["valid"] and a["freeze_events"] == 0 and abs(a["fps_ratio"] - 1) < 0.05, a
    b = analyse(mk({200, 400})); assert b["freeze_events"] == 2 and b["frozen_time_share"] > 0.04, b
    assert not (analyse(mk({200, 400}))["freeze_events"] == 0), "should not pass: there were two 1-second pauses but they were not detected"
    print("Self-test passed: 0 freezes without pauses, 2 for two 1 s pauses, none at the 64 s wrap")


if __name__ == "__main__":
    if sys.argv[1] == "--selftest": selftest()
    else: print(json.dumps(analyse(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 15.0), ensure_ascii=False))
