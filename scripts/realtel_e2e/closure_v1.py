#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deployment closure on a real client (realtel-closure-v1): can the estimator get usable input from browser telemetry alone? A headless Chrome loopback call exports the receiver's
full getStats() every 60 ms; packets rebuilt from the capture (send time from abs-send-time) feed collector v5 (SlidingCollectorV5), which gives the correct interface. Each method
computes the 15 features from pairs of getStats() snapshots into the same slots (missing set to 0, f12 to f14 set to training constants); all feed the same estimator
(the challenge baseline, baseline.onnx), whose output is compared with its output on the correct interface. First version; closure_v2.py imports all its functions. Needs onnxruntime.
Usage: closure_v1.py prompt | design ROUND | devcheck ROUND | freeze ROUND | judge [--selftest]; prompt writes the designer prompt from two adjacent dev snapshots, design asks the hosted
designer for feature code (round 2 sends back only the round-1 dev error), devcheck reports exceptions and missing shares on the dev run, freeze fixes a round's code, judge scores and records.
"""
import hashlib, json, math, random, statistics, struct, subprocess, sys, traceback
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_e2e_v1 as E
from spec_collector_v5 import SlidingCollectorV5  # noqa: E402
from spec_collector import MEDIA_PROPORTION  # noqa: E402
OUT = ROOT / "experiments/results/realtel_closure_v1"; ID = "realtel-closure-v1"; DELTA = 0.10; SEED = 20261007; WARM = 50
ONNX = ROOT / "experiments/results/switch_deploy_v1/models/schaferct_public.onnx"; SRTP_TAG = 10
SPEC = (ROOT / "data/audit_bench_v1/official_feature_spec.txt").read_text()


def snapshots(d):
    S, sdp = [], ""
    for l in open(d / "stats.jsonl"):
        j = json.loads(l)
        if "sdp_offer" in j: sdp = j["sdp_offer"]
        if "report" not in j: continue
        v = [x for x in j["report"].values() if x.get("type") == "inbound-rtp" and x.get("kind") == "video"]
        if v: S.append((v[0]["timestamp"], j["report"]))
    return S, sdp


def ext_id(sdp, uri="abs-send-time"):
    for l in sdp.splitlines():
        if l.startswith("a=extmap:") and uri in l: return int(l.split(":")[1].split()[0].split("/")[0])
    return None


def packets(d, S, sdp):
    """Extract the RTP packets sent to the receiver (media and RTX SSRCs taken from getStats) from the capture as collector input records."""
    ss = set()
    for _, rep in S[-1:]:
        for x in rep.values():
            if x.get("type") == "inbound-rtp":
                ss.add(x["ssrc"])
                if x.get("rtxSsrc"): ss.add(x["rtxSsrc"])
    eid = ext_id(sdp); out = []
    for t, pr, sp, dp, u, ul in E.pcap(d / "cap.pcap"):
        if pr != "udp" or len(u) < 12 or (u[0] >> 6) != 2 or 192 <= u[1] <= 223: continue
        ssrc = struct.unpack(">I", u[8:12])[0]
        if ssrc not in ss: continue
        cc = u[0] & 15; hl = 12 + 4 * cc; ast = None
        if u[0] & 0x10:
            L = struct.unpack(">H", u[hl + 2:hl + 4])[0]; body = u[hl + 4:hl + 4 + 4 * L]; i = 0
            while i < len(body):
                b = body[i]
                if b == 0: i += 1; continue
                e, ln = b >> 4, (b & 15) + 1
                if e == eid and ln == 3: ast = int.from_bytes(body[i + 1:i + 4], "big")
                i += 1 + ln
            hl += 4 + 4 * L
        if ast is None: continue
        body_len = ul - hl - SRTP_TAG; pad = bool(u[0] & 0x20)
        out.append({"send_time_ms": ast / 2 ** 18 * 1000.0, "arrival_time_ms": t * 1000.0, "payload_type": u[1] & 0x7F, "header_length": hl,
                    "payload_size": 0 if pad else body_len, "padding_length": body_len if pad else 0, "sequence_number": struct.unpack(">H", u[2:4])[0], "ssrc": ssrc})
    return out


def truth_obs(S, P):
    """Replay packets into SlidingCollectorV5 and take the reference 150-value observation at each snapshot time."""
    c = SlidingCollectorV5(clock=lambda: 0.0); P = sorted(P, key=lambda p: p["arrival_time_ms"]); j = 0; obs, truthful = [], []
    for T, _ in S:
        while j < len(P) and P[j]["arrival_time_ms"] < T: c.report_states(P[j]); j += 1
        obs.append(c.observation(now_ms=T)); truthful.append(c.last_truthful_media)
    return np.array(obs, float), truthful


def assemble(S, feat):
    """Build 150-value observations from feat(prev, cur) over the collector's slots (newest first), with missing values set to 0 and f12 to f14 set to constants."""
    cache = {}
    def F(a, b):
        if (a, b) not in cache:
            try: v = feat(S[a][1], S[b][1]); v = [x if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None for x in (list(v) + [None] * 15)[:15]]; err = 0
            except Exception: v, err = [None] * 15, 1
            cache[(a, b)] = (v, err)
        return cache[(a, b)]
    O, errs, calls = [], 0, 0
    for i in range(len(S)):
        if i < WARM: O.append([0.0] * 150); continue
        sl = [(i - k - 1, i - k) for k in range(5)] + [(i - 10 * (k + 1), i - 10 * k) for k in range(5)]
        vals = []
        for a, b in sl:
            v, e = F(a, b); errs += e; calls += 1; vals.append(v)
        o = [(vals[s][f] if vals[s][f] is not None else 0.0) for f in range(15) for s in range(10)]
        # The last 30 slots (features 12 to 14, media shares) are overwritten with training constants, as the deployed collector does.
        o[-30:] = MEDIA_PROPORTION; O.append(o)
    return np.array(O, float), errs / max(calls, 1), cache


def video_in(rep):
    v = [x for x in rep.values() if x.get("type") == "inbound-rtp" and x.get("kind") == "video"]; return v[0] if v else {}


def mapping_feat(mp):
    """Turn a field mapping (name, diff, scale) into a feature function that reads the inbound video stream of getStats(); unreadable fields are missing."""
    def feat(prev, cur):
        a, b = video_in(prev), video_in(cur); out = [None] * 15
        for k, m in enumerate(mp):
            if m is None: continue
            name, diff, sc = m; v1 = b.get(name)
            if not isinstance(v1, (int, float)) or isinstance(v1, bool): continue
            if diff:
                v0 = a.get(name)
                if not isinstance(v0, (int, float)) or isinstance(v0, bool): continue
                out[k] = (v1 - v0) * sc
            else: out[k] = v1 * sc
        return out
    return feat


def _imp(name, *a, **k):
    """Import hook for the sandbox: allow only math, the one module the prompt permits."""
    if name == "math": return math
    raise ImportError(name)


def code_feat(path):
    ns = {"__builtins__": {"__import__": _imp, "abs": abs, "min": min, "max": max, "sum": sum, "len": len, "float": float, "int": int, "range": range, "list": list, "dict": dict,
                           "isinstance": isinstance, "sorted": sorted, "any": any, "all": all, "round": round, "zip": zip, "enumerate": enumerate, "str": str,
                           "bool": bool, "ValueError": ValueError, "KeyError": KeyError, "TypeError": TypeError, "ZeroDivisionError": ZeroDivisionError, "Exception": Exception, "None": None},
          "math": math}
    exec(compile(Path(path).read_text(), str(path), "exec"), ns); return ns["features"]


def run_onnx(obs):
    import onnxruntime as ort
    so = ort.SessionOptions(); so.intra_op_num_threads = 1; so.inter_op_num_threads = 1
    s = ort.InferenceSession(str(ONNX), sess_options=so, providers=["CPUExecutionProvider"]); sh = tuple(s.get_inputs()[1].shape)
    h = np.zeros(sh, np.float32); c = np.zeros(sh, np.float32); pr = np.empty(len(obs), np.float32)
    for t in range(len(obs)):
        y, h, c = s.run(None, {"obs": obs[t:t + 1].reshape(1, 1, -1).astype(np.float32), "hidden_states": h, "cell_states": c}); pr[t] = y[0, 0, 0]
    return pr


def deviation(y, y0):
    m = np.arange(len(y)) >= WARM; return float(np.median(np.abs(y[m] - y0[m]) / np.maximum(y0[m], 1.0)))


TEMPLATE = """A learned bandwidth estimator for real-time video runs at the receiver of a WebRTC call. Every 60 ms it reads 150 numbers: 15 features, each computed over the 5 most recent 60 ms monitor intervals and the 5 most recent 600 ms monitor intervals. The official definition of the 15 features:
{spec}

We want to deploy it in an unmodified browser, where the only telemetry is RTCPeerConnection.getStats() at the receiver, polled about every 60 ms. Below are two consecutive real getStats() results from this receiver (one audio and one video stream are received), as JSON objects mapping stats id to stats dictionary:
PREVIOUS:
{prev}
CURRENT:
{cur}

Write a Python function `features(prev, cur)` that takes two such dictionaries (the window is the interval between their timestamps; the same function is also called on reports about 600 ms apart for the long intervals) and returns a list of 15 values, one per feature in the order above and in the units of the definition. Compute a feature only when getStats gives what is needed to compute it for this window; return None for a feature that getStats cannot provide. Only the `math` module is available; do not import anything. The function must not raise on missing keys. Answer with the code in a single ```python block. Keep your reasoning brief."""


def build_prompt():
    S, _ = snapshots(OUT / "dev/dev_r1500_L1"); i = len(S) // 2
    trim = lambda rep: {k: v for k, v in rep.items() if v.get("type") not in ("certificate",)}
    return TEMPLATE.format(spec=SPEC.split("are as follows.")[1].split("The indices")[0].strip(), prev=json.dumps(trim(S[i - 1][1]), indent=0), cur=json.dumps(trim(S[i][1]), indent=0))


def ask_code(prompt, tag):
    import coldstart_rule_v1 as CR
    import re
    r = CR.ask(prompt, 48000); txt = r["choices"][0]["message"].get("content") or ""
    m = re.findall(r"```python\s*(.*?)```", txt, re.S); code = m[-1] if m else ""
    (OUT / f"design_{tag}.py").write_text(code); (OUT / f"design_{tag}.raw.json").write_text(json.dumps({"usage": r.get("usage"), "content": txt}, ensure_ascii=False))
    print(tag, "lines of code", len(code.splitlines()), "output token", (r.get("usage") or {}).get("completion_tokens"))


def devcheck(tag):
    S, _ = snapshots(OUT / "dev/dev_r1500_L1"); f = code_feat(OUT / f"design_{tag}.py"); errs, nones, tb = 0, [0] * 15, None
    for i in range(1, len(S)):
        for a, b in ((i - 1, i), (max(0, i - 10), i)):
            try:
                v = list(f(S[a][1], S[b][1]))
                for k in range(15):
                    if k >= len(v) or v[k] is None: nones[k] += 1
            except Exception:
                errs += 1; tb = tb or traceback.format_exc(limit=3)
    n = 2 * (len(S) - 1); print(tag, "call", n, "anomaly", errs, "missing share per feature", [round(x / n, 2) for x in nones])
    return errs, tb


def judge(D, seed=SEED, B=5000):
    """Return delta = mean deviation of the best non-LLM arm (all-missing included) minus that of the LLM code, its 90% run-bootstrap interval and the best arm."""
    runs = sorted(D["LLM_CODE"]); base = [m for m in D if m.startswith("MAP_") and m != "MAP_LLM" or m == "ZERO"]
    mean = lambda m, sel: sum(D[m][r] for r in sel) / len(sel)
    best = min(base, key=lambda m: mean(m, runs))
    d = lambda sel: mean(best, sel) - mean("LLM_CODE", sel)
    Dl = d(runs); rng = random.Random(seed); boots = sorted(d([rng.choice(runs) for _ in runs]) for _ in range(B)); lo, hi = boots[int(0.05 * B)], boots[int(0.95 * B) - 1]
    return Dl, lo, hi, best


def selftest():
    D = {"LLM_CODE": {f"r{i}": 0.1 for i in range(8)}, "MAP_A": {f"r{i}": 0.5 for i in range(8)}, "ZERO": {f"r{i}": 0.9 for i in range(8)}, "MAP_LLM": {f"r{i}": 0.05 for i in range(8)}}
    Dl, lo, hi, best = judge(D); assert best == "MAP_A" and abs(Dl - 0.4) < 1e-9 and lo > 0
    D["LLM_CODE"] = {f"r{i}": 0.6 for i in range(8)}; assert judge(D)[0] < 0
    S = [(1000.0 + 60 * i, {"x": {"type": "inbound-rtp", "kind": "video", "packetsReceived": i}}) for i in range(80)]
    O, er, _ = assemble(S, lambda p, c: [video_in(c)["packetsReceived"] - video_in(p)["packetsReceived"]] + [None] * 14)
    assert O[60][0] == 1 and O[60][5] == 10 and er == 0 and O[60][-1] == MEDIA_PROPORTION[-1]
    print("Self-test passed (decision, best control, negative, slots and coverage)")


def cmd_judge():
    runs = sorted(p for p in (OUT / "runs").iterdir() if (p / "OK").exists()); assert len(runs) == 8, len(runs)
    import realtel_adapter_v1 as M, realtel_baselines_v2 as V
    fl = M.TEST["w3c_webrtc_stats"]["fields"]
    Lm = {(j["source"], j["pres"]): j["mapping"] for j in map(json.loads, open(M.OUT / "llm_test_deepseek.jsonl")) if j.get("ok")}[("w3c_webrtc_stats", 0)]
    arms = {"LLM_CODE": code_feat(OUT / "design_frozen.py"),
            "MAP_LLM": mapping_feat([None if m is None else (fl[m["source"]][0], m["diff"], m["scale"]) for m in Lm]), "ZERO": lambda p, c: [None] * 15}
    Sc = V.classic_scores(); Sc.update(json.load(open(V.OUT / "scores_valentine.json"))); Sc.update(json.load(open(V.OUT / "scores_embed.json"))); taus = json.load(open(V.OUT / "judge.json"))["baselines"]
    for b, sc in Sc.items():
        dec = V.decide(sc["test"]["w3c_webrtc_stats"], taus[b]["tau"])
        arms["MAP_" + b] = mapping_feat([None if j is None else (fl[j][0], M.is_cum(fl[j][2]), M.unit_scale(k, fl[j][0], fl[j][2])) for k, j in enumerate(dec)])
    if (OUT / "design_open_frozen.py").exists(): arms["OPEN_CODE"] = code_feat(OUT / "design_open_frozen.py")
    D = {m: {} for m in arms}; ERR = {}; FE = {m: {} for m in arms}
    for d in runs:
        S, sdp = snapshots(d); P = packets(d, S, sdp); T0, truthful = truth_obs(S, P); y0 = run_onnx(T0)
        for m, f in arms.items():
            O, er, _ = assemble(S, f); y = run_onnx(O); D[m][d.name] = deviation(y, y0)
            if m == "LLM_CODE": ERR[d.name] = er
            idx = np.arange(len(S)) >= WARM
            FE[m][d.name] = {f_: (float(np.median(np.abs(O[idx, f_ * 10] - T0[idx, f_ * 10]) / np.maximum(np.abs(T0[idx, f_ * 10]), 1e-9))) if np.any(T0[idx, f_ * 10] != 0) else None) for f_ in range(12)}
        print(d.name, {m: round(D[m][d.name], 3) for m in D}, flush=True)
    Dl, lo, hi, best = judge(D); gross = max(ERR.values()) > 0.05
    v = "does not hold" if (Dl <= 0 or gross) else ("holds" if lo > 0 and Dl >= DELTA else "direction only")
    mean = {m: sum(D[m].values()) / len(D[m]) for m in D}
    json.dump({"verdict": v, "delta": Dl, "ci90": [lo, hi], "best_base": best, "mean_dev": mean, "dev": D, "llm_code_err_rate": ERR, "feature_err": FE}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    basis = (f"8 runs, deviation of estimator output relative to ground-truth input (median of stepwise relative deviation, averaged over runs): LLM code {mean['LLM_CODE']:.3f}; best non-LLM {best} {mean[best]:.3f}; all missing {mean['ZERO']:.3f}; Δ {Dl:+.3f}, 90% interval [{lo:+.3f}, {hi:+.3f}]; LLM code has the largest anomaly rate {max(ERR.values()):.3f}. Report only: LLM field mapping {mean['MAP_LLM']:.3f}" + (f", open-source code {mean['OPEN_CODE']:.3f}" if "OPEN_CODE" in mean else "") +
             "; average deviation of each method " + ",".join(f"{m} {x:.3f}" for m, x in mean.items()) + ".")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"delta": Dl, "ci90": [lo, hi], "mean_dev": mean, "best_base": best}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template)." + basis, "--basis", basis,
       "--limitations", "Loopback interface with netem, single estimator (Schaferct baseline), open-loop comparison of estimator output rather than closed-loop video quality; getStats cannot obtain per-packet delay, so delay-type features cannot be produced by any method; f12 to f14 are overwritten as constants following the deployed system.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "prompt":
        p = build_prompt(); (OUT / "prompt.txt").write_text(p); h = hashlib.sha256(p.encode()).hexdigest(); (OUT / "prompt_sha256.txt").write_text(h); print("prompt length", len(p), "hash", h[:12])
    elif c == "design":
        r = sys.argv[2]; p = (OUT / "prompt.txt").read_text()
        if r == "2": p += "\n\nYour previous function raised this error on real data:\n" + (OUT / "devcheck_r1.txt").read_text() + "\nFix it and return the full function again."
        ask_code(p, f"r{r}")
    elif c == "devcheck":
        e, tb = devcheck(f"r{sys.argv[2]}"); (OUT / f"devcheck_r{sys.argv[2]}.txt").write_text(tb or "")
    elif c == "freeze":
        src = OUT / f"design_r{sys.argv[2]}.py"; dst = OUT / "design_frozen.py"; dst.write_text(src.read_text()); print("freeze", hashlib.sha256(dst.read_bytes()).hexdigest()[:12])
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
