#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repeated designer calls on the 12 real client stacks (registered experiment realtel-repeat-v1).
Sources, frozen prompt, parsing, scoring, baseline mappings and judging are reused unchanged from realtel_scale_v1 and realtel_adapter_v1.
Repetition 0 is the original realtel-scale-v1 call (report only); repetitions 1 and 2 are new calls and form the primary endpoint.
Usage: realtel_repeat_v1.py llm | judge [--selftest]
llm calls DeepSeek, logs model id and send time per call and resumes from the cache (ALLOW_PEAK=1 skips the off-peak gate); judge scores, bootstraps, judges and records.
"""
import json, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_scale_v1 as RS  # noqa: E402
OUT = ROOT / "experiments/results/realtel_repeat_v1"; ID = "realtel-repeat-v1"; REPS = (1, 2)


def cmd_llm():
    import coldstart_rule_v1 as CR
    assert M.tmpl_hash().startswith(RS.FROZEN), "prompt template differs from the frozen version"
    S = RS.load_sources(); OUT.mkdir(parents=True, exist_ok=True); cache = OUT / "llm_repeat.jsonl"; done = set()
    if cache.exists(): done = {(j["rep"], j["source"], j["pres"]) for j in map(json.loads, open(cache)) if j.get("ok") is not None}
    jobs = [(r, n, k) for r in REPS for n in S for k in range(M.NPRES) if (r, n, k) not in done]; lock = threading.Lock(); print("to run", len(jobs), flush=True)
    def work(job):
        rep, n, k = job; p = M.build_prompt(S[n], k); t0 = time.time(); r = CR.ask(p, 48000); wall = time.time() - t0
        txt = r["choices"][0]["message"].get("content") or ""
        try: mp = M.parse(txt, len(S[n]["fields"])); ok = True
        except Exception: mp, ok = None, False
        rec = {"rep": rep, "source": n, "pres": k, "mapping": mp, "ok": ok, "wall_s": wall, "usage": r.get("usage", {}), "model": r.get("model"),
               "created": r.get("created"), "sent_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)), "tail": txt[-300:]}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); print(rep, n, k, "parsed" if ok else "parse failure", round(wall, 1), "seconds", r.get("model"), flush=True)
    peak_ok = __import__("os").environ.get("ALLOW_PEAK") == "1"
    if not (peak_ok or CR.AR.ok_to_send()) or CR.AR.balance(CR.AR.KEY.read_text().strip()) < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping"); return
    with ThreadPoolExecutor(6) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


def load_maps(S):
    """Return {repetition: {(source, order): mapping or None}}, with repetition 0 from the realtel-scale-v1 cache; the last record of a cell wins."""
    L = {0: {}}
    for j in map(json.loads, open(RS.OUT / "llm_deepseek.jsonl")): L[0][(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    for j in map(json.loads, open(OUT / "llm_repeat.jsonl")): L.setdefault(j["rep"], {})[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    for r in L:
        for n in S:
            for k in range(M.NPRES): L[r].setdefault((n, k), None)
    return L


def agreement(S, L, reps):
    """Return the share of (source, order, feature) cells with identical mappings across repetitions and the number of identical whole mappings."""
    cells = same_cells = whole = 0
    for n in S:
        for k in range(M.NPRES):
            mps = [L[r][(n, k)] for r in reps]; whole += int(all(m == mps[0] for m in mps))
            for f in range(15):
                v = [None if m is None else m[f] for m in mps]; cells += 1; same_cells += int(all(x == v[0] for x in v))
    return same_cells / cells, whole


def selftest():
    S = RS.load_sources(); assert len(S) == 12, len(S)
    L0 = {}
    for j in map(json.loads, open(RS.OUT / "llm_deepseek.jsonl")): L0[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    for n in S:
        for k in range(M.NPRES): L0.setdefault((n, k), None)
    R0 = RS.rows(S, L0); assert round(M.ba(R0), 3) == 0.920, M.ba(R0)
    B = RS.base_maps(S); R_base = {b: RS.rows(S, {(n, 0): B[b][n] for n in S}) for b in B}
    best = max(R_base, key=lambda b: M.ba(R_base[b])); assert best == "CUPID" and round(M.ba(R_base[best]), 3) == 0.560, (best, M.ba(R_base[best]))
    bad = {(n, k): None for n in S for k in range(M.NPRES)}; Rb = RS.rows(S, bad) + RS.rows(S, bad)
    assert M.judge(Rb, R_base)[0] == "does not hold"
    assert M.judge(R0 + R0, R_base)[0] == "holds"
    a, w = agreement(S, {0: L0, 1: L0, 2: L0}, (0, 1, 2)); assert a == 1.0 and w == 36
    a2, _ = agreement(S, {0: L0, 1: bad, 2: L0}, (0, 1, 2)); assert a2 < 1.0
    print("Self-test passed: reproduces 0.920 and Cupid 0.560; verdict and agreement cases")


def cmd_judge():
    S = RS.load_sources(); L = load_maps(S)
    recs = [json.loads(l) for l in open(OUT / "llm_repeat.jsonl")]
    assert all(r in L and len(L[r]) == 36 for r in REPS), {r: len(L.get(r, {})) for r in REPS}
    B = RS.base_maps(S); R_base = {b: RS.rows(S, {(n, 0): B[b][n] for n in S}) for b in B}
    R = {r: RS.rows(S, L[r]) for r in (0,) + REPS}
    v, m = M.judge(R[1] + R[2], R_base)
    ba_rep = {r: M.ba(R[r]) for r in R}; ba_all3 = M.ba(R[0] + R[1] + R[2])
    strip_t = {n: dict(s, truth=[["same", t[1], False, 1.0] if t[0] == "same" else t for t in s["truth"]]) for n, s in S.items()}
    strip_m = lambda mp: None if mp is None else [None if x is None else {"source": x["source"], "diff": False, "scale": 1.0} for x in mp]
    ba_id = {r: M.ba(RS.rows(strip_t, {key: strip_m(mp) for key, mp in L[r].items()})) for r in R}
    agr3, whole3 = agreement(S, L, (0, 1, 2)); agr_new, whole_new = agreement(S, L, REPS)
    scored = [n for n in S if any(t[0] in ("same", "none") for t in S[n]["truth"])]
    perfect = {n: all(all(x["same"]) and all(x["none"]) for r in R for x in R[r] if x["source"] == n) for n in scored}
    fails = sum(1 for j in recs if not j.get("ok")); models = sorted({j.get("model") for j in recs}); days = sorted({j["sent_utc"][:10] for j in recs})
    res = {"verdict": v, **m, "ba_by_rep": ba_rep, "ba_all3": ba_all3, "ba_range": [min(ba_rep.values()), max(ba_rep.values())], "ba_id_only_by_rep": ba_id,
           "cell_agreement_3": agr3, "whole_same_3": whole3, "cell_agreement_new": agr_new, "whole_same_new": whole_new,
           "sources_all_correct_all_reps": sum(perfect.values()), "n_scored_sources": len(perfect), "parse_fail_new": fails, "models": models, "days_utc": days}
    json.dump(res, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    basis = (f"12 stacks, 3 orders per stack, two new calls merged BA {m['ba_llm']:.3f}, best control {m['best_base']} {m['ba_base'][m['best_base']]:.3f}, Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; mis-mappings {m['false_map_rate']:.3f}. Report only: BA per call {json.dumps({k: round(x, 3) for k, x in ba_rep.items()})} (call 0 is the original call), three-call merge {ba_all3:.3f}; fields only {json.dumps({k: round(x, 3) for k, x in ba_id.items()})}; per-cell three-call agreement {agr3:.3f}, whole-file identical {whole3}/36 (between the two new calls {agr_new:.3f}, {whole_new}/36); sources fully correct in all three {sum(perfect.values())}/{len(perfect)}; new-call parse failures {fails}/72; model identifier {models}; call date (UTC) {days}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: res[k] for k in ("delta", "ci90", "ba_llm", "ba_by_rep", "ba_all3", "ba_range", "cell_agreement_3", "whole_same_3", "parse_fail_new", "models", "days_utc")}, ensure_ascii=False, default=str),
       "--artifact", str(OUT / "judge.json"), "--artifact", str(OUT / "llm_repeat.jsonl"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (the confirmatory template is verbatim identical to realtel-scale-v1, the primary endpoint uses only two new calls)." + basis, "--basis", basis,
       "--limitations", "Only the 12 stacks are repeated; the 7 specifications, the end-to-end and the closed-loop tests are not repeated; the two repetitions ran on one day, so drift is covered only between the call dates; the hosted model size and version are not disclosed.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "llm": cmd_llm()
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
