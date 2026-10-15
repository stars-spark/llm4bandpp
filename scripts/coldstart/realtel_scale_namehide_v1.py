#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Masked field names on the 12 client stacks of realtel-scale-v1 (registered experiment realtel-scale-namehide-v1).
Masking follows realtel-namehide-v1: field names become field_NN and each field's own name is replaced in its text.
Frozen prompt (template hash d2467ef5dc35), deepseek-flash with the same settings, three field orders per source, full scoring.
Baselines are the seven non-LLM matchers of realtel-scale-v1 on the real names.
Usage: realtel_scale_namehide_v1.py prompts | llm | judge
"""
import json, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_namehide_v1 as NH  # noqa: E402
import realtel_scale_v1 as RS  # noqa: E402
OUT = RS.OUT / "namehide"; ID = "realtel-scale-namehide-v1"


def hidden_sources():
    S = RS.load_sources(); H = {}
    for n, s in S.items():
        h = NH.hide({"header": s["header"], "fields": s["fields"]}); H[n] = {"header": h["header"], "fields": h["fields"], "truth": s["truth"]}
        # Ground truth names the real field; map it to the masked field_NN by position.
        name2h = {f[0]: hf[0] for f, hf in zip(s["fields"], h["fields"])}
        H[n]["truth"] = [["same", name2h[t[1]], t[2], t[3]] if t[0] == "same" else t for t in s["truth"]]
    return S, H


def cmd_prompts():
    S, H = hidden_sources(); OUT.mkdir(parents=True, exist_ok=True)
    json.dump(H, open(OUT / "sources_hidden.json", "w"), ensure_ascii=False, indent=1)
    leak = []
    for n in S:
        for (orig, _, _), (h, w, d) in zip(S[n]["fields"], H[n]["fields"]):
            if NH.ident_like(orig) and orig in d: leak.append((n, orig))
            if not NH.ident_like(orig) and (f'"{orig}"' in d): leak.append((n, orig))
    print("fields whose own name remains in their text:", leak)
    n0 = "Agora Web SDK"; print(M.build_prompt(H[n0], 0)[-1200:])
    assert not leak, "a field's own name remains in its text; stopping"


def cmd_llm():
    import coldstart_rule_v1 as CR
    assert M.tmpl_hash().startswith(RS.FROZEN), "prompt template differs from the frozen version"
    H = {n: {"header": s["header"], "fields": [tuple(f) for f in s["fields"]], "truth": s["truth"]} for n, s in json.load(open(OUT / "sources_hidden.json")).items()}
    cache = OUT / "llm_deepseek.jsonl"; done = {}
    if cache.exists(): done = {(j["source"], j["pres"]) for j in map(json.loads, open(cache)) if j.get("ok")}
    jobs = [(n, k) for n in H for k in range(M.NPRES) if (n, k) not in done]; lock = threading.Lock(); print("to run", len(jobs), flush=True)
    def work(job):
        n, k = job; p = M.build_prompt(H[n], k); t0 = time.time(); r = CR.ask(p, 48000); wall = time.time() - t0; txt = r["choices"][0]["message"].get("content") or ""
        try: mp = M.parse(txt, len(H[n]["fields"])); ok = True
        except Exception: mp, ok = None, False
        rec = {"source": n, "pres": k, "mapping": mp, "ok": ok, "wall_s": wall, "usage": r.get("usage", {}), "finish": r["choices"][0].get("finish_reason"), "tail": txt[-300:]}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); print(n, k, "parsed" if ok else "parse failure", round(wall, 1), "seconds", flush=True)
    if not CR.AR.ok_to_send() or CR.AR.balance(CR.AR.KEY.read_text().strip()) < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping"); return
    with ThreadPoolExecutor(6) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


def cmd_judge():
    H = {n: {"header": s["header"], "fields": [tuple(f) for f in s["fields"]], "truth": s["truth"]} for n, s in json.load(open(OUT / "sources_hidden.json")).items()}
    L = {}
    for j in map(json.loads, open(OUT / "llm_deepseek.jsonl")): L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    for n in H:
        for k in range(M.NPRES): L.setdefault((n, k), None)
    R_hid = RS.rows(H, L)
    S = RS.load_sources(); B = RS.base_maps(S); R_base = {b: RS.rows(S, {(n, 0): B[b][n] for n in S}) for b in B}
    v, m = M.judge(R_hid, R_base)
    named = json.load(open(RS.OUT / "judge.json"))["ba_llm"]
    nbad = sum(1 for j in map(json.loads, open(OUT / "llm_deepseek.jsonl")) if not j.get("ok"))
    per = {n: M.ba([r for r in R_hid if r["source"] == n]) for n in H if any(len(r["same"]) + len(r["none"]) for r in R_hid if r["source"] == n)}
    json.dump({"verdict": v, **m, "ba_named": named, "unparsed": nbad, "per_source": per, "rows": R_hid}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    basis = (f"12 new sources with field names masked, DeepSeek balanced accuracy {m['ba_llm']:.3f} (with real names {named:.3f}, drop {named - m['ba_llm']:.3f}); best of seven controls with real names {m['best_base']} {m['ba_base'][m['best_base']]:.3f}; Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; mis-mappings {m['false_map_rate']:.3f}; unparseable {nbad}/36. Per source {json.dumps({k: round(x, 3) for k, x in per.items()}, ensure_ascii=False)}")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m[k] for k in ("delta", "ci90", "ba_llm", "false_map_rate")} | {"ba_named": named, "unparsed": nbad}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (the same as realtel-namehide-v1)." + basis, "--basis", basis,
       "--limitations", "Only the field's own name is masked; the name of the object it belongs to and other field names in the description are not masked; compare against the real names; ground truth is the same as realtel-scale-v1.", "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    {"prompts": cmd_prompts, "llm": cmd_llm}.get(c, lambda: None)()
    if c == "judge": cmd_judge()
