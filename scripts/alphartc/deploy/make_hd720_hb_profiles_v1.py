#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Link profiles of hd720-highbw-ch-v1 (2026-10-05, rule written before it was run). Rule hd720_hb_v1, seed 20261006; the
window, gap-filling, floor, delay and queue rules are imported from make_hd720_real_profiles_v1.py:
  Constant: hb_c3, hb_c6, hb_c10 and hb_c15 at 3, 6, 10 and 15 Mbit/s, 120 s each, 50 ms delay, no random loss,
    queue packets = ceil(capacity x 250 ms / 9600 bit).
  Real-trace windows: only UCC 4G and Chorus traces of data/llm_kp/corpus_v1.jsonl, excluding any trace already used by a
    profile under scripts/alphartc or in the testbed's staleness_profiles directory (hd720 and hd720_real8 included);
    120 s windows with at least 108 valid seconds; hb_t1 takes a mean in [5000, 10000) and hb_t2 in [10000, 15000] kbit/s;
    eligible windows are sorted by (trace_id, start second) and random.Random(20261006) picks one of each, from two
    different traces; per-second rates rounded, floor 30 kbit/s; queue packets = ceil(95th percentile of the window's
    per-second rate x 250 ms / 9600 bit).
The 15 Mbit/s upper end: the estimator output is capped at 20 Mbit/s, and with the patched sender the 720p conference
sources reach about 12 to 16 Mbit/s (hb-calib-explore-v2).
Reads only the corpus and writes only scripts/alphartc/deploy/profiles/hd720_hb/. Usage: python3 make_hd720_hb_profiles_v1.py;
--selftest runs the self-test of the original rule.
"""
import json, random, re, sys
from pathlib import Path
HERE = Path(__file__).resolve(); sys.path.insert(0, str(HERE.parent))
import make_hd720_real_profiles_v1 as V1  # noqa: E402
OUT = HERE.parent / "profiles" / "hd720_hb"; SEED = 20261006
CONST = {"hb_c3": 3000, "hb_c6": 6000, "hb_c10": 10000, "hb_c15": 15000}
BANDS = [("hb_t1", 5000.0, 10000.0, False), ("hb_t2", 10000.0, 15000.0, True)]


def used_traces():
    used = set()
    for p in list((V1.ROOT / "scripts/alphartc").rglob("*.profile")) + list(Path("/path/to/alphartc/LLM4Band/staleness_profiles").glob("*.profile")):
        if OUT in p.parents: continue
        for m in re.finditer(r"trace_id=(\S+)", p.read_text(errors="ignore")): used.add(m.group(1))
    return used


def main():
    OUT.mkdir(parents=True, exist_ok=True); rec = {}
    for name, kbps in CONST.items():
        p = OUT / f"{name}.profile"; q = V1.queue_packets(kbps)
        p.write_text(f"# {name}: constant {kbps} kbps, delay {V1.DELAY} ms, loss 0, 120 s. hd720-highbw-ch-v1, queue packets {q}.\nrate {kbps}\ndelay {V1.DELAY}\nloss 0\nwait 120\n")
        rec[name] = {"kind": "constant", "kbps": kbps, "queue_packets": q, "sha256": V1.sha(p)}
    rows = [json.loads(l) for l in open(V1.CORPUS)]; used = used_traces()
    assert "ucc_4g/static/A_2017.11.22_10.06.58" in used, "the traces of hd720_real8 were not excluded"
    pool = []
    for tr in sorted((r for r in rows if r["source"] in ("ucc_4g", "chorus") and r["capacity_mbps"] is not None and r["trace_id"] not in used), key=lambda r: r["trace_id"]):
        pool += V1.windows(tr)
    pool.sort(key=lambda w: (w["trace_id"], w["start_s"])); rng = random.Random(SEED); chosen = {}; pools = {}
    for name, lo, hi, inc in BANDS:
        cand = [w for w in pool if V1.in_band(w["mean_kbps"], lo, hi, inc) and all(w["trace_id"] != c["trace_id"] for c in chosen.values())]
        pools[name] = {"n_windows": len(cand), "by_source": {s: sum(1 for w in cand if w["source"] == s) for s in ("ucc_4g", "chorus")}}
        chosen[name] = rng.choice(cand)
    for name, w in chosen.items():
        qp = V1.queue_packets(V1.p95(w["rates"]))
        lines = [f"# trace_id={w['trace_id']} source={w['source']} env={w['env']} window=[{w['start_s']},{w['start_s'] + V1.WIN})s mean_kbps={w['mean_kbps']:.1f} valid_seconds={w['n_valid']} queue_packets={qp}",
                 f"# hd720-highbw-ch-v1 rule hd720_hb_v1 seed {SEED}; latency {V1.DELAY} ms, no random packet loss, per-second rate floor {V1.FLOOR} kbit/s"]
        for j, r in enumerate(w["rates"]):
            lines.append(f"rate {r}")
            if j == 0: lines += [f"delay {V1.DELAY}", "loss 0"]
            lines.append("wait 1")
        p = OUT / f"{name}.profile"; p.write_text("\n".join(lines) + "\n")
        rec[name] = {"kind": "real", "trace_id": w["trace_id"], "source": w["source"], "env": w["env"], "start_s": w["start_s"], "mean_kbps": w["mean_kbps"], "n_valid": w["n_valid"],
                     "p95_kbps": V1.p95(w["rates"]), "queue_packets": qp, "sha256": V1.sha(p)}
    (OUT / "provenance.json").write_text(json.dumps({"rule": "hd720_hb_v1", "seed": SEED, "corpus_sha256": V1.sha(V1.CORPUS), "script_sha256": V1.sha(HERE), "excluded_used_traces": len(used),
                                                      "candidate_pools": pools, "profiles": rec}, ensure_ascii=False, indent=1))
    print(json.dumps({"pools": pools, "profiles": {k: {kk: v.get(kk) for kk in ("kind", "kbps", "trace_id", "env", "mean_kbps", "queue_packets")} for k, v in rec.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    V1.selftest() if "--selftest" in sys.argv else main()
