#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real-trace windows of hd720-realtrace-ch-v1 (2026-10-05, rule written before it was run). Rule hd720_real8_v1, seed
20261005, with the window, gap-filling, floor and queue rules of make_hd720_real_profiles_v1.py (its functions are imported):
  1. Only traces whose source is ucc_4g or chorus in data/llm_kp/corpus_v1.jsonl, excluding any trace named in the header
     trace_id of a .profile under scripts/alphartc (hd_r1 and hd_r2 of profiles/hd720 included) or in the testbed's
     staleness_profiles directory.
  2. Non-overlapping 120 s windows with at least 108 valid seconds; a window mean in [1200, 2000) goes to the low pool and
     one in [2000, 3000] to the high pool (the R1 and R2 tiers of hd720-closedloop-v1).
  3. Eligible windows are sorted by (trace_id, start second); random.Random(20261005) alternately picks from the low and the
     high pool, 8 windows in all (4 each), at most one window per trace.
  4. Per-second rates rounded, floor 30 kbit/s, 50 ms delay, no random loss; queue packets = ceil(95th percentile of the
     window's per-second rate x 250 ms / 9600 bit).
Reads only the corpus and writes only scripts/alphartc/deploy/profiles/hd720_real8/ (hd_t1 to hd_t8 and provenance.json).
Usage: python3 make_hd720_real8_profiles_v1.py; --selftest runs only the self-test of the original rule.
"""
import json, random, re, sys
from pathlib import Path
HERE = Path(__file__).resolve(); sys.path.insert(0, str(HERE.parent))
import make_hd720_real_profiles_v1 as V1
OUT = HERE.parent / "profiles" / "hd720_real8"; SEED, N_PER = 20261005, 4
BANDS = [("low", 1200.0, 2000.0, False), ("high", 2000.0, 3000.0, True)]


def used_traces():
    used = set()
    for p in list((V1.ROOT / "scripts/alphartc").rglob("*.profile")) + list(Path("/path/to/alphartc/LLM4Band/staleness_profiles").glob("*.profile")):
        if OUT in p.parents: continue
        for m in re.finditer(r"trace_id=(\S+)", p.read_text(errors="ignore")): used.add(m.group(1))
    return used


def main():
    rows = [json.loads(l) for l in open(V1.CORPUS)]; used = used_traces(); OUT.mkdir(parents=True, exist_ok=True)
    assert {"chorus/downlink-cellular_hsr_16", "ucc_4g/train/A_2017.12.18_07.25.15"} <= used, "the traces of hd_r1 and hd_r2 were not excluded"
    pool = []
    for tr in sorted((r for r in rows if r["source"] in ("ucc_4g", "chorus") and r["capacity_mbps"] is not None and r["trace_id"] not in used), key=lambda r: r["trace_id"]):
        pool += V1.windows(tr)
    pool.sort(key=lambda w: (w["trace_id"], w["start_s"])); rng = random.Random(SEED); chosen = []; pools = {}
    for _ in range(N_PER):
        for band, lo, hi, inc in BANDS:
            cand = [w for w in pool if V1.in_band(w["mean_kbps"], lo, hi, inc) and all(w["trace_id"] != c["trace_id"] for c in chosen)]
            pools.setdefault(band, {"n_windows_first_draw": len(cand), "by_source": {s: sum(1 for w in cand if w["source"] == s) for s in ("ucc_4g", "chorus")}})
            w = rng.choice(cand); w = dict(w, band=band); chosen.append(w)
    rec = {}
    for i, w in enumerate(chosen, 1):
        name = f"hd_t{i}"; qp = V1.queue_packets(V1.p95(w["rates"]))
        hdr = [f"# trace_id={w['trace_id']} source={w['source']} env={w['env']} window=[{w['start_s']},{w['start_s'] + V1.WIN})s mean_kbps={w['mean_kbps']:.1f} valid_seconds={w['n_valid']} queue_packets={qp}",
               f"# hd720-realtrace-ch-v1 rule hd720_real8_v1 seed {SEED}, {w['band']} profile; latency {V1.DELAY} ms, no random packet loss, per-second rate floor {V1.FLOOR} kbit/s"]
        lines = list(hdr)
        for j, r in enumerate(w["rates"]):
            lines.append(f"rate {r}")
            if j == 0: lines += [f"delay {V1.DELAY}", "loss 0"]
            lines.append("wait 1")
        p = OUT / f"{name}.profile"; p.write_text("\n".join(lines) + "\n")
        rec[name] = {"kind": "real", "band": w["band"], "trace_id": w["trace_id"], "source": w["source"], "env": w["env"], "start_s": w["start_s"], "mean_kbps": w["mean_kbps"],
                     "n_valid": w["n_valid"], "p95_kbps": V1.p95(w["rates"]), "queue_packets": qp, "sha256": V1.sha(p)}
    (OUT / "provenance.json").write_text(json.dumps({"rule": "hd720_real8_v1", "seed": SEED, "corpus_sha256": V1.sha(V1.CORPUS), "script_sha256": V1.sha(HERE), "excluded_used_traces": len(used),
                                                      "candidate_pools": pools, "profiles": rec}, ensure_ascii=False, indent=1))
    print(json.dumps({k: {kk: v[kk] for kk in ("band", "trace_id", "source", "env", "start_s", "mean_kbps", "queue_packets")} for k, v in rec.items()}, ensure_ascii=False, indent=0))


if __name__ == "__main__":
    V1.selftest() if "--selftest" in sys.argv else main()
