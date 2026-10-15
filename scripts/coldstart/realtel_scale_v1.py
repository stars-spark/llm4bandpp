#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Designer test on 12 more real client stacks (registered experiment realtel-scale-v1).
Fields are transcribed in data/real_telemetry_specs_v2/ and the adjudicated ground truth is truth_final.json. Presentation follows realtel-adapter-v1: header, real names, location, official text, three field orders.
DeepSeek uses the frozen prompt (template hash d2467ef5dc35) and wall-clock time is logged per call; baselines are the seven methods of realtel-baseline-strength-v1 with their thresholds.
Usage: realtel_scale_v1.py build | llm | valentine | embed | judge [--selftest] | open_prompts | open_score
build makes sources.json from the transcription and the final ground truth; valentine and embed compute matcher similarities in their own environments;
judge scores, bootstraps, judges and records; open_prompts and open_score write prompts for and score the open R1-distilled models (report only).
"""
import hashlib, json, random, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
SPEC = ROOT / "data/real_telemetry_specs_v2/field_transcription.json"; OUT = ROOT / "experiments/results/realtel_scale_v1"; ID = "realtel-scale-v1"
FROZEN = "d2467ef5dc35"; PRICE_IN, PRICE_OUT = 0.3, 1.2


def load_sources():
    return {n: {"header": s["header"], "fields": [tuple(f) for f in s["fields"]], "truth": s["truth"]} for n, s in json.load(open(OUT / "sources.json")).items()}


CUT = re.compile(r"\s+combined with\b|,\s*split by\b|,\s*grouped by\b|,\s*with\s|\s+\((?:video|audio)\)|\s*\([^)]*other endpoint[^)]*\)|,\s*per\b|\s+per track\b", re.I)


def neutral_where(ctxs):
    """Pick the shortest location string without a transcriber usage hint (combined with, split by, ...); if all carry hints, the shortest after cutting the hint."""
    clean = sorted((c for c in ctxs if CUT.split(c)[0].strip(" ,;") == c), key=lambda c: (len(c), c))
    return clean[0] if clean else sorted((CUT.split(c)[0].strip(" ,;") for c in ctxs), key=lambda c: (len(c), c))[0]


def cmd_build():
    J = json.load(open(SPEC)); T = json.load(open(OUT / "truth_final.json"))["truth"]; S = {}
    for n, s in J.items():
        if s.get("status") != "kept": continue
        assert n in T, f"{n} no finalized ground truth"
        order, doc, where = [], {}, {}
        for k in range(15):
            e = s["features"][str(k)]; nm = e.get("name", "")
            if not nm or nm == "not found": continue
            if nm not in doc: order.append(nm); doc[nm] = []; where[nm] = set()
            where[nm].add(e.get("context", ""))
            q = (e.get("quote") or "").strip()
            if q and q not in doc[nm]: doc[nm].append(q)
        fields = [(nm, neutral_where(where[nm]), " ".join(doc[nm]) or "(no documentation text)") for nm in order]
        names = [f[0] for f in fields]
        for k, t in enumerate(T[n]):
            if t[0] == "same": assert t[1] in names, (n, k, t)
        S[n] = {"header": s["header"], "fields": fields, "truth": T[n]}
    OUT.mkdir(parents=True, exist_ok=True); json.dump(S, open(OUT / "sources.json", "w"), ensure_ascii=False, indent=1)
    cnt = lambda c: sum(x[0] == c for s in S.values() for x in s["truth"])
    print("source", len(S), "Same", cnt("same"), "none", cnt("none"), "different definition", cnt("kind"))


def cmd_llm():
    import coldstart_rule_v1 as CR
    assert M.tmpl_hash().startswith(FROZEN), "prompt template differs from the frozen version"
    S = load_sources(); cache = OUT / "llm_deepseek.jsonl"; done = {}
    if cache.exists(): done = {(j["source"], j["pres"]): j for j in map(json.loads, open(cache)) if j.get("ok")}
    jobs = [(n, k) for n in S for k in range(M.NPRES) if (n, k) not in done]; lock = threading.Lock(); print("to run", len(jobs), flush=True)
    def work(job):
        n, k = job; p = M.build_prompt(S[n], k); t0 = time.time(); r = CR.ask(p, 48000); wall = time.time() - t0; txt = r["choices"][0]["message"].get("content") or ""
        try: mp = M.parse(txt, len(S[n]["fields"])); ok = True
        except Exception: mp, ok = None, False
        rec = {"source": n, "pres": k, "mapping": mp, "ok": ok, "wall_s": wall, "usage": r.get("usage", {}), "tail": txt[-300:]}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); print(n, k, "parsed" if ok else "parse failure", round(wall, 1), "seconds", flush=True)
    if not CR.AR.ok_to_send() or CR.AR.balance(CR.AR.KEY.read_text().strip()) < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping"); return
    with ThreadPoolExecutor(6) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


def cmd_valentine():
    import pandas as pd
    from valentine import valentine_match
    from valentine.algorithms import Coma, Cupid, SimilarityFlooding
    S = load_sources(); res = {}
    for name, mk in (("COMA", lambda: Coma(use_instances=False)), ("CUPID", lambda: Cupid()), ("SF", lambda: SimilarityFlooding())):
        res[name] = {}
        for sn, src in S.items():
            fn = [f[0] for f in src["fields"]]; a = pd.DataFrame({c: ["1"] for c in fn}); b = pd.DataFrame({c: ["1"] for c in M.SHORT})
            r = valentine_match([a, b], mk()); mat = [[0.0] * len(fn) for _ in range(15)]
            for p, s in r.items():
                if p.source_column in fn and p.target_column in M.SHORT: mat[M.SHORT.index(p.target_column)][fn.index(p.source_column)] = float(s)
            res[name][sn] = mat
    json.dump(res, open(OUT / "scores_valentine.json", "w"))


def cmd_embed():
    import torch
    from transformers import AutoModel, AutoTokenizer
    S = load_sources(); res = {}; dev = "cuda" if torch.cuda.is_available() else "cpu"
    for name, mid, pool, qpref in (("BGE", "BAAI/bge-large-en-v1.5", "cls", "Represent this sentence for searching relevant passages: "), ("MPNET", "sentence-transformers/all-mpnet-base-v2", "mean", "")):
        src_dir = str(Path("/path/to/models") / mid)
        tok = AutoTokenizer.from_pretrained(src_dir); mod = AutoModel.from_pretrained(src_dir).to(dev).eval()
        def enc(texts):
            b = tok(texts, padding=True, truncation=True, max_length=512, return_tensors="pt").to(dev)
            with torch.no_grad(): h = mod(**b).last_hidden_state
            v = h[:, 0] if pool == "cls" else (h * b["attention_mask"].unsqueeze(-1)).sum(1) / b["attention_mask"].sum(1, keepdim=True)
            return torch.nn.functional.normalize(v.float(), dim=-1)
        Q = enc([qpref + f for f in M.FEAT]); res[name] = {}
        for sn, src in S.items(): D = enc([f"{n} | {w} | {d}" for n, w, d in src["fields"]]); res[name][sn] = (Q @ D.T).cpu().tolist()
        del mod; torch.cuda.empty_cache()
    json.dump(res, open(OUT / "scores_embed.json", "w"))


def decide(mat, tau):
    out = []
    for k in range(15):
        j = max(range(len(mat[k])), key=lambda j: mat[k][j]); out.append(j if mat[k][j] >= tau else None)
    return out


def base_maps(S):
    """Map the new sources with the seven baselines (presentation 0) using the thresholds of realtel-baseline-strength-v1."""
    taus = json.load(open(M.OUT / "strong_baselines/judge.json"))["baselines"]
    Sc = {"NAME": {n: [[M.sim_name(k, f[0]) for f in s["fields"]] for k in range(15)] for n, s in S.items()}, "TFIDF": {n: M.tfidf_matrix(s) for n, s in S.items()}}
    Sc.update(json.load(open(OUT / "scores_valentine.json"))); Sc.update(json.load(open(OUT / "scores_embed.json"))); out = {}
    for b, sc in Sc.items():
        out[b] = {}
        for n, s in S.items():
            dec = decide(sc[n], taus[b]["tau"]); fl = s["fields"]
            out[b][n] = [None if j is None else {"source": j, "diff": M.is_cum(fl[j][2]), "scale": M.unit_scale(k, fl[j][0], fl[j][2])} for k, j in enumerate(dec)]
    return out


def rows(S, maps):
    out = []
    for (n, k), mp in maps.items():
        f, _ = M.present(S[n], k); r = M.score(S[n]["truth"], f, mp); r.update({"source": n, "pres": k}); out.append(r)
    return out


def selftest():
    S = {f"s{i}": {"header": f"source {i} header text", "fields": [("a", "x", "Total number of packets"), ("b", "x", "bytes"), ("c", "x", "decoy")],
                   "truth": [["kind"]] + [["same", "a", True, 1.0]] + [["same", "b", False, 1.0]] + [["none"]] * 12} for i in range(6)}
    perfect = {}
    for n, s in S.items():
        for k in range(3):
            f, idx = M.present(s, k); perfect[(n, k)] = [({"source": idx[t[1]], "diff": t[2], "scale": t[3]} if t[0] == "same" else None) for t in s["truth"]]
    R = rows(S, perfect); assert M.ba(R) == 1.0
    bad = {(n, 0): [None] * 15 for n in S}; Rb = rows(S, bad); assert abs(M.ba(Rb) - 0.5) < 1e-9
    assert M.judge(R, {"A": Rb})[0] == "holds" and M.judge(Rb, {"A": R})[0] == "does not hold"
    print("Self-test passed (all correct 1.0, all missing 0.5, holds, does not hold)")


def cmd_judge():
    S = load_sources(); L = {}
    for j in map(json.loads, open(OUT / "llm_deepseek.jsonl")): L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    for n in S:
        for k in range(M.NPRES): L.setdefault((n, k), None)
    R_llm = rows(S, L); B = base_maps(S); R_base = {b: rows(S, {(n, 0): B[b][n] for n in S}) for b in B}
    v, m = M.judge(R_llm, R_base)
    recs = [json.loads(l) for l in open(OUT / "llm_deepseek.jsonl")]
    wall = sorted(r["wall_s"] for r in recs if r.get("ok")); usage = [r["usage"] for r in recs if r.get("ok")]
    cost = sorted((u.get("prompt_tokens", 0) * PRICE_IN + u.get("completion_tokens", 0) * PRICE_OUT) / 1e6 for u in usage)
    scored = [n for n in S if any(t[0] in ("same", "none") for t in S[n]["truth"])]
    perfect = {n: all(sum(r["same"]) == len(r["same"]) and sum(r["none"]) == len(r["none"]) for r in R_llm if r["source"] == n) for n in scored}
    med = lambda xs: xs[len(xs) // 2]
    extra = {"wall_median_s": med(wall), "wall_max_s": wall[-1], "cost_median_usd": med(cost), "cost_max_usd": cost[-1], "sources": len(S),
             "sources_all_correct_all_pres": sum(perfect.values()), "per_source_all_correct": perfect}
    # Report only: field identity without diff and scale, as in realtel-baseline-strength-v1.
    strip_t = lambda SS: {n: dict(s, truth=[["same", t[1], False, 1.0] if t[0] == "same" else t for t in s["truth"]]) for n, s in SS.items()}
    strip_m = lambda mp: None if mp is None else [None if x is None else {"source": x["source"], "diff": False, "scale": 1.0} for x in mp]
    Si = strip_t(S); _, mi = M.judge(rows(Si, {key: strip_m(mp) for key, mp in L.items()}), {b: rows(Si, {(n, 0): strip_m(B[b][n]) for n in S}) for b in B})
    # Report only: verdict under the alternative ground truth in truth_sens_round1.json; mappings unchanged.
    T1 = json.load(open(OUT / "truth_sens_round1.json"))["truth"]; S1 = {n: dict(s, truth=T1[n]) for n, s in S.items()}
    for n, s in S1.items(): assert all(t[0] != "same" or t[1] in [f[0] for f in s["fields"]] for t in s["truth"]), n
    v1, m1 = M.judge(rows(S1, L), {b: rows(S1, {(n, 0): B[b][n] for n in S}) for b in B})
    chrome = next(n for n in S if n.startswith("Chrome legacy"))
    extra.update({"id_only": {k: mi[k] for k in ("delta", "ci90", "ba_llm", "ba_base", "best_base")}, "sens_round1": {"verdict": v1, **{k: m1[k] for k in ("delta", "ci90", "ba_llm", "ba_base", "best_base", "false_map_rate")}},
                  "drift_chrome_legacy_all_correct": perfect[chrome]})
    json.dump({"verdict": v, **m, **extra, "rows_llm": R_llm, "rows_base": R_base}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    ns = sum(len(r["same"]) for r in R_llm); nn = sum(len(r["none"]) for r in R_llm)
    basis = (f"{len(S)} new real sources, 3 field orders each: DeepSeek maps same-quantity features {sum(sum(r['same']) for r in R_llm)}/{ns} and answers missing where no field exists {sum(sum(r['none']) for r in R_llm)}/{nn}, balanced accuracy {m['ba_llm']:.3f}; seven baselines " + ",".join(f"{b} {x:.3f}" for b, x in m["ba_base"].items()) + f", best: {m['best_base']}; Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; mis-mapping {m['false_map_rate']:.3f}. Report only: among the {len(perfect)} sources with scored cells, {extra['sources_all_correct_all_pres']} are fully correct in all three orders; per-client wall-clock median {extra['wall_median_s']:.1f} seconds (longest {extra['wall_max_s']:.1f}), cost median {extra['cost_median_usd']:.4f} USD (peak price); looking only at the field LLM {mi['ba_llm']:.3f}, best comparison {mi['best_base']} {mi['ba_base'][mi['best_base']]:.3f}, Δ {mi['delta']:+.3f} [{mi['ci90'][0]:+.3f}, {mi['ci90'][1]:+.3f}]; sensitivity (ground truth of the first round of checking) judged {v1}, Δ {m1['delta']:+.3f} [{m1['ci90'][0]:+.3f}, {m1['ci90'][1]:+.3f}], best comparison {m1['best_base']}; version drift: old Chrome version all three orders {'all correct' if perfect[chrome] else 'not all correct'} (the new W3C version is fully correct in realtel-adapter-v1).")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m[k] for k in ("delta", "ci90", "ba_llm", "ba_base", "false_map_rate")} | {k: extra[k] for k in ("wall_median_s", "cost_median_usd", "sources_all_correct_all_pres", "sources")}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template, the same as realtel-adapter-v1)." + basis, "--basis", basis,
       "--limitations", "Only the official field description, no values; ground truth given by the transcription and verified by two checkers; baseline thresholds come from the earlier dev sources; the sources are public documents that may be in the model's training data (checked separately by the name-masking experiment).",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    {"build": cmd_build, "llm": cmd_llm, "valentine": cmd_valentine, "embed": cmd_embed}.get(c, lambda: None)()
    if c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()


OPEN_W = "/path/to/server/work/openreason_v1"
OPEN_RUNS = {"r1_32b": ("gpu-server-1", "/path/to/server/models/DeepSeek-R1-Distill-Qwen-32B-int4-gptq"), "r1_14b": ("gpu-server-2", "/path/to/server/models/DeepSeek-R1-Distill-Qwen-14B")}


def cmd_open_prompts():
    assert M.tmpl_hash().startswith(FROZEN), "prompt template differs from the frozen version"
    S = load_sources(); p = OUT / "prompts_scale.jsonl"
    with open(p, "w") as f:
        for n in S:
            for k in range(M.NPRES): f.write(json.dumps({"id": f"scale|{n}|{k}", "prompt": M.build_prompt(S[n], k)}, ensure_ascii=False) + "\n")
    print("Written", p, len(S) * M.NPRES, "items")


def cmd_open_score():
    S = load_sources(); lines = []
    for tag in OPEN_RUNS:
        f = OUT / f"out_open_{tag}.jsonl"
        if not f.exists(): lines.append(f"{tag}: no result file"); continue
        L, nbad, toks = {}, 0, []
        for j in map(json.loads, open(f)):
            _, n, k = j["id"].split("|"); toks.append(j.get("n_tokens", 0))
            try: L[(n, int(k))] = M.parse(j["text"], len(S[n]["fields"]))
            except Exception: L[(n, int(k))] = None; nbad += 1
        for n in S:
            for k in range(M.NPRES): L.setdefault((n, k), None)
        R = rows(S, L); s = sum(sum(r["same"]) for r in R); ns = sum(len(r["same"]) for r in R); c = sum(sum(r["none"]) for r in R); nn = sum(len(r["none"]) for r in R)
        lines.append(f"{tag}: same quantity {s}/{ns}, none corresponding to missing answers {c}/{nn}, balanced accuracy {M.ba(R):.3f}, mis-mapping {sum(r['false_map'] for r in R)}/{nn}; unparseable {nbad}/{len(S) * M.NPRES} (counted as all missing); median output tokens {sorted(toks)[len(toks) // 2]}")
    txt = "Report only (open-source R1 distillation, same frozen prompt, temperature 0.6, one sample per item):" + ";".join(lines) + ". Does not change the conclusion of this experiment."
    print(txt); subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, txt], check=True)


if __name__ == "__main__" and sys.argv[1] in ("open_prompts", "open_score"):
    {"open_prompts": cmd_open_prompts, "open_score": cmd_open_score}[sys.argv[1]]()
