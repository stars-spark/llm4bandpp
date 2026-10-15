#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end check of the designer's adapters on real software telemetry (registered experiment realtel-e2e-v1).
Reads captures and telemetry under experiments/results/realtel_e2e_v1/runs/<source>_L<loss>_r<rep>/, computes ground truth from the capture,
applies each method's adapter to the real telemetry and scores every (run, feature) cell.
Sources: W3C getStats in Chrome, iperf3 UDP JSON, Linux tcp_info, and RTCP reports of a GStreamer RTP session scored against RFC 3550/3611.
Usage: realtel_e2e_v1.py judge [--selftest] [--runs DIR] | check DIR; check prints each source's error under the ground-truth adapter, as a tool check without a verdict.
"""
import json, math, random, statistics, struct, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
OUT = ROOT / "experiments/results/realtel_e2e_v1"; ID = "realtel-e2e-v1"; DELTA = 0.15; SEED = 20261005
SRC = {"w3c": "w3c_webrtc_stats", "iperf3": "iperf3_udp_json", "tcpinfo": "linux_tcp_info", "gst": "rfc3550_rfc3611"}
FEATS = {"w3c": [1, 2], "iperf3": [0, 2, 10], "tcpinfo": [1, 2], "gst": [10]}
REL_TOL, LOSS_TOL, GROSS_REL, GROSS_LOSS, SRTP_TAG = 0.05, 0.01, 0.5, 0.1, 10


def pcap(path):
    """Yield (time, protocol, src port, dst port, transport payload, extra) per IPv4 packet; extra is (seq, flags, payload length) for TCP and the payload length for UDP."""
    b = Path(path).read_bytes(); off = 24
    while off + 16 <= len(b):
        ts, us, cl, ol = struct.unpack("<IIII", b[off:off + 16]); p = b[off + 16:off + 16 + cl]; off += 16 + cl
        if len(p) < 34 or p[12:14] != b"\x08\x00": continue
        ip = p[14:]; ihl = (ip[0] & 15) * 4; tot = struct.unpack(">H", ip[2:4])[0]; proto = ip[9]; t = ts + us / 1e6
        if proto == 17:
            sp, dp, ul = struct.unpack(">HHH", ip[ihl:ihl + 6]); yield t, "udp", sp, dp, ip[ihl + 8:], ul - 8
        elif proto == 6:
            sp, dp, seq = struct.unpack(">HHI", ip[ihl:ihl + 8]); doff = (ip[ihl + 12] >> 4) * 4; fl = ip[ihl + 13]
            yield t, "tcp", sp, dp, ip[ihl + doff:], (seq, fl, tot - ihl - doff)


def rtp_info(u, ulen):
    """Return (ssrc, seq, payload bytes, padding bit) for an RTP packet, or None for RTCP and non-RTP; callers subtract the SRTP tag."""
    if len(u) < 12 or (u[0] >> 6) != 2 or 192 <= u[1] <= 223: return None
    cc = u[0] & 15; hl = 12 + 4 * cc
    if u[0] & 0x10 and len(u) >= hl + 4: hl += 4 + 4 * struct.unpack(">H", u[hl + 2:hl + 4])[0]
    return struct.unpack(">I", u[8:12])[0], struct.unpack(">H", u[2:4])[0], ulen - hl, bool(u[0] & 0x20)


def pairs(times, step=10):
    return [(i, i + step) for i in range(0, len(times) - step, step)]


def load_w3c(d):
    snaps = []
    for l in open(d / "stats.jsonl"):
        j = json.loads(l)
        if "rows" not in j: continue
        r = next((x for x in j["rows"] if x["side"] == "recv" and x["type"] == "inbound-rtp"), None)
        if not r or not r.get("packetsReceived"): continue
        ri = next((x for x in j["rows"] if x["side"] == "send" and x["type"] == "remote-inbound-rtp"), {})
        snaps.append({"t": r["timestamp"] / 1000, "ssrc": r["ssrc"], "rtx": r.get("rtxSsrc"), "f": {
            "packetsReceived": r.get("packetsReceived"), "bytesReceived": r.get("bytesReceived"), "jitterBufferDelay": r.get("jitterBufferDelay"),
            "roundTripTime": ri.get("roundTripTime"), "totalInterFrameDelay": r.get("totalInterFrameDelay"), "jitter": r.get("jitter"),
            "fractionLost": ri.get("fractionLost"), "kind": r.get("kind")}})
    ss = {snaps[-1]["ssrc"]}; rtx = {s["rtx"] for s in snaps if s.get("rtx")}; pk = []
    for t, pr, sp, dp, u, ul in pcap(d / "cap.pcap"):
        if pr != "udp": continue
        x = rtp_info(u, ul)
        if x and (x[0] in ss or x[0] in rtx): pk.append((t, x[2] - SRTP_TAG, x[0] in ss, x[3]))
    W = []
    for i, j in pairs([s["t"] for s in snaps]):
        a, b = snaps[i]["t"], snaps[j]["t"]; sel = [p for p in pk if a < p[0] <= b]
        W.append({"r0": snaps[i]["f"], "r1": snaps[j]["f"], "dt": b - a, "truth": {1: len(sel), 2: sum(p[1] for p in sel)},
                  "alt": {"media SSRC packet count": sum(1 for p in sel if p[2]), "16-byte checksum byte count": sum(p[1] - 6 for p in sel)}})
    return W


def load_iperf3(d):
    S = json.load(open(d / "server.json")); iv = S["intervals"]; pk = []
    for t, pr, sp, dp, u, ul in pcap(d / "cap.pcap"):
        if pr == "udp" and dp == 5201 and len(u) >= 12: pk.append((t, ul, struct.unpack(">I", u[8:12])[0]))
    t0 = pk[0][0]; W = []; prev_max = 0
    for x in iv:
        s = x["streams"][0]; a, b = t0 + s["start"], t0 + s["end"]; sel = [p for p in pk if a <= p[0] < b]
        if not sel or s["end"] - s["start"] < 0.5: continue
        mx = max(p[2] for p in sel); exp = mx - prev_max; rec = len(sel); prev_max = max(prev_max, mx); by = sum(p[1] for p in sel)
        f = {k: s.get(k) for k in ("bits_per_second", "packets", "bytes", "jitter_ms", "lost_percent")}
        W.append({"r0": None, "r1": f, "dt": s["end"] - s["start"], "truth": {0: by * 8 / (s["end"] - s["start"]), 2: by, 10: max(0.0, (exp - rec) / exp) if exp > 0 else None}})
    return W


def load_tcpinfo(d):
    R = [json.loads(l) for l in open(d / "tcpinfo.jsonl")]; seg = []; isn = None
    for t, pr, sp, dp, u, ex in pcap(d / "cap.pcap"):
        if pr != "tcp" or dp != 6000: continue
        seq, fl, plen = ex
        if fl & 0x02: isn = seq; continue
        if plen > 0: seg.append((t, seq, plen))
    M32 = 0xFFFFFFFF; le = lambda x, y: ((y - x) & M32) < 2 ** 31
    nxt = (isn + 1) & M32; pend = {}; adv = []
    # Advance rcv_nxt over in-order bytes (32-bit wraparound) and record (time, bytes advanced) at each advance.
    for t, seq, plen in seg:
        pend[seq] = max(pend.get(seq, 0), plen); moved = 0
        while True:
            prog = False
            for s, l in list(pend.items()):
                e = (s + l) & M32
                if le(s, nxt) and not le(e, nxt): moved += (e - nxt) & M32; nxt = e; prog = True
                if le(e, nxt): pend.pop(s, None)
            if not prog: break
        if moved: adv.append((t, moved))
    W = []
    for i, j in pairs([r["t"] for r in R]):
        a, b = R[i]["t"], R[j]["t"]
        W.append({"r0": R[i], "r1": R[j], "dt": b - a, "truth": {1: sum(1 for s in seg if a < s[0] <= b), 2: sum(m for t, m in adv if a < t <= b)}})
    return W


def load_gst(d):
    rtp, rr, sr = [], [], []
    for t, pr, sp, dp, u, ul in pcap(d / "cap.pcap"):
        if pr != "udp": continue
        if dp == 5000:
            x = rtp_info(u, ul + SRTP_TAG)
            if x: rtp.append((t, x[1]))
        elif dp == 5005 and len(u) >= 20 and u[1] == 201 and (u[0] & 31) >= 1: rr.append((t, u[12], struct.unpack(">I", u[16:20])[0]))
        elif dp == 5001 and len(u) >= 28 and u[1] == 200: sr.append((t, struct.unpack(">I", u[24:28])[0]))
    ext, cyc, last = [], 0, None
    for t, s in rtp:
        if last is not None and s < last and last - s > 30000: cyc += 65536
        last = s; ext.append((t, cyc + s))
    # A gap above 1.5x the median means netem dropped a receiver report in between; such pairs are skipped.
    gaps = [rr[i][0] - rr[i - 1][0] for i in range(1, len(rr))]; med = statistics.median(gaps) if gaps else 0; W = []
    for i in range(1, len(rr)):
        if rr[i][0] - rr[i - 1][0] > 1.5 * med: continue
        lo, hi = rr[i - 1][2], rr[i][2]; exp = hi - lo
        if exp <= 0: continue
        rec = sum(1 for t, e in ext if lo < e <= hi); oc = [v for t, v in sr if t <= rr[i][0]]; oc0 = [v for t, v in sr if t <= rr[i - 1][0]]
        f = lambda r, o: {"fraction lost": r[1], "sender's octet count": o[-1] if o else None, "payload type": 96}
        W.append({"r0": f(rr[i - 1], oc0), "r1": f(rr[i], oc), "dt": rr[i][0] - rr[i - 1][0], "truth": {10: max(0.0, (exp - rec) / exp)}})
    return W


LOAD = {"w3c": load_w3c, "iperf3": load_iperf3, "tcpinfo": load_tcpinfo, "gst": load_gst}


def adapters():
    """Return {method: {e2e source: {feature: (field, diff, scale) or None}}} for the designer, the open models and the seven baselines."""
    import realtel_baselines_v2 as V
    out = {}
    def from_map(mp, src):
        f = M.TEST[src]["fields"]; return {k: (None if (mp is None or mp[k] is None) else (f[mp[k]["source"]][0], bool(mp[k]["diff"]), float(mp[k]["scale"]))) for k in range(15)}
    L = {(j["source"], j["pres"]): j["mapping"] for j in map(json.loads, open(M.OUT / "llm_test_deepseek.jsonl")) if j.get("ok")}
    out["DEEPSEEK"] = {e: from_map(L.get((s, 0)), s) for e, s in SRC.items()}
    for tag in ("r1_32b", "r1_14b"):
        p = M.OUT / f"out_open_{tag}.jsonl"
        if not p.exists(): continue
        O = {}
        for j in map(json.loads, open(p)):
            _, n, k = j["id"].split("|")
            if k == "0":
                try: O[n] = M.parse(j["text"], len(M.TEST[n]["fields"]))
                except Exception: O[n] = None
        out["OPEN_" + tag] = {e: from_map(O.get(s), s) for e, s in SRC.items()}
    S = V.classic_scores(); S.update(json.load(open(V.OUT / "scores_valentine.json"))); S.update(json.load(open(V.OUT / "scores_embed.json")))
    taus = json.load(open(V.OUT / "judge.json"))["baselines"]
    for b, sc in S.items():
        out[b] = {}
        for e, s in SRC.items():
            fl = M.TEST[s]["fields"]; dec = V.decide(sc["test"][s], taus[b]["tau"])
            out[b][e] = {k: (None if dec[k] is None else (fl[dec[k]][0], M.is_cum(fl[dec[k]][2]), M.unit_scale(k, fl[dec[k]][0], fl[dec[k]][2]))) for k in range(15)}
    return out


def apply(w, a):
    """Return an adapter's value on one window, or None when the field is missing or not numeric."""
    if a is None: return None
    name, diff, sc = a; v1 = (w["r1"] or {}).get(name)
    if not isinstance(v1, (int, float)) or isinstance(v1, bool): return None
    if diff:
        v0 = (w["r0"] or {}).get(name) if w["r0"] is not None else None
        if not isinstance(v0, (int, float)) or isinstance(v0, bool): return None
        return (v1 - v0) * sc
    return v1 * sc


def unit_err(W, k, a):
    """Return (median error, correct) for one cell: absolute error for loss ratio, relative error otherwise; a missing value or no usable window counts as wrong."""
    errs = []
    for w in W:
        t = w["truth"].get(k); v = apply(w, a)
        if t is None: continue
        if v is None: return (float("inf"), False)
        if k == 10: errs.append(abs(v - t))
        elif t > 0: errs.append(abs(v - t) / t)
    if not errs: return (float("inf"), False)
    m = statistics.median(errs); return (m, m <= (LOSS_TOL if k == 10 else REL_TOL))


def judge(R, seed=SEED, B=5000):
    """Apply the registered criterion to delta = designer correct share - best baseline share (run bootstrap); any gross designer error makes it not hold."""
    base = {m: r for m, r in R.items() if m not in ("DEEPSEEK",) and not m.startswith("OPEN_")}
    rate = lambda rows: sum(x["ok"] for x in rows) / len(rows)
    best = max(base, key=lambda m: rate(base[m])); runs = sorted({x["run"] for x in R["DEEPSEEK"]})
    def d(sel):
        a = [x for r in sel for x in R["DEEPSEEK"] if x["run"] == r]; b = [x for r in sel for x in base[best] if x["run"] == r]; return rate(a) - rate(b)
    D = d(runs); rng = random.Random(seed); boots = sorted(d([rng.choice(runs) for _ in runs]) for _ in range(B)); lo, hi = boots[int(0.05 * B)], boots[int(0.95 * B) - 1]
    gross = [x for x in R["DEEPSEEK"] if x["err"] > (GROSS_LOSS if x["k"] == 10 else GROSS_REL)]
    v = "does not hold" if (not D > 0 or gross) else ("holds" if lo > 0 and D >= DELTA else "direction only")
    return v, {"delta": D, "ci90": [lo, hi], "best_base": best, "rate": {m: rate(r) for m, r in R.items()}, "gross_llm": len(gross)}


def selftest():
    W = [{"r0": {"x": 100}, "r1": {"x": 200}, "dt": 1, "truth": {1: 100, 10: 0.02}}, {"r0": {"x": 200}, "r1": {"x": 310}, "dt": 1, "truth": {1: 110, 10: 0.03}}]
    assert unit_err(W, 1, ("x", True, 1.0))[1] and not unit_err(W, 1, ("x", False, 1.0))[1] and not unit_err(W, 1, None)[1]
    W2 = [{"r0": None, "r1": {"lp": 2.0}, "dt": 1, "truth": {10: 0.02}}]
    assert unit_err(W2, 10, ("lp", False, 0.01))[1] and not unit_err(W2, 10, ("lp", False, 1.0))[1]
    mk = lambda p, n=48: [{"run": f"r{i % 24}", "ok": int(random.Random(i * 7 + int(p * 100)).random() < p), "err": 0.01, "k": 1} for i in range(n)]
    assert judge({"DEEPSEEK": mk(1.0), "A": mk(0.5)})[0] == "holds"
    assert judge({"DEEPSEEK": mk(0.5), "A": mk(0.9)})[0] == "does not hold"
    G = mk(1.0); G[0]["err"] = 0.9
    assert judge({"DEEPSEEK": G, "A": mk(0.3)})[0] == "does not hold"
    print("Self-test passed (difference, coefficients, missing, packet loss, holds, does not hold, safety line)")


def collect(runs_dir):
    A = adapters(); R = {m: [] for m in A}; detail = {}
    for d in sorted(Path(runs_dir).iterdir()):
        if not d.is_dir() or not (d / "OK").exists(): continue
        src = d.name.split("_")[0]; W = LOAD[src](d); detail[d.name] = {"windows": len(W)}
        for k in FEATS[src]:
            for m in A:
                e, ok = unit_err(W, k, A[m][src].get(k)); R[m].append({"run": d.name, "k": k, "src": src, "ok": int(ok), "err": e})
                detail[d.name].setdefault(m, {})[k] = None if e == float("inf") else round(e, 4)
    return A, R, detail


def cmd_check(runs_dir):
    """Print each run's error under the ground-truth adapter to check the ground-truth code; no verdict."""
    for d in sorted(Path(runs_dir).iterdir()):
        if not d.is_dir(): continue
        src = d.name.split("_")[0]; W = LOAD[src](d); s = SRC[src]; t = M.truth(M.TEST[s])
        print(d.name, "window", len(W), {k: (lambda r: (round(r[0], 4), r[1]))(unit_err(W, k, (t[k][1], t[k][2], t[k][3]))) for k in FEATS[src] if t[k][0] == "same"})


def cmd_judge(runs_dir):
    A, R, detail = collect(runs_dir); n = {m: len(r) for m, r in R.items()}; assert len(set(n.values())) == 1 and n["DEEPSEEK"] == 48, n
    v, m = judge(R)
    json.dump({"verdict": v, **m, "adapters": A, "detail": detail, "units": R}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1, default=str)
    rt = m["rate"]
    basis = (f"24 runs, 48 cells: DeepSeek adapter judged correct {rt['DEEPSEEK']:.3f}; control " + ",".join(f"{b} {x:.3f}" for b, x in rt.items() if b != "DEEPSEEK" and not b.startswith("OPEN_")) +
             f"(best: {m['best_base']}); Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; designer cells with severe errors {m['gross_llm']}. Report only: open models " + ",".join(f"{b} {x:.3f}" for b, x in rt.items() if b.startswith("OPEN_")) + "See judge.json for each run.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"delta": m["delta"], "ci90": m["ci90"], "rate": rt, "gross_llm": m["gross_llm"]}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template)." + basis, "--basis", basis,
       "--limitations", "Loopback with netem, not a wide-area network; the RFC source has only one scored feature (loss rate); Chrome loopback call has video only; ground truth is computed from packet captures under the pre-registration definition, and the W3C byte count assumes a 10-byte SRTP authentication tag.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]; rd = sys.argv[sys.argv.index("--runs") + 1] if "--runs" in sys.argv else str(OUT / "runs")
    if c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge(rd)
    elif c == "check": cmd_check(sys.argv[2])
