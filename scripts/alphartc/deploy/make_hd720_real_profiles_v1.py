#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Link profiles of hd720-closedloop-v1 (2026-10-03). Rule hd720_real_v1, seed 20261003, written down (here and in the
registry notes) before it was run.
Real-trace windows R1 and R2:
  1. Only traces whose source is ucc_4g or chorus in data/llm_kp/corpus_v1.jsonl, excluding any trace named in the header
     trace_id of a .profile under scripts/alphartc or in the testbed's staleness_profiles directory.
  2. Each trace is cut into non-overlapping 120 s windows from second 0; a window qualifies with at least 108 valid
     (non-empty) seconds; an empty second takes the previous valid value, and an empty first second the window's first
     valid value.
  3. The window mean is taken over valid seconds (Mbps x 1000 = kbit/s); R1 needs a mean in [1200, 2000) kbit/s, R2 in
     [2000, 3000] kbit/s.
  4. Eligible windows are sorted by (trace_id, start second); random.Random(20261003) first picks one window from the R1
     pool, then one from the R2 pool without R1's trace.
  5. Per-second rates rounded to integer kbit/s, floor 30; 50 ms delay, no random loss; queue packets = ceil(95th
     percentile of the window's per-second rate x 250 ms / 9600 bit).
Constant profiles: C1, C2, C3 and C8 at 1, 2, 3 and 8 Mbps, 120 s each, queue packets = ceil(capacity x 250 ms / 9600 bit),
i.e. 27, 53, 79 and 209; also G4 (4 Mbps, 105 packets) and CAL20 (20 Mbps, 521 packets) for gating and calibration, all
120 s, 50 ms delay, no loss.
Reads only the corpus and writes only scripts/alphartc/deploy/profiles/hd720/. Usage: python3 make_hd720_real_profiles_v1.py;
--selftest checks only the rule functions (including windows that must be rejected).
"""
import hashlib, json, math, random, re, sys
from pathlib import Path
HERE = Path(__file__).resolve(); ROOT = HERE.parents[3]; CORPUS = ROOT / "data/llm_kp/corpus_v1.jsonl"; OUT = HERE.parent / "profiles" / "hd720"
SEED, WIN, MIN_VALID, FLOOR, DELAY = 20261003, 120, 108, 30, 50
BANDS = {"hd_r1": (1200.0, 2000.0, False), "hd_r2": (2000.0, 3000.0, True)}
CONST = {"hd_c1": 1000, "hd_c2": 2000, "hd_c3": 3000, "hd_c8": 8000, "hd_g4": 4000, "hd_cal20": 20000}


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def queue_packets(kbps): return math.ceil(kbps * 250.0 / 9600.0)


def p95(xs):
    s = sorted(xs); k = (len(s) - 1) * 0.95; f = math.floor(k); c = min(f + 1, len(s) - 1); return s[f] + (s[c] - s[f]) * (k - f)


def windows(tr):
    cap = tr["capacity_mbps"]; out = []
    for s in range(0, len(cap) - WIN + 1, WIN):
        w = cap[s:s + WIN]; valid = [v for v in w if v is not None]
        if len(valid) < MIN_VALID: continue
        mean = sum(valid) * 1000.0 / len(valid); filled = []; last = valid[0]
        for v in w:
            last = v if v is not None else last; filled.append(last)
        rates = [max(FLOOR, round(v * 1000.0)) for v in filled]
        out.append({"trace_id": tr["trace_id"], "source": tr["source"], "env": tr.get("mobility_or_env"), "start_s": s, "mean_kbps": mean, "n_valid": len(valid), "rates": rates})
    return out


def in_band(m, lo, hi, inc): return lo <= m <= hi if inc else lo <= m < hi


def used_traces():
    used = set()
    for p in list((ROOT / "scripts/alphartc").rglob("*.profile")) + list(Path("/path/to/alphartc/LLM4Band/staleness_profiles").glob("*.profile")):
        if OUT in p.parents: continue
        for m in re.finditer(r"trace_id=(\S+)", p.read_text(errors="ignore")): used.add(m.group(1))
    return used


def write_profile(name, rates, header):
    lines = list(header)
    for j, r in enumerate(rates):
        lines.append(f"rate {r}")
        if j == 0: lines += [f"delay {DELAY}", "loss 0"]
        lines.append("wait 1")
    p = OUT / f"{name}.profile"; p.write_text("\n".join(lines) + "\n"); return p


def main():
    rows = [json.loads(l) for l in open(CORPUS)]; used = used_traces(); OUT.mkdir(parents=True, exist_ok=True); rec = {}
    for name, kbps in CONST.items():
        p = OUT / f"{name}.profile"
        p.write_text(f"# {name}: constant {kbps} kbps, delay {DELAY} ms, loss 0, 120 s. hd720-closedloop-v1, queue packets {queue_packets(kbps)}.\nrate {kbps}\ndelay {DELAY}\nloss 0\nwait 120\n")
        rec[name] = {"kind": "constant", "kbps": kbps, "queue_packets": queue_packets(kbps), "sha256": sha(p)}
    pool = []
    for tr in sorted((r for r in rows if r["source"] in ("ucc_4g", "chorus") and r["capacity_mbps"] is not None and r["trace_id"] not in used), key=lambda r: r["trace_id"]):
        pool += windows(tr)
    pool.sort(key=lambda w: (w["trace_id"], w["start_s"])); rng = random.Random(SEED); pools = {}; chosen = {}
    for name, (lo, hi, inc) in BANDS.items():
        cand = [w for w in pool if in_band(w["mean_kbps"], lo, hi, inc) and all(w["trace_id"] != c["trace_id"] for c in chosen.values())]
        pools[name] = {"n_windows": len(cand), "by_source": {s: sum(1 for w in cand if w["source"] == s) for s in ("ucc_4g", "chorus")}}
        chosen[name] = rng.choice(cand)
    for name, w in chosen.items():
        qp = queue_packets(p95(w["rates"]))
        hdr = [f"# trace_id={w['trace_id']} source={w['source']} env={w['env']} window=[{w['start_s']},{w['start_s'] + WIN})s mean_kbps={w['mean_kbps']:.1f} valid_seconds={w['n_valid']} queue_packets={qp}",
               f"# corpus_v1 sha256={sha(CORPUS)[:16]} rule=hd720_real_v1 seed={SEED}; 1s values, Mbps to kbit/s, gaps carried forward, round to int, floor {FLOOR}"]
        p = write_profile(name, w["rates"], hdr)
        rec[name] = {"kind": "real", "trace_id": w["trace_id"], "source": w["source"], "env": w["env"], "start_s": w["start_s"], "mean_kbps": w["mean_kbps"], "n_valid": w["n_valid"],
                     "p95_kbps": p95(w["rates"]), "queue_packets": qp, "sha256": sha(p)}
    (OUT / "provenance.json").write_text(json.dumps({"rule": "hd720_real_v1", "seed": SEED, "corpus_sha256": sha(CORPUS), "script_sha256": sha(HERE), "excluded_used_traces": len(used),
                                                      "candidate_pools": pools, "profiles": rec}, ensure_ascii=False, indent=1))
    print(json.dumps({"pools": pools, "chosen": {k: {kk: v[kk] for kk in ("trace_id", "start_s", "mean_kbps", "queue_packets")} for k, v in rec.items() if v["kind"] == "real"}}, ensure_ascii=False))


def selftest():
    tr = {"trace_id": "t", "source": "ucc_4g", "capacity_mbps": [1.5] * 110 + [None] * 10 + [2.5] * 100 + [None] * 20}
    w = windows(tr)
    assert len(w) == 1 and w[0]["start_s"] == 0 and w[0]["n_valid"] == 110 and w[0]["rates"][-1] == 1500, w
    assert in_band(1500, 1200, 2000, False) and not in_band(2000, 1200, 2000, False) and in_band(3000, 2000, 3000, True)
    assert queue_packets(1000) == 27 and queue_packets(2000) == 53 and queue_packets(3000) == 79 and queue_packets(8000) == 209 and queue_packets(20000) == 521
    print("Tier rules self-test passed (including insufficient valid seconds, windows that should have been rejected)")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
