#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Two-step LLM matching baseline (registered experiment llm-twostep-match-v1).
Step 1 reuses the cached generic matches of llm_schema_match_v1 (deepseek-flash, temperature 0, three field orders) without new calls.
Step 2 makes one call per source and field order: it lists the matched (feature, field) pairs and asks only for diff (cumulative counter) and scale, worded as item (a) of the designer prompt.
Unmatched features stay missing; a step-2 parse failure makes the whole source and order missing; an unanswered pair makes that feature missing.
Primary endpoint on the 12 client stacks of realtel-scale-v1: delta = BA(designer) - BA(two-step), source-block bootstrap, 90% interval; holds if the lower bound > 0 and delta >= 0.15.
Report only: delta on the 7 specifications and the correct share on the 42 end-to-end cells of realtel-e2e-v1.
Usage: llm_twostep_match_v1.py hash | llm | judge [--selftest]
"""
import hashlib, json, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart")); sys.path.insert(0, str(ROOT / "scripts/realtel_e2e"))
import realtel_adapter_v1 as M  # noqa: E402
import llm_schema_match_v1 as LS  # noqa: E402
OUT = ROOT / "experiments/results/llm_twostep_match_v1"; ID = "llm-twostep-match-v1"

STEP2 = """A field of a client's telemetry source has been matched to each feature below of a bandwidth estimator's interface. The estimator reads every feature over 60 ms and 600 ms windows. For each matched pair, say how to turn the field into the feature.

Telemetry source: {header}

Matched pairs:
{pairs}

For each pair give "diff" (true if the field is a cumulative counter, so the difference of two consecutive readings is used) and "scale" (feature value = field value, or its difference, times scale). Differences in the length of the reporting interval are acceptable. Answer as JSON in a single ```json code block: {{"pairs": [{{"pair": 0, "diff": true or false, "scale": a}}, ... one entry per pair]}}. Keep your reasoning brief."""


def tmpl_hash(): return hashlib.sha256((STEP2 + json.dumps(M.FEAT)).encode()).hexdigest()


def pairs_of(src, k, mp1):
    """List the (feature, field index) pairs matched in step 1; field indices follow the k-th field order."""
    return [(t, mp1[t]["source"]) for t in range(15) if mp1 and mp1[t] is not None]


def build_prompt(src, k, P):
    f, _ = M.present(src, k)
    pairs = "\n".join(f"pair {p}: feature \"{M.FEAT[t]}\" <- field {f[j][0]} | {f[j][1]} | {f[j][2]}" for p, (t, j) in enumerate(P))
    return STEP2.format(header=src["header"], pairs=pairs)


def parse2(txt, P):
    """Parse the step-2 JSON into a per-feature mapping; return (mapping, number of unanswered pairs)."""
    m = re.findall(r"```json\s*(.*?)```", txt, re.S); body = re.sub(r"//[^\n]*", "", m[-1])
    body = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\w.])", lambda q: repr(float(q.group(1)) / float(q.group(2))), body)
    ans = {int(e["pair"]): e for e in json.loads(body)["pairs"]}; mp = [None] * 15; miss = 0
    for p, (t, j) in enumerate(P):
        e = ans.get(p)
        if e is None or not isinstance(e.get("scale"), (int, float)) or isinstance(e.get("diff"), str): miss += 1; continue
        mp[t] = {"source": j, "diff": bool(e["diff"]), "scale": float(e["scale"])}
    return mp, miss


def step1():
    return {(j["set"], j["source"], j["pres"]): (j["mapping"] if j.get("ok") else None) for j in map(json.loads, open(LS.OUT / "llm_generic.jsonl"))}


def cmd_llm():
    import coldstart_rule_v1 as CR
    OUT.mkdir(parents=True, exist_ok=True); h = tmpl_hash(); fz = OUT / "prompt_hash_frozen.txt"
    if fz.exists(): assert fz.read_text().strip() == h, "prompt differs from the frozen version"
    else: fz.write_text(h)
    cache = OUT / "llm_twostep.jsonl"; done = set()
    if cache.exists(): done = {(j["set"], j["source"], j["pres"]) for j in map(json.loads, open(cache)) if j.get("ok") is not None}
    SS = LS.sets(); S1 = step1(); lock = threading.Lock()
    jobs = [(s, n, k) for s, S in SS.items() for n in S for k in range(M.NPRES) if (s, n, k) not in done]; print("to run", len(jobs), flush=True)
    def work(job):
        s, n, k = job; src = SS[s][n]; P = pairs_of(src, k, S1.get(job))
        if not P:
            rec = {"set": s, "source": n, "pres": k, "mapping": [None] * 15, "missing_pairs": 0, "ok": True, "no_call": True}
        else:
            t0 = time.time(); r = CR.ask(build_prompt(src, k, P), 48000); wall = time.time() - t0; txt = r["choices"][0]["message"].get("content") or ""
            try: mp, miss = parse2(txt, P); ok = True
            except Exception: mp, miss, ok = [None] * 15, None, False
            rec = {"set": s, "source": n, "pres": k, "mapping": mp, "missing_pairs": miss, "ok": ok, "n_pairs": len(P), "wall_s": wall, "usage": r.get("usage", {}), "tail": txt[-300:]}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); print(s, n, k, "parsed" if rec["ok"] else "parse failure", flush=True)
    bal = CR.AR.balance(CR.AR.KEY.read_text().strip())
    if not CR.AR.ok_to_send() or bal < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping", bal); sys.exit(2)
    with ThreadPoolExecutor(6) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


def selftest():
    P = [(2, 0), (7, 3)]
    mp, miss = parse2('x\n```json\n{"pairs": [{"pair": 0, "diff": true, "scale": 8}, {"pair": 1, "diff": false, "scale": 1/1000}]}\n```', P)
    assert mp[2] == {"source": 0, "diff": True, "scale": 8.0} and abs(mp[7]["scale"] - 0.001) < 1e-12 and miss == 0 and mp[0] is None
    mp, miss = parse2('```json\n{"pairs": [{"pair": 1, "diff": false, "scale": 1}]}\n```', P); assert mp[2] is None and miss == 1 and mp[7]["scale"] == 1.0
    try: parse2("no json", P); raise AssertionError("Should fail to parse")
    except AssertionError: raise
    except Exception: pass
    SS = LS.sets(); S1 = step1(); n = sorted(SS["scale12"])[0]; src = SS["scale12"][n]; P = pairs_of(src, 1, S1[("scale12", n, 1)])
    p = build_prompt(src, 1, P); assert all(f"pair {i}:" in p for i in range(len(P))) and src["header"] in p
    print("Self-test passed: parsing (score coefficients, missing answers treated as missing, no JSON judged as failure), prompts listed pair by pair; prompt hash", tmpl_hash()[:12])


def e2e(two):
    """Score the two-step, designer and generic-matcher adapters on the 42 end-to-end cells; return the correct share and count per method."""
    import realtel_e2e_v1 as E
    import e2e_valuerule_v1 as VR
    A = E.adapters(); G = VR.generic_adapters()
    T = {e: {k: (None if two.get(s) is None or two[s][k] is None else (M.TEST[s]["fields"][two[s][k]["source"]][0], two[s][k]["diff"], two[s][k]["scale"])) for k in range(15)} for e, s in E.SRC.items()}
    R = {"DEEPSEEK": [], "GENERIC": [], "TWO_STEP": []}
    for d in sorted((E.OUT / "runs").iterdir()):
        if not d.is_dir() or not (d / "OK").exists(): continue
        src = d.name.split("_")[0]; W = E.LOAD[src](d)
        for k in E.FEATS[src]:
            if (src, k) in VR.DROP: continue
            for m, ad in (("DEEPSEEK", A["DEEPSEEK"]), ("GENERIC", G), ("TWO_STEP", T)): R[m].append(int(E.unit_err(W, k, ad[src].get(k))[1]))
    assert len(R["DEEPSEEK"]) == 42, len(R["DEEPSEEK"])
    return {m: sum(v) / len(v) for m, v in R.items()}, {m: sum(v) for m, v in R.items()}


def cmd_judge():
    SS = LS.sets(); L2 = {}
    for j in map(json.loads, open(OUT / "llm_twostep.jsonl")): L2[(j["set"], j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    res = {}
    for s, dpath in (("scale12", LS.SC.OUT / "llm_deepseek.jsonl"), ("spec7", M.OUT / "llm_test_deepseek.jsonl")):
        S = SS[s]; Ld = LS.load_maps(dpath); Lt = {(n, k): L2.get((s, n, k)) for n in S for k in range(M.NPRES)}
        for n in S:
            for k in range(M.NPRES): Ld.setdefault((n, k), None)
        v, m = M.judge(LS.rows(S, Ld), {"TWO_STEP": LS.rows(S, Lt)})
        res[s] = {"verdict": v, "delta": m["delta"], "ci90": m["ci90"], "ba_designer": m["ba_llm"], "ba_twostep": m["ba_base"]["TWO_STEP"], "designer_false_map_rate": m["false_map_rate"]}
    two0 = {n: L2.get(("spec7", n, 0)) for n in SS["spec7"]}; rate, cnt = e2e(two0)
    recs = [json.loads(l) for l in open(OUT / "llm_twostep.jsonl")]
    a, b = res["scale12"], res["spec7"]
    basis = (f"12 real client stacks (3 field orders per stack): designer BA {a['ba_designer']:.3f}, two-step (general matching then ask about units and differencing) {a['ba_twostep']:.3f}; Δ {a['delta']:+.3f}, 90% interval [{a['ci90'][0]:+.3f}, {a['ci90'][1]:+.3f}]. Report only: 7 specifications designer {b['ba_designer']:.3f}, two-step {b['ba_twostep']:.3f}, Δ {b['delta']:+.3f} [{b['ci90'][0]:+.3f}, {b['ci90'][1]:+.3f}]; end-to-end 42 cells judged correct designer {cnt['DEEPSEEK']}, general matcher {cnt['GENERIC']}, two-step {cnt['TWO_STEP']}; second-step calls {sum(1 for r in recs if not r.get('no_call'))}, parse failures {sum(1 for r in recs if not r['ok'])}, missing correct answers {sum(r.get('missing_pairs') or 0 for r in recs)}.")
    print(a["verdict"], basis)
    json.dump({"res": res, "e2e_rate": rate, "e2e_count": cnt}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    ex = lambda *x: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *x], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"scale12": a, "spec7": b, "e2e_count": cnt}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"), "--artifact", str(OUT / "llm_twostep.jsonl"))
    ex("conclude", "--id", ID, "--verdict", a["verdict"], "--vs-criteria", "Criterion as pre-registered (Delta = BA(designer) - BA(two-step), lower bound > 0 and Delta >= 0.15 holds, Delta <= 0 does not hold)." + basis, "--basis", basis,
       "--limitations", "The first step reuses the generic matcher's cached output verbatim; the second step uses one prompt version, frozen before the run and not tuned; same hosted model, temperature 0; 12 sources resampled by source; ground truth is the final version (transcribed by the LLM, adjudicated by the LLM with the authors' approval).",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "hash": print(tmpl_hash())
    elif c == "llm": cmd_llm()
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
