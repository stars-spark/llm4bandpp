#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-designer-ch-v1: the designer inside the 720p deployed system (arm_ch_schema).
Five synthetic schemas (test_g to test_j, rt_getstats) with frozen maps, four adapters (LLM designer, distribution match, name match, none) plus the true mapping, on hd_c1, hd_c2, hd_r1, hd_r2 with Johnny. Main endpoint: LLM minus the best non-LLM adapter in VMAF over 20 cells; holds if the 90% lower bound is above 0 and the difference is at least 1.5 VMAF, with no cell 10 VMAF below the true mapping.
Usage: hd720_designer_ch_v1.py jobs | smoke | smoke-gate | judge | selftest
"""
import hashlib, json, random, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-designer-ch-v1"); ID = "hd720-designer-ch-v1"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v25.sh"
MAPS = Path("/path/to/testbed/results/obsschema-closedloop-llm4bandpp-v2/maps.json"); MAPS_SHA = "5a22ce3e0dfca21c7ed1ddb7fb5099dd767421ae9f3251aa4f4a9af5990198ea"
ARM = "arm_ch_schema"; CONDS = ["hd_c1", "hd_c2", "hd_r1", "hd_r2"]; CONTENT = "johnny"
SCHEMAS = ["test_g", "test_h", "test_i", "test_j", "rt_getstats"]; METHODS = ["LLM", "DIST", "NAME", "NONE"]; NONLLM = ["DIST", "NAME", "NONE"]
BASE_ENV = dict(AL.ENV[AL.CH]); MIN_D = 1.5; SAFE = 10.0; SEED = 20261006; B = 10000


def maps():
    assert hashlib.sha256(MAPS.read_bytes()).hexdigest() == MAPS_SHA, "Frozen mapping hash mismatch"
    return json.load(open(MAPS))["schemas"]


def jobs():
    AL.prepare(K); C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; M = maps(); J = []
    for cond in CONDS:
        keys = ["CLEAN#1", "CLEAN#2"] + [f"{s}-{m}" for s in SCHEMAS for m in METHODS]; random.Random(f"{ID}/{cond}").shuffle(keys)
        for k in keys:
            env = dict(BASE_ENV); rep = 1
            if k.startswith("CLEAN"): rep = int(k.split("#")[1]); key = "CLEAN"
            else:
                key = k; s, m = k.split("-"); mp = M[s][m] if m != "NONE" else None
                env.update(STALENESS_OBS_SCHEMA=s, STALENESS_OBS_MAP="IDENTITY" if mp is None else json.dumps(mp, separators=(",", ":")))
            J.append({"cond": f"{cond}__{CONTENT}__{key}__r{rep}", "arm": ARM, "profile": str(H.P / f"{cond}.profile"), "rep": rep, "video_id": CONTENT,
                      "queue": H.queue_of(cond), "source": H.source_of(CONTENT, layout), "env": env})
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_designer_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def stats(runs):
    """Return clean[cond] and V[(method, schema, cond)] from the valid runs."""
    clean, V = {}, {}
    for r in runs:
        if not (r.get("valid") and r.get("vmaf") is not None): continue
        key = r["job"].split("__")[2]; cond = r["cond"]
        if key == "CLEAN": clean.setdefault(cond, []).append(r["vmaf"])
        else: s, m = key.split("-"); V[(m, s, cond)] = r["vmaf"]
    return {c: sum(x) / len(x) for c, x in clean.items()}, V


def decide(clean, V):
    cells = [(s, c) for s in SCHEMAS for c in CONDS if all((m, s, c) in V for m in METHODS)]
    if len(cells) < 10: return "inconclusive", {"n_cells": len(cells)}
    best = max(NONLLM, key=lambda m: sum(V[(m, s, c)] for s, c in cells) / len(cells))
    d = [V[("LLM", s, c)] - V[(best, s, c)] for s, c in cells]; D = sum(d) / len(d)
    rng = random.Random(SEED); bs = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(B)); ci = [bs[int(0.05 * B)], bs[int(0.95 * B) - 1]]
    severe = [f"{s}|{c}" for s, c in cells if c in clean and V[("LLM", s, c)] < clean[c] - SAFE]
    v = "does not hold" if (D <= 0 or severe) else ("holds" if ci[0] > 0 and D >= MIN_D else "direction only")
    mean = {m: sum(V[(m, s, c)] for s, c in cells) / len(cells) for m in METHODS}
    dev = {m: sum(abs(V[(m, s, c)] - clean[c]) for s, c in cells if c in clean) / len(cells) for m in METHODS}
    return v, {"n_cells": len(cells), "best_nonllm": best, "delta": D, "ci90": ci, "severe": severe, "cell_diff": {f"{s}|{c}": x for (s, c), x in zip(cells, d)},
               "mean_vmaf": mean, "mean_abs_dev_from_clean": dev, "clean_by_cond": clean, "llm_minus_clean": sum(V[("LLM", s, c)] - clean[c] for s, c in cells if c in clean) / len(cells)}


def selftest():
    clean = {c: 80.0 for c in CONDS}
    def mk(llm, other):
        return {(m, s, c): (llm if m == "LLM" else other) for m in METHODS for s in SCHEMAS for c in CONDS}
    assert decide(clean, mk(80.0, 75.0))[0] == "holds"
    assert decide(clean, mk(80.0, 79.5))[0] == "direction only"
    assert decide(clean, mk(75.0, 80.0))[0] == "does not hold"
    V = mk(80.0, 70.0); V[("LLM", "test_g", "hd_c1")] = 60.0; assert decide(clean, V)[0] == "does not hold"
    assert decide(clean, {k: v for k, v in mk(80.0, 70.0).items() if k[1] in ("test_g",)})[0] == "inconclusive"
    M = maps(); assert set(M) >= set(SCHEMAS) and all(set(M[s]) >= {"LLM", "DIST", "NAME"} for s in SCHEMAS)
    print("Self-test passed: holds, direction only, does not hold, safety line, inconclusive; frozen mapping hash matches")


KS = Path("/path/to/testbed/results/hd720-designer-ch-smoke-v1")


def schema_audit(Kdir):
    """Check that the first obs-trace record of every valid run carries the job's schema and map (empty for the true mapping, IDENTITY for no adapter); return the mismatches."""
    import gzip
    S = json.load(open(Kdir / "main" / "jobs.json")); bad = []
    for j in S["jobs"]:
        key = j["cond"].split("__")[2]; want = ("", "") if key == "CLEAN" else (key.split("-")[0], "IDENTITY" if key.endswith("-NONE") else "JSON")
        fs = list((Kdir / "main" / j["cond"]).glob("obs_*.jsonl.gz"))
        if not fs: continue
        with gzip.open(fs[0], "rt") as f: first = json.loads(f.readline())
        if (first.get("schema", ""), first.get("map", "")) != want: bad.append((j["cond"], first.get("schema"), first.get("map"), want))
    return bad


def smoke():
    AL.prepare(KS); C = json.load(open(KS / "contents.json")); layout, ly = C["layout"], C["label_y"]; M = maps(); J = []
    for m in ("NONE", "LLM"):
        env = dict(BASE_ENV, STALENESS_OBS_SCHEMA="test_g", STALENESS_OBS_MAP="IDENTITY" if m == "NONE" else json.dumps(M["test_g"][m], separators=(",", ":")))
        J.append({"cond": f"hd_c2__{CONTENT}__test_g-{m}__r1", "arm": ARM, "profile": str(H.P / "hd_c2.profile"), "rep": 1, "video_id": CONTENT,
                  "queue": H.queue_of("hd_c2"), "source": H.source_of(CONTENT, layout), "env": env})
    (KS / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID + "-smoke", KS / "main", J, ROOT / "logs/hd720_designer_smoke_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (KS / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("smoke jobs:", len(J))


def smoke_gate():
    runs, bad = AL.collect(KS, set()); sa = schema_audit(KS)
    ok = len(runs) == 2 and all(r.get("valid") for r in runs) and not bad and not sa
    print("smoke test", "Pass" if ok else "not passed", [(r["job"], r.get("valid"), r.get("invalid_reasons"), r.get("vmaf")) for r in runs], "hash anomaly", bad, "mode mismatch", sa)
    sys.exit(0 if ok else 1)


def judge():
    runs, bad = AL.collect(K, set())
    if not AL.audit_ok(K, ID, runs, bad): return
    sa = schema_audit(K)
    if sa:
        subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, f"schema check failed {len(sa)} times (foreign schema or mapping not in effect), no conclusion recorded: {sa[:5]}"], check=True); return
    clean, V = stats(runs); v, m = decide(clean, V)
    key = lambda r: r["job"].split("__")[2].split("-")[-1]
    agg = lambda rs, f: (lambda xs: sum(xs) / len(xs) if xs else None)([r[f] for r in rs if r.get("valid") and r.get(f) is not None])
    ba = {k: {f: agg([r for r in runs if key(r) == k], f) for f in ("vmaf", "file_freeze_per_min", "loss_rate", "delay_score", "envelope_rewrite_frac")} for k in ["CLEAN"] + METHODS}
    nv = {k: sum(1 for r in runs if r.get("valid") and key(r) == k) for k in ["CLEAN"] + METHODS}
    res = {"verdict": v, **m, "by_interface": ba, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad, "invalid_runs": {r["job"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_designer_ch_v1"; AL.export(K, local, runs, res)
    r2 = lambda x: None if x is None else round(x, 2)
    basis = (f"Primary endpoint D_A (designer mapping minus best non-LLM mapping {m.get('best_nonllm')}, deployed system C-H with the 5 kb/s floor and probing envelope v6, {m.get('n_cells')} cells equally weighted) {r2(m.get('delta'))} VMAF, 90% interval {[r2(x) for x in m.get('ci90', [])]}; safety line: cells where the LLM is more than 10 points below the true mapping {m.get('severe') or 'none'}. Report only: average VMAF per mapping {json.dumps({k: r2(x) for k, x in m.get('mean_vmaf', {}).items()}, ensure_ascii=False)}; average deviation from the true mapping {json.dumps({k: r2(x) for k, x in m.get('mean_abs_dev_from_clean', {}).items()}, ensure_ascii=False)}; LLM minus CLEAN {r2(m.get('llm_minus_clean'))}; per-mapping freezes, packet loss, delay score and probing envelope rewrite fraction {json.dumps({k: {f: r2(x[f]) for f in x} for k, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m.get(k) for k in ("delta", "ci90", "best_nonllm", "severe", "mean_vmaf", "mean_abs_dev_from_clean", "llm_minus_clean")}, ensure_ascii=False), "--artifact", str(local / "result_v1.json"))
    if v in ("holds", "direction only", "does not hold"):
        ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (D_A lower bound greater than 0 and not less than 1.5 VMAF, safety line 10 points)." + basis, "--basis", basis,
           "--limitations", "Single sequence (Johnny), four conditions, 1 run per cell per mapping; the foreign schema is the synthetic schema plus the rt_getstats (getStats naming), with mappings taken from the frozen maps.json; the shadow GCC of probing envelope v6 collects native packet reports; single-machine testbed; run script v25.",
           "--next", "")
    else: ex("note", "--id", ID, f"Judged as \"{v}\", no registered conclusion. {basis}")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest, "smoke": smoke, "smoke-gate": smoke_gate}[sys.argv[1]]()
