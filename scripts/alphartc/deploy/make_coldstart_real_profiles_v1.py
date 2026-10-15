#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real-trace link profiles for the cold-start scenarios (rule coldstart_real_v1, seed 20261001). The rule is given verbatim
in registry/preregistrations/prereg_22.md.
Reads only data/llm_kp/corpus_v1.jsonl and writes only scripts/alphartc/deploy/profiles/coldstart_real/. Profiles are written
as in make_lowbw_real_profiles_v1.py.
Usage: python3 scripts/alphartc/deploy/make_coldstart_real_profiles_v1.py
"""
import hashlib, json, random
from pathlib import Path
HERE = Path(__file__).resolve(); ROOT = HERE.parents[3]; CORPUS = ROOT / "data/llm_kp/corpus_v1.jsonl"; OUT = HERE.parent / "profiles" / "coldstart_real"
SCEN = {"4g_car": ("ucc_4g", "car"), "4g_ped": ("ucc_4g", "pedestrian"), "3g_tram": ("norway_hsdpa", "tram"), "3g_metro": ("norway_hsdpa", "metro")}
WIN, FLOOR, MAX_CLAMP, LO, HI, PER_TRACE, PER_SCEN, SEED, DELAY, LOSS = 120, 30, 12, 200.0, 4000.0, 3, 36, 20261001, 50, 0


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def windows(tr):
    cap = tr["capacity_mbps"]; out = []
    for s in range(0, len(cap) - WIN + 1, WIN):
        w = cap[s:s + WIN]
        if any(v is None for v in w): continue
        kb = [v * 1000.0 for v in w]; mean = sum(kb) / WIN; ncl = sum(round(x) < FLOOR for x in kb)
        if LO <= mean <= HI and ncl <= MAX_CLAMP: out.append({"trace_id": tr["trace_id"], "start_s": s, "mean_kbps": mean, "n_clamped": ncl, "rates": [max(FLOOR, round(x)) for x in kb]})
    return out


def main():
    rows = [json.loads(l) for l in open(CORPUS)]; rng = random.Random(SEED); OUT.mkdir(parents=True, exist_ok=True); rec = []
    for name, (src, mob) in SCEN.items():
        pool = []
        for tr in sorted((r for r in rows if r["source"] == src and r["mobility_or_env"] == mob and r["capacity_mbps"] is not None), key=lambda r: r["trace_id"]):
            w = windows(tr); pool += (sorted(rng.sample(w, PER_TRACE), key=lambda x: x["start_s"]) if len(w) > PER_TRACE else w)
        chosen = rng.sample(pool, PER_SCEN) if len(pool) > PER_SCEN else pool
        for i, w in enumerate(chosen, 1):
            lines = [f"# trace_id={w['trace_id']} source={src} mobility={mob} window=[{w['start_s']},{w['start_s'] + WIN})s mean_kbps={w['mean_kbps']:.1f} clamped_seconds={w['n_clamped']}",
                     f"# corpus_v1 sha256={sha(CORPUS)[:16]} rule=coldstart_real_v1 seed={SEED}; 1s values, Mbps to kbit/s, round to int, floor {FLOOR}"]
            for j, r in enumerate(w["rates"]):
                lines.append(f"rate {r}")
                if j == 0: lines += [f"delay {DELAY}", f"loss {LOSS}"]
                lines.append("wait 1")
            p = OUT / f"{name}_{i:02d}.profile"; p.write_text("\n".join(lines) + "\n")
            rec.append({"profile": p.name, "scenario": name, "trace_id": w["trace_id"], "start_s": w["start_s"], "mean_kbps": w["mean_kbps"], "n_clamped": w["n_clamped"], "sha256": sha(p)})
        print(name, "candidate", len(pool), "select", len(chosen), "different traces", len({w["trace_id"] for w in chosen}))
    (OUT / "provenance.json").write_text(json.dumps({"rule": "coldstart_real_v1", "seed": SEED, "corpus_sha256": sha(CORPUS), "script_sha256": sha(HERE), "profiles": rec}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
