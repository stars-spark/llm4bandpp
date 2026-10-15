#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch script of hd720-designer-tel-v2, a telemetry-only row of Table IV: the designer in the telemetry-only configuration on new cellular windows hd_t1 to hd_t4 with FourPeople.
Main endpoint: LLM minus the best non-LLM adapter in VMAF over 20 cells; a call broken by the adapter counts as VMAF 0 and tool faults drop the cell; holds if the 90%
lower bound is above 0 and the difference is at least 1.5 VMAF, with no cell 10 VMAF below the true mapping.
Confirms hd720-designer-tel-v1 on new conditions and a new sequence, with the break-as-zero rule of its post hoc revision fixed before the runs; downstream (arm_ch_schema_tel,
run script v27), mappings and checks come from hd720_designer_tel_v1.py. Usage: hd720_designer_tel_v2.py jobs | smoke | smoke-gate | judge | selftest
"""
import json, random, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
import hd720_designer_tel_v1 as TEL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-designer-tel-v2"); KS = Path("/path/to/testbed/results/hd720-designer-tel-v2-smoke"); ID = "hd720-designer-tel-v2"
LOCAL = ROOT / "experiments/results/hd720_designer_tel_v2"
RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v27.sh"; ARM = TEL.ARM
PT = D_ / "profiles/hd720_real8"; PROV = json.load(open(PT / "provenance.json"))["profiles"]
CONDS = ["hd_t1", "hd_t2", "hd_t3", "hd_t4"]; CONTENT = "fourpeople"
SCHEMAS = TEL.SCHEMAS; METHODS = TEL.METHODS; NONLLM = TEL.NONLLM; BASE_ENV = dict(TEL.BASE_ENV)
MIN_D = 1.5; SAFE = 10.0; SEED = 20261007; B = 10000
BREAK = ("run script validity check did not pass or has no result", "VMAF not computed")


def job(cond, key, rep, env, layout):
    return {"cond": f"{cond}__{CONTENT}__{key}__r{rep}", "arm": ARM, "profile": str(PT / f"{cond}.profile"), "rep": rep, "video_id": CONTENT,
            "queue": PROV[cond]["queue_packets"], "source": H.source_of(CONTENT, layout), "env": env}


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
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_designer_tel_v2_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def is_break(r):
    rs = r.get("invalid_reasons") or []
    return (not r.get("valid")) and bool(rs) and all(any(x.startswith(b) for b in BREAK) for x in rs)


def stats(runs):
    """Return clean[cond], V[(method, schema, cond)] with call breaks as 0, break counts and completed-call VMAF per method, and tool-fault runs."""
    clean, V, brk, done, tool = {}, {}, {m: 0 for m in METHODS}, {m: [] for m in METHODS}, []
    for r in runs:
        key = r["job"].split("__")[2]; cond = r["cond"]
        if key == "CLEAN":
            if r.get("valid") and r.get("vmaf") is not None: clean.setdefault(cond, []).append(r["vmaf"])
            continue
        s, m = key.split("-")
        if r.get("valid") and r.get("vmaf") is not None: V[(m, s, cond)] = r["vmaf"]; done[m].append(r["vmaf"])
        elif is_break(r): V[(m, s, cond)] = 0.0; brk[m] += 1
        else: tool.append(r["job"])
    return {c: sum(x) / len(x) for c, x in clean.items()}, V, brk, done, tool


def decide(clean, V):
    cells = [(s, c) for s in SCHEMAS for c in CONDS if all((m, s, c) in V for m in METHODS)]
    if len(cells) < 10: return "inconclusive", {"n_cells": len(cells)}
    best = max(NONLLM, key=lambda m: sum(V[(m, s, c)] for s, c in cells) / len(cells))
    d = [V[("LLM", s, c)] - V[(best, s, c)] for s, c in cells]; D = sum(d) / len(d)
    rng = random.Random(SEED); bs = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(B)); ci = [bs[int(0.05 * B)], bs[int(0.95 * B) - 1]]
    severe = [f"{s}|{c}" for s, c in cells if c in clean and V[("LLM", s, c)] < clean[c] - SAFE]
    v = "does not hold" if (D <= 0 or severe) else ("holds" if ci[0] > 0 and D >= MIN_D else "direction only")
    mean = {m: sum(V[(m, s, c)] for s, c in cells) / len(cells) for m in METHODS}
    return v, {"n_cells": len(cells), "best_nonllm": best, "delta": D, "ci90": ci, "severe": severe, "cell_diff": {f"{s}|{c}": x for (s, c), x in zip(cells, d)},
               "mean_vmaf_breaks0": mean, "clean_by_cond": clean, "llm_minus_clean": sum(V[("LLM", s, c)] - clean[c] for s, c in cells if c in clean) / len(cells)}


def selftest():
    clean = {c: 80.0 for c in CONDS}
    def mk(llm, other):
        return {(m, s, c): (llm if m == "LLM" else other) for m in METHODS for s in SCHEMAS for c in CONDS}
    assert decide(clean, mk(80.0, 75.0))[0] == "holds"
    assert decide(clean, mk(80.0, 79.5))[0] == "direction only"
    assert decide(clean, mk(75.0, 80.0))[0] == "does not hold"
    V = mk(80.0, 70.0); V[("LLM", "test_g", "hd_t1")] = 60.0; assert decide(clean, V)[0] == "does not hold"
    assert decide(clean, {k: v for k, v in mk(80.0, 70.0).items() if k[1] in ("test_g",)})[0] == "inconclusive"
    base = {"cond": "hd_t1", "vmaf": None}
    runs = [dict(base, job="hd_t1__fourpeople__test_g-NAME__r1", valid=False, invalid_reasons=["run script validity check did not pass or has no result"]),
            dict(base, job="hd_t1__fourpeople__test_g-DIST__r1", valid=False, invalid_reasons=["VMAF not computed"]),
            dict(base, job="hd_t1__fourpeople__test_g-NONE__r1", valid=False, invalid_reasons=["Missing run directory"]),
            dict(base, job="hd_t1__fourpeople__test_g-LLM__r1", valid=True, vmaf=81.0),
            dict(base, job="hd_t1__fourpeople__CLEAN__r1", valid=False, invalid_reasons=["run script validity check did not pass or has no result"])]
    c, V, brk, done, tool = stats(runs)
    assert V[("NAME", "test_g", "hd_t1")] == 0.0 and V[("DIST", "test_g", "hd_t1")] == 0.0 and ("NONE", "test_g", "hd_t1") not in V and tool == ["hd_t1__fourpeople__test_g-NONE__r1"]
    assert brk["NAME"] == 1 and brk["DIST"] == 1 and c == {} and done["LLM"] == [81.0]
    M = TEL.maps(); assert set(M) >= set(SCHEMAS) and all(set(M[s]) >= {"LLM", "DIST", "NAME"} for s in SCHEMAS)
    assert all((PT / f"{c}.profile").is_file() for c in CONDS)
    print("Self-test passed: verdicts, break-as-zero rule, tool-fault drop, frozen map hash, profiles hd_t1 to hd_t4 present")


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
    clean, V, brk, done, tool = stats(runs); v, m = decide(clean, V)
    key = lambda r: r["job"].split("__")[2].split("-")[-1]
    agg = lambda rs, f: (lambda xs: sum(xs) / len(xs) if xs else None)([r[f] for r in rs if r.get("valid") and r.get(f) is not None])
    ba = {k: {f: agg([r for r in runs if key(r) == k], f) for f in ("vmaf", "file_freeze_per_min", "loss_rate", "delay_score", "envelope_rewrite_frac")} for k in ["CLEAN"] + METHODS}
    nv = {k: sum(1 for r in runs if r.get("valid") and key(r) == k) for k in ["CLEAN"] + METHODS}
    res = {"verdict": v, **m, "breaks": brk, "tool_invalid": tool, "by_interface_completed": ba, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad,
           "invalid_runs": {r["job"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    AL.export(K, LOCAL, runs, res)
    r2 = lambda x: None if x is None else round(x, 2)
    basis = (f"Primary endpoint D_A (designer mapping minus best non-LLM mapping {m.get('best_nonllm')}, broken calls counted as 0, telemetry-only configuration C-H with the 5 kb/s floor and probing envelope v4, FourPeople, hd_t1 to hd_t4, {m.get('n_cells')} cells equally weighted) {r2(m.get('delta'))} VMAF, 90% interval {[r2(x) for x in m.get('ci90', [])]}; safety line: cells where the LLM is more than 10 points below the true mapping {m.get('severe') or 'none'}. Report only: broken calls {json.dumps(brk, ensure_ascii=False)} (20 calls per mapping); excluded for tool reasons {len(tool)}; average VMAF (broken calls counted as 0) {json.dumps({k: r2(x) for k, x in m.get('mean_vmaf_breaks0', {}).items()}, ensure_ascii=False)}; LLM minus CLEAN {r2(m.get('llm_minus_clean'))}; per-mapping VMAF, freezes, packet loss, delay score and probing envelope rewrite fraction of completed calls {json.dumps({k: {f: r2(x[f]) for f in x} for k, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m.get(k) for k in ("delta", "ci90", "best_nonllm", "severe", "mean_vmaf_breaks0", "llm_minus_clean")} | {"breaks": brk}, ensure_ascii=False),
       "--artifact", str(LOCAL / "result_v1.json"))
    if v in ("holds", "direction only", "does not hold"):
        ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (broken calls counted as 0, as written down before the run; D_A lower bound greater than 0 and not less than 1.5 VMAF, safety line 10 points)." + basis, "--basis", basis,
           "--limitations", "Tests only the telemetry-only configuration (probing envelope v4, no shadow GCC); the five schemas and frozen mappings are those of v1; the conditions (four cellular windows) and the sequence (FourPeople) are new; 1 run per cell per mapping; single-machine testbed; run script v27.",
           "--next", "")
    else: ex("note", "--id", ID, f"Judged as \"{v}\", no registered conclusion. {basis}")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest, "smoke": smoke, "smoke-gate": smoke_gate}[sys.argv[1]]()
