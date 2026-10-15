#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stronger non-LLM baselines for the real-telemetry designer test (realtel-baseline-strength-v1); LLM mappings are shared with realtel-adapter-v1. Baselines: Valentine 1.0 Coma
(schema only), Cupid and Similarity Flooding; two sentence-embedding retrievers (bge-large-en-v1.5, all-mpnet-base-v2); NAME and TFIDF. Each takes the top-scoring field per feature
and answers missing below a threshold tuned on the dev sources only (best dev BA, ties to the smaller threshold); the primary endpoint scores field identity only.
Second baseline set: the first, NAME and TFIDF only, is part of realtel_adapter_v1.py. realtel_revise_v1.py, realtel_namehide_v1.py, realtel_e2e_v1.py and closure_v1.py and _v2.py
import its scorers for the matcher comparators of Table IV and Fig. 3.
Usage (each in its own environment): realtel_baselines_v2.py valentine | embed | judge [--selftest]; valentine and embed write scores_valentine.json and scores_embed.json, judge tunes, scores, bootstraps by source and records.
"""
import json, random, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M
OUT = M.OUT / "strong_baselines"; ID = "realtel-baseline-strength-v1"; DELTA = 0.15; SEED = 20261004
SPLITS = {"dev": M.DEV, "test": M.TEST}


def cmd_valentine():
    import pandas as pd
    from valentine import valentine_match
    from valentine.algorithms import Coma, Cupid, SimilarityFlooding
    OUT.mkdir(parents=True, exist_ok=True); res = {}
    for name, mk in (("COMA", lambda: Coma(use_instances=False)), ("CUPID", lambda: Cupid()), ("SF", lambda: SimilarityFlooding())):
        res[name] = {}
        for sp, S in SPLITS.items():
            res[name][sp] = {}
            for sn, src in S.items():
                fn = [n for n, _, _ in src["fields"]]
                a = pd.DataFrame({c: ["1"] for c in fn}); b = pd.DataFrame({c: ["1"] for c in M.SHORT})
                r = valentine_match([a, b], mk()); mat = [[0.0] * len(fn) for _ in range(15)]
                for p, s in r.items():
                    if p.source_column in fn and p.target_column in M.SHORT: mat[M.SHORT.index(p.target_column)][fn.index(p.source_column)] = float(s)
                res[name][sp][sn] = mat
            print(name, sp, "complete", flush=True)
    json.dump(res, open(OUT / "scores_valentine.json", "w"))


def cmd_embed():
    import torch
    from transformers import AutoModel, AutoTokenizer
    OUT.mkdir(parents=True, exist_ok=True); res = {}; dev = "cuda" if torch.cuda.is_available() else "cpu"
    for name, mid, pool, qpref in (("BGE", "BAAI/bge-large-en-v1.5", "cls", "Represent this sentence for searching relevant passages: "),
                                   ("MPNET", "sentence-transformers/all-mpnet-base-v2", "mean", "")):
        loc = Path("/path/to/models") / mid; src = str(loc) if (loc / "model.safetensors").exists() else mid
        tok = AutoTokenizer.from_pretrained(src); mod = AutoModel.from_pretrained(src).to(dev).eval()
        def enc(texts):
            b = tok(texts, padding=True, truncation=True, max_length=512, return_tensors="pt").to(dev)
            with torch.no_grad(): h = mod(**b).last_hidden_state
            v = h[:, 0] if pool == "cls" else (h * b["attention_mask"].unsqueeze(-1)).sum(1) / b["attention_mask"].sum(1, keepdim=True)
            return torch.nn.functional.normalize(v.float(), dim=-1)
        Q = enc([qpref + f for f in M.FEAT]); res[name] = {}
        for sp, S in SPLITS.items():
            res[name][sp] = {}
            for sn, src in S.items():
                D = enc([f"{n} | {w} | {d}" for n, w, d in src["fields"]]); res[name][sp][sn] = (Q @ D.T).cpu().tolist()
        print(name, mid, "complete", flush=True); del mod; torch.cuda.empty_cache()
    json.dump(res, open(OUT / "scores_embed.json", "w"))


def classic_scores():
    """Recompute the NAME and TFIDF similarity matrices for the dev and test sources."""
    out = {"NAME": {}, "TFIDF": {}}
    for sp, S in SPLITS.items():
        out["NAME"][sp] = {sn: [[M.sim_name(k, n) for n, _, _ in s["fields"]] for k in range(15)] for sn, s in S.items()}
        out["TFIDF"][sp] = {sn: M.tfidf_matrix(s) for sn, s in S.items()}
    return out


def decide(mat, tau):
    out = []
    for k in range(15):
        j = max(range(len(mat[k])), key=lambda j: mat[k][j]); out.append(j if mat[k][j] >= tau else None)
    return out


def score_id(t, fields, dec):
    """Score field identity only: a same feature counts if its field is right, a none feature if it is answered missing."""
    same, none = [], []
    for k, x in enumerate(t):
        if x[0] == "same": same.append(int(dec[k] is not None and fields[dec[k]][0] == x[1]))
        elif x[0] == "none": none.append(int(dec[k] is None))
    return {"same": same, "none": none}


def ba(rows): return M.ba(rows)


def tune(scores_dev):
    cand = sorted({v for sn in scores_dev for row in scores_dev[sn] for v in row} | {0.0}) + [float("inf")]
    def dba(tau): return ba([score_id(M.truth(M.DEV[sn]), M.DEV[sn]["fields"], decide(scores_dev[sn], tau)) for sn in M.DEV])
    best = max(cand, key=lambda t: (dba(t), -t)); return best, dba(best)


def llm_rows(path):
    L = {}
    for l in open(path):
        j = json.loads(l)
        if "source" in j: n, k, mp = j["source"], j["pres"], (j["mapping"] if j.get("ok") else None)
        else:
            _, n, k = j["id"].split("|"); k = int(k)
            try: mp = M.parse(j["text"], len(M.TEST[n]["fields"]))
            except Exception: mp = None
        L[(n, k)] = mp
    rows = []
    for n in M.TEST:
        for k in range(M.NPRES):
            f, _ = M.present(M.TEST[n], k); mp = L.get((n, k)); dec = [None if (mp is None or m is None) else m["source"] for m in (mp or [None] * 15)]
            r = score_id(M.truth(M.TEST[n]), f, dec); r["source"] = n; rows.append(r)
    return rows


def judge(R_llm, R_base, seed=SEED, B=5000):
    srcs = sorted({r["source"] for r in R_llm}); best = max(R_base, key=lambda b: ba(R_base[b])); bl = R_base[best]
    def d(sel): return ba([r for s in sel for r in R_llm if r["source"] == s]) - ba([r for s in sel for r in bl if r["source"] == s])
    D = d(srcs); rng = random.Random(seed); boots = sorted(d([rng.choice(srcs) for _ in srcs]) for _ in range(B))
    lo, hi = boots[int(0.05 * B)], boots[int(0.95 * B) - 1]
    v = "does not hold" if not D > 0 else ("holds" if lo > 0 and D >= DELTA else "direction only")
    return v, {"delta": D, "ci90": [lo, hi], "best_base": best, "ba_llm": ba(R_llm), "ba_base": {b: ba(R_base[b]) for b in R_base}}


def selftest():
    for n, s in M.TEST.items():
        f, idx = M.present(s, 2); t = M.truth(s)
        r = score_id(t, f, [idx[x[1]] if x[0] == "same" else None for x in t]); assert all(r["same"]) and all(r["none"]), n
        r0 = score_id(t, f, [None] * 15); assert not any(r0["same"]) and all(r0["none"]), n
    mats = {}
    for sn, s in M.DEV.items():
        f = s["fields"]; t = M.truth(s); mat = [[0.1] * len(f) for _ in range(15)]
        for k, x in enumerate(t):
            if x[0] == "same": mat[k][[n for n, _, _ in f].index(x[1])] = 0.9
            else: mat[k][0] = 0.3
        mats[sn] = mat
    tau, d = tune(mats); assert 0.3 < tau <= 0.9 and abs(d - 1.0) < 1e-9, (tau, d)
    def mk(p_s, p_n, rng): return [{"source": n, "same": [int(rng.random() < p_s) for x in M.truth(M.TEST[n]) if x[0] == "same"], "none": [int(rng.random() < p_n) for x in M.truth(M.TEST[n]) if x[0] == "none"]} for n in M.TEST]
    rng = random.Random(2)
    assert judge(mk(1, 1, rng), {"A": mk(0.4, 0.6, rng)})[0] == "holds"
    assert judge(mk(0.6, 0.6, rng), {"A": mk(0.95, 0.95, rng)})[0] == "does not hold"
    print("Self-test passed (scoring, threshold, holds, does not hold)")


def cmd_judge():
    S = classic_scores(); S.update(json.load(open(OUT / "scores_valentine.json"))); S.update(json.load(open(OUT / "scores_embed.json")))
    R_base, info = {}, {}
    for b, sc in S.items():
        tau, dba = tune(sc["dev"]); rows = []; full = []
        for n, s in M.TEST.items():
            dec = decide(sc["test"][n], tau); r = score_id(M.truth(s), s["fields"], dec); r["source"] = n; rows.append(r)
            mp = [None if j is None else {"source": j, "diff": M.is_cum(s["fields"][j][2]), "scale": M.unit_scale(k, s["fields"][j][0], s["fields"][j][2])} for k, j in enumerate(dec)]
            fr = M.score(M.truth(s), s["fields"], mp); fr["source"] = n; full.append(fr)
        R_base[b] = rows; info[b] = {"tau": tau, "dev_ba": dba, "test_ba_id": ba(rows), "test_ba_full": ba(full),
                                     "same": sum(sum(r["same"]) for r in rows), "none": sum(sum(r["none"]) for r in rows)}
        print(b, info[b], flush=True)
    R_llm = llm_rows(M.OUT / "llm_test_deepseek.jsonl"); v, m = judge(R_llm, R_base)
    opens = {t: ba(llm_rows(M.OUT / f"out_open_{t}.jsonl")) for t in ("r1_32b", "r1_14b") if (M.OUT / f"out_open_{t}.jsonl").exists()}
    json.dump({"verdict": v, **m, "baselines": info, "open_models_ba_id": opens}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    nn = sum(len(r["none"]) for r in R_base[m["best_base"]]); ns = sum(len(r["same"]) for r in R_base[m["best_base"]]); bi = info[m["best_base"]]
    basis = (f"Field only: DeepSeek balanced accuracy {m['ba_llm']:.3f}; seven comparisons " + ",".join(f"{b} {x:.3f}" for b, x in m["ba_base"].items()) +
             f"; best is {m['best_base']} (same quantity {bi['same']}/{ns}, no-counterpart features answered missing {bi['none']}/{nn}, development threshold {bi['tau']:.3g}); Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]. Report only: full scoring including differencing and scale " + ",".join(f"{b} {info[b]['test_ba_full']:.3f}" for b in info) + f"; open models, same quantity {json.dumps({k: round(x, 3) for k, x in opens.items()})}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m[k] for k in ("delta", "ci90", "ba_llm", "ba_base")}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template)." + basis, "--basis", basis,
       "--limitations", "Thresholds are taken only on two development sources (27 scored decisions); the Valentine matcher reads only field names; only two sentence-embedding models are tried; seven sources; the LLM mappings are those of realtel-adapter-v1, already known when the baselines were run.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "valentine": cmd_valentine()
    elif c == "embed": cmd_embed()
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
