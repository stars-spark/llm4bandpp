#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-designer-tel-fid-v1: interface fidelity of the designer in the telemetry-only configuration (arm_ch_schema_tel) on new windows hd_t5, hd_t7, hd_t8 and hd_c3.
Criterion as obsschema-closedloop-v2: deviation |U(method) - U(true mapping)| in utility over 20 cells; delta = best statistical adapter's mean deviation minus the LLM's, condition-block bootstrap 90% interval; holds if the lower bound is above 0 and delta is at least 3; a call break counts as utility 0.
Usage: hd720_designer_tel_fid_v1.py jobs | judge | selftest
"""
import json, random, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
import hd720_designer_tel_v1 as TEL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-designer-tel-fid-v1"); KS = Path("/path/to/testbed/results/hd720-designer-tel-fid-v1-smoke"); ID = "hd720-designer-tel-fid-v1"
LOCAL = ROOT / "experiments/results/hd720_designer_tel_fid_v1"
RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v27.sh"; ARM = TEL.ARM
PT = D_ / "profiles/hd720_real8"; PROV = json.load(open(PT / "provenance.json"))["profiles"]
CONDS = ["hd_t5", "hd_t7", "hd_t8", "hd_c3"]; CONTENT = "johnny"
SCHEMAS = TEL.SCHEMAS; METHODS = TEL.METHODS; NONLLM = TEL.NONLLM; BASE_ENV = dict(TEL.BASE_ENV)
MIN_D = 3.0; SAFE = 10.0; SEED = 20261007; B = 5000
BREAK = ("run script validity check did not pass or has no result", "VMAF not computed")


def job(cond, key, rep, env, layout):
    prof, q = (PT / f"{cond}.profile", PROV[cond]["queue_packets"]) if cond in PROV else (H.P / f"{cond}.profile", H.queue_of(cond))
    return {"cond": f"{cond}__{CONTENT}__{key}__r{rep}", "arm": ARM, "profile": str(prof), "rep": rep, "video_id": CONTENT,
            "queue": q, "source": H.source_of(CONTENT, layout), "env": env}


def env_of(k, M):
    env = dict(BASE_ENV)
    if k.startswith("CLEAN"): return env, "CLEAN", int(k.split("#")[1])
    s, m = k.split("-"); mp = M[s][m] if m != "NONE" else None
    env.update(STALENESS_OBS_SCHEMA=s, STALENESS_OBS_MAP="IDENTITY" if mp is None else json.dumps(mp, separators=(",", ":")))
    return env, k, 1


def jobs():
    AL.prepare(K); C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; M = TEL.maps(); J = []
    assert CONTENT in C["main_contents"]
    for cond in CONDS:
        keys = ["CLEAN#1", "CLEAN#2"] + [f"{s}-{m}" for s in SCHEMAS for m in METHODS]; random.Random(f"{ID}/{cond}").shuffle(keys)
        for k in keys:
            env, key, rep = env_of(k, M); J.append(job(cond, key, rep, env, layout))
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_designer_tel_fid_v1_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def is_break(r):
    rs = r.get("invalid_reasons") or []
    return (not r.get("valid")) and bool(rs) and all(any(x.startswith(b) for b in BREAK) for x in rs)


def stats(runs, f="utility"):
    """Return clean[cond] (mean of valid correct-interface runs), V[(method, schema, cond)] with call breaks as 0, break counts per method and tool-fault runs."""
    clean, V, brk, tool = {}, {}, {m: 0 for m in METHODS}, []
    for r in runs:
        key = r["job"].split("__")[2]; cond = r["cond"]
        if key == "CLEAN":
            if r.get("valid") and r.get(f) is not None: clean.setdefault(cond, []).append(r[f])
            continue
        s, m = key.split("-")
        if r.get("valid") and r.get(f) is not None: V[(m, s, cond)] = r[f]
        elif is_break(r): V[(m, s, cond)] = 0.0; brk[m] += 1
        else: tool.append(r["job"])
    return {c: sum(x) / len(x) for c, x in clean.items()}, V, brk, tool


def decide(clean, V):
    """Apply the obsschema-closedloop-v2 fidelity criterion with condition-block bootstrap and return verdict and metrics."""
    cells = [(s, c) for s in SCHEMAS for c in CONDS if c in clean and all((m, s, c) in V for m in METHODS)]
    conds = sorted({c for _, c in cells})
    if len(cells) < 10: return "inconclusive", {"n_cells": len(cells)}
    dev = lambda m, sel: [abs(V[(m, s, c)] - clean[c]) for s, c in cells if c in sel]
    mean = lambda xs: sum(xs) / len(xs)
    md = {m: mean(dev(m, conds)) for m in METHODS}
    best = min(("DIST", "NAME"), key=lambda m: md[m])
    D = md[best] - md["LLM"]
    rng = random.Random(SEED); bs = []
    for _ in range(B):
        sel = [rng.choice(conds) for _ in conds]; a = [x for c in sel for x in dev("LLM", [c])]; b = [x for c in sel for x in dev(best, [c])]
        bs.append(mean(b) - mean(a))
    bs.sort(); ci = [bs[int(0.05 * B)], bs[int(0.95 * B) - 1]]
    severe = [f"{s}|{c}" for s, c in cells if V[("LLM", s, c)] < clean[c] - SAFE]
    v = "does not hold" if (D <= 0 or severe) else ("holds" if ci[0] > 0 and D >= MIN_D else "direction only")
    return v, {"n_cells": len(cells), "best_stat": best, "delta": D, "ci90": ci, "severe": severe, "mean_dev": md, "clean_by_cond": clean}


def selftest():
    clean = {c: 80.0 for c in CONDS}
    def mk(llm, other):
        return {(m, s, c): (llm if m == "LLM" else other) for m in METHODS for s in SCHEMAS for c in CONDS}
    assert decide(clean, mk(80.0, 70.0))[0] == "holds"
    assert decide(clean, mk(79.0, 77.5))[0] == "direction only"
    assert decide(clean, mk(75.0, 79.0))[0] == "does not hold"
    V = mk(80.0, 60.0); V[("LLM", "test_g", CONDS[0])] = 65.0; assert decide(clean, V)[0] == "does not hold"
    V = mk(80.0, 60.0); V[("LLM", "test_g", CONDS[0])] = 95.0; assert decide(clean, V)[0] == "holds"
    assert decide(clean, {k: v for k, v in mk(80.0, 70.0).items() if k[1] == "test_g"})[0] == "inconclusive"
    v, m = decide(clean, mk(80.0, 70.0)); assert m["best_stat"] in ("DIST", "NAME") and abs(m["delta"] - 10.0) < 1e-9
    base = {"cond": CONDS[0], "vmaf": None, "utility": None}
    runs = [dict(base, job=f"{CONDS[0]}__johnny__test_g-NAME__r1", valid=False, invalid_reasons=["run script validity check did not pass or has no result"]),
            dict(base, job=f"{CONDS[0]}__johnny__test_g-NONE__r1", valid=False, invalid_reasons=["Missing run directory"]),
            dict(base, job=f"{CONDS[0]}__johnny__test_g-LLM__r1", valid=True, utility=81.0),
            dict(base, job=f"{CONDS[0]}__johnny__CLEAN__r1", valid=True, utility=80.0)]
    c, V, brk, tool = stats(runs)
    assert V[("NAME", "test_g", CONDS[0])] == 0.0 and ("NONE", "test_g", CONDS[0]) not in V and tool == [f"{CONDS[0]}__johnny__test_g-NONE__r1"] and c == {CONDS[0]: 80.0} and brk["NAME"] == 1
    M = TEL.maps(); assert set(M) >= set(SCHEMAS) and all(set(M[s]) >= {"LLM", "DIST", "NAME"} for s in SCHEMAS)
    assert all((PT / f"{c}.profile").is_file() if c in PROV else (H.P / f"{c}.profile").is_file() for c in CONDS)
    print("Self-test passed: verdicts, break-as-zero rule, tool-fault drop, frozen map hash, four profiles present")


def smoke():
    AL.prepare(KS); C = json.load(open(KS / "contents.json")); layout, ly = C["layout"], C["label_y"]; M = TEL.maps()
    J = [job("hd_t1", "CLEAN", 1, dict(BASE_ENV), layout), job("hd_t1", "test_g-LLM", 1, env_of("test_g-LLM", M)[0], layout)]
    (KS / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID + "-smoke", KS / "main", J, ROOT / "logs/hd720_designer_tel_v2_smoke_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (KS / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("smoke jobs:", len(J))


def smoke_gate():
    runs, bad = TEL.collect_tel(KS); sa = TEL.schema_audit(KS)
    ok = len(runs) == 2 and all(r.get("valid") for r in runs) and not bad and not sa
    print("smoke test", "Pass" if ok else "not passed", [(r["job"], r.get("valid"), r.get("invalid_reasons"), r.get("vmaf")) for r in runs], "hash anomaly", bad, "mode mismatch", sa)
    sys.exit(0 if ok else 1)


def judge():
    runs, bad = TEL.collect_tel(K)
    if not AL.audit_ok(K, ID, runs, bad): return
    sa = TEL.schema_audit(K)
    if sa:
        subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, f"schema check failed {len(sa)} times (foreign schema or mapping not in effect), no conclusion recorded: {sa[:5]}"], check=True); return
    clean, V, brk, tool = stats(runs); v, m = decide(clean, V)
    cv, Vv, _, _ = stats(runs, "vmaf"); _, mv = decide(cv, Vv)
    key = lambda r: r["job"].split("__")[2].split("-")[-1]
    nv = {k: sum(1 for r in runs if r.get("valid") and key(r) == k) for k in ["CLEAN"] + METHODS}
    res = {"verdict": v, **m, "breaks": brk, "tool_invalid": tool, "vmaf_report": {k: mv.get(k) for k in ("mean_dev", "delta", "ci90")}, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad,
           "invalid_runs": {r["job"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    AL.export(K, LOCAL, runs, res)
    r2 = lambda x: None if x is None else round(x, 2)
    basis = (f"Primary endpoint (same as obsschema-closedloop-v2): mean utility deviation from the true mapping {json.dumps({k: r2(x) for k, x in m.get('mean_dev', {}).items()}, ensure_ascii=False)}; Δ ({m.get('best_stat')} minus LLM) {r2(m.get('delta'))}, 90% interval {[r2(x) for x in m.get('ci90', [])]}; safety line (cells where the LLM is more than 10 utility points below the true mapping) {m.get('severe') or 'none'}; downstream is the deployed system with read-only telemetry (C-H with the 5 kb/s floor and probing envelope v4), Johnny, hd_t5, hd_t7, hd_t8, hd_c3, {m.get('n_cells')} cells. Report only: broken calls {json.dumps(brk, ensure_ascii=False)} (20 calls per mapping); excluded for tool reasons {len(tool)}; quality deviation {json.dumps({k: r2(x) for k, x in (mv.get('mean_dev') or {}).items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m.get(k) for k in ("delta", "ci90", "best_stat", "severe", "mean_dev")} | {"breaks": brk}, ensure_ascii=False), "--artifact", str(LOCAL / "result_v1.json"))
    if v in ("holds", "direction only", "does not hold"):
        ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (verbatim the same as obsschema-closedloop-v2: Δ lower bound above 0 and Δ at least 3, safety line 10 utility points; broken calls count as 0, fixed before the run)." + basis, "--basis", basis,
           "--limitations", "Tests only the telemetry-only configuration (probing envelope v4, no shadow GCC); the criterion was chosen after seeing hd720-designer-tel-v2 (reusing the registered fidelity criterion, new data); the five schemas and frozen mappings are those of the first two batches; 1 run per cell per mapping; single-machine testbed; run script v27.",
           "--next", "")
    else: ex("note", "--id", ID, f"Judged as \"{v}\", no registered conclusion. {basis}")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest}[sys.argv[1]]()
