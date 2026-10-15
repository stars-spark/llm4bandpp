#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stronger non-LLM baseline for interface adaptation on the synthetic schema (registered experiment obsschema-strong-baseline-v1).
The unit-aware name matcher was designed from the dev schemas only and frozen; the copy in scripts/arb/unitname_v1/ (unit_name_match.py, hungarian.py) is hashed into matcher_sha256.txt.
Usage: obsschema_strong_baseline_v1.py transforms | remote | judge [--selftest]
transforms maps the 72 test groups with the frozen matcher (32 groups from the obsschema_v1 evidence, 40 from the obsschema_rt evidence);
remote uploads the mappings, runs the original evaluation code on the remote host and fetches the results;
judge compares with the registered R1-distilled 32B readings and records the verdict.
"""
import hashlib, json, random, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; ID = "obsschema-strong-baseline-v1"
OLD = ROOT / "experiments/results/obsschema_v1"; NEW = ROOT / "experiments/results/obsschema_rt_openreason_v1"; OUT = ROOT / "experiments/results/obsschema_strong_baseline_v1"
R_OLD = "/path/to/server/outputs/obsschema_v1"; R_NEW = "/path/to/server/outputs/obsschema_rt_v1"; SSH = ["ssh", "-o", "ConnectTimeout=20", "-o", "BatchMode=yes"]
M = "UNITNAME"; DELTA = 0.25


def transforms():
    sys.path.insert(0, str(ROOT / "scripts/arb/unitname_v1")); import unit_name_match as U
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "matcher_sha256.txt").write_text(hashlib.sha256((ROOT / "scripts/arb/unitname_v1/unit_name_match.py").read_bytes()).hexdigest())
    for tag, d, phase in (("old", OLD, "test"), ("new", NEW, "test_rt")):
        G = json.load(open(d / "groups.json"))["groups"]; E = json.load(open(d / "evidence.json")); T = {}
        for g in G:
            if g["phase"] != phase: continue
            e = E["groups"][str(g["id"])]
            try: T[str(g["id"])] = {M: U.match(e["names"], e["stats"], E["ref"])}
            except Exception as ex: print("matcher raised an exception; group recorded as not adapted", tag, g["id"], ex); T[str(g["id"])] = {}
        (OUT / f"transforms_{tag}.json").write_text(json.dumps(T, ensure_ascii=False)); print(tag, "number of groups", len(T))


def remote():
    def run(cmd): return subprocess.run(SSH + ["gpu-server-1", cmd], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=7200)
    subprocess.run(["scp", "-q", str(OUT / "transforms_old.json"), f"gpu-server-1:{R_OLD}/transforms_test_unitname.json"], check=True)
    subprocess.run(["scp", "-q", str(OUT / "transforms_new.json"), f"gpu-server-1:{R_NEW}/transforms_unitname.json"], check=True)
    py = "python3"
    print(run(f"cd /path/to/server/work && {py} obsschema_v1.py eval {R_OLD}/transforms_test_unitname.json test _unitname > {R_OLD}/eval_unitname.log 2>&1; echo rc=$?").stdout.strip())
    print(run(f"cd /path/to/server/work && {py} obsschema_rt_offline_v1.py eval {R_NEW}/transforms_unitname.json unitname > {R_NEW}/eval_unitname.log 2>&1; echo rc=$?").stdout.strip())
    subprocess.run(["scp", "-q", f"gpu-server-1:{R_OLD}/eval_test_unitname.json", str(OUT / "eval_old_unitname.json")], check=True)
    subprocess.run(["scp", "-q", f"gpu-server-1:{R_NEW}/eval_unitname.json", str(OUT / "eval_new_unitname.json")], check=True)


def med(res, m):
    xs = [r.get(m, np.nan) for r in res.values()]
    return float(np.nanmedian(xs)) if any(x == x for x in xs) else float("nan")


def rows():
    out = []
    for tag, d, llm_f, ub_f, phase in (("old", OLD, OLD / "eval_test_r1_32b.json", OUT / "eval_old_unitname.json", "test"),
                                       ("new", NEW, NEW / "eval_rt_r1_32b.json", OUT / "eval_new_unitname.json", "test_rt")):
        G = {str(g["id"]): g for g in json.load(open(d / "groups.json"))["groups"] if g["phase"] == phase}
        L = json.load(open(llm_f))["results"]; B = json.load(open(ub_f))["results"]
        ds = json.load(open(OLD / "eval_test.json"))["results"] if tag == "old" else None
        for gid, g in G.items():
            ml, mb = med(L[gid], "LLM"), med(B[gid], M)
            r = {"set": tag, "id": gid, "cs": f"{tag}|{g['scen']}|{g['draw']}", "schema": g["schema"], "med_LLM": ml, "med_UB": mb,
                 "LLM": int(ml <= 1.2), "UB": int(mb <= 1.2), "OBF": int(med(L[gid], "LLM_OBF") <= 1.2), "DIST": int(med(B[gid], "DIST") <= 1.2), "NAME": int(med(B[gid], "NAME") <= 1.2)}
            if ds is not None: r["DEEPSEEK"] = int(med(ds[gid], "LLM") <= 1.2)
            out.append(r)
    return out


def judge(R, seed=20261009, B=5000):
    n = len(R); D = sum(r["LLM"] - r["UB"] for r in R) / n; cs = sorted({r["cs"] for r in R}); rng = random.Random(seed); boots = []
    for _ in range(B):
        pick = [rng.choice(cs) for _ in cs]; sel = [r for c in pick for r in R if r["cs"] == c]; boots.append(sum(r["LLM"] - r["UB"] for r in sel) / len(sel))
    lo, hi = float(np.percentile(boots, 5)), float(np.percentile(boots, 95))
    sev = {"LLM": sum(not (r["med_LLM"] <= 2) for r in R), "UB": sum(not (r["med_UB"] <= 2) for r in R)}; safe = sev["LLM"] <= sev["UB"]
    v = "does not hold" if (not D > 0 or not safe) else ("holds" if lo > 0 and D >= DELTA else "direction only")
    return v, {"n": n, "delta": D, "ci90": [lo, hi], "severe": sev, "safe": safe, "success": {k: sum(r.get(k, 0) for r in R) for k in ("LLM", "UB", "OBF", "DIST", "NAME", "DEEPSEEK")},
               "per_schema": {s: {"LLM": sum(r["LLM"] for r in R if r["schema"] == s), "UB": sum(r["UB"] for r in R if r["schema"] == s)} for s in sorted({r["schema"] for r in R})}}


def selftest():
    def mk(pl, pb):
        rr = random.Random(3); out = []
        for i in range(72):
            a, b = int(rr.random() < pl), int(rr.random() < pb)
            out.append({"cs": f"c{i % 16}", "schema": f"s{i % 9}", "LLM": a, "UB": b, "OBF": 0, "DIST": 0, "NAME": 0, "med_LLM": 1.0 if a else 1.5, "med_UB": 1.0 if b else 1.5})
        return out
    assert judge(mk(0.85, 0.3))[0] == "holds"
    assert judge(mk(0.5, 0.7))[0] == "does not hold"
    R = mk(0.85, 0.3); R[0]["med_LLM"] = R[1]["med_LLM"] = 9.0
    for r in R: r["med_UB"] = 1.0 if r["med_UB"] > 2 else r["med_UB"]
    assert judge(R)[0] == "does not hold"
    print("Verdict self-test passed (holds, does not hold, safety line)")


def main():
    R = rows(); v, m = judge(R); (OUT / "judge.json").write_text(json.dumps({"verdict": v, **m, "rows": R}, ensure_ascii=False, indent=1))
    s = m["success"]
    basis = (f"72 held-out groups: R1 distilled 32B success {s['LLM']}, unit-aware name matching {s['UB']}; Δ (by group proportion) {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; groups with median ratio above 2 LLM {m['severe']['LLM']}, matcher {m['severe']['UB']}. Report only: by schema {json.dumps(m['per_schema'], ensure_ascii=False)}; shuffled field names {s['OBF']}, distribution matching {s['DIST']}, literal name matching {s['NAME']}; DeepSeek on the old 32 groups {s['DEEPSEEK']}. Matcher source hash {(OUT / 'matcher_sha256.txt').read_text()[:12]}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m[k] for k in ("delta", "ci90", "severe", "success", "per_schema")}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template)." + basis, "--basis", basis,
       "--limitations", "The matcher was designed blind by us and represents only one plausible rule-based matcher; evaluation is offline step-by-step replay, not closed loop; the LLM readings use the registered R1-distilled 32B.", "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "transforms": transforms()
    elif c == "remote": remote()
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
