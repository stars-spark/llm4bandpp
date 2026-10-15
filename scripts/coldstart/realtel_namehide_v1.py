#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Masked field names on the seven real sources (registered experiment realtel-namehide-v1), a check against recalling interface names.
Documentation text and field locations are kept; each field name becomes field_NN, and the field's own name inside its text (identifier or quoted form) is replaced too.
Prompt: frozen realtel-adapter-v1 template (hash checked), deepseek-flash with the same settings, three field orders per source.
Scoring uses the ground truth in truth_v3.json with the full score; baselines are the seven non-LLM matchers on the real names.
Usage: realtel_namehide_v1.py prompts | llm | judge [--selftest]; prompts writes the masked sources and prints one for a manual leak check.
"""
import json, random, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
OUT = M.OUT / "namehide_v1"; ID = "realtel-namehide-v1"; DELTA = 0.15; FALSE_MAP_MAX = 0.15; SEED = 20261006


def ident_like(n): return bool(re.search(r"[A-Z_\-\[\]/:]", n))


def hide(src):
    """Return a copy of a source with field names replaced by field_NN (transcription order) and each field's own name masked in its text."""
    fs = []
    for j, (n, w, d) in enumerate(src["fields"]):
        h = f"field_{j + 1:02d}"; dd = d
        pats = [re.escape(n)] if ident_like(n) else [r'"' + re.escape(n) + r'"', r"`" + re.escape(n) + r"`", r"\b" + re.escape(n) + r"\b(?=\s*[:=])"]
        for p in pats: dd = re.sub(p, h if not p.startswith('"') else f'"{h}"', dd)
        fs.append((h, w, dd))
    return {"header": src["header"], "fields": fs}


HID = {n: hide(s) for n, s in M.TEST.items()}


def cmd_prompts():
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(HID, open(OUT / "sources_hidden.json", "w"), ensure_ascii=False, indent=1)
    leak = []
    for n, s in M.TEST.items():
        for (orig, _, _), (h, w, d) in zip(s["fields"], HID[n]["fields"]):
            if ident_like(orig) and orig in d: leak.append((n, orig))
            if not ident_like(orig) and (f'"{orig}"' in d): leak.append((n, orig))
    print("fields whose own name remains in their text:", leak)
    print(M.build_prompt(HID["gstreamer_rtpmanager"], 0).split("The fields it exposes")[1][:1500])


def cmd_llm():
    import coldstart_rule_v1 as CR
    assert M.tmpl_hash() == (M.OUT / "prompt_hash_frozen.txt").read_text().strip(), "prompt template differs from the frozen version"
    cache = OUT / "llm_hidden_deepseek.jsonl"; done = {}
    if cache.exists(): done = {(j["source"], j["pres"]): j for j in map(json.loads, open(cache)) if j.get("ok")}
    jobs = [(n, k) for n in HID for k in range(M.NPRES) if (n, k) not in done]; lock = threading.Lock(); print("to run", len(jobs), flush=True)
    def work(job):
        n, k = job; r = CR.ask(M.build_prompt(HID[n], k), 48000); txt = r["choices"][0]["message"].get("content") or ""
        try: mp = M.parse(txt, len(HID[n]["fields"])); ok = True
        except Exception: mp, ok = None, False
        rec = {"source": n, "pres": k, "mapping": mp, "ok": ok, "tail": txt[-400:], "usage": r.get("usage", {})}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); print(n, k, "parsed" if ok else "parse failure", flush=True)
    if not CR.AR.ok_to_send() or CR.AR.balance(CR.AR.KEY.read_text().strip()) < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping"); return
    with ThreadPoolExecutor(5) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


def truth3(): return json.load(open(M.OUT / "truth_v3.json"))["truth"]


def rows(T, maps):
    """Score mappings keyed by (source, presentation) against ground truth T; masking keeps the field order of realtel_adapter_v1.present."""
    out = []
    for (n, k), mp in maps.items():
        f, _ = M.present(M.TEST[n], k); r = M.score(T[n], f, mp); r.update({"source": n, "pres": k}); out.append(r)
    return out


def base_full(T):
    """Score the seven non-LLM baselines on real names in full: dev-tuned field choice plus the generic unit and diff rules, presentation 0."""
    import realtel_baselines_v2 as V
    S = V.classic_scores(); S.update(json.load(open(V.OUT / "scores_valentine.json"))); S.update(json.load(open(V.OUT / "scores_embed.json")))
    taus = json.load(open(V.OUT / "judge.json"))["baselines"]; R = {}
    for b, sc in S.items():
        maps = {}
        for n, s in M.TEST.items():
            dec = V.decide(sc["test"][n], taus[b]["tau"]); fl = s["fields"]
            maps[(n, 0)] = [None if j is None else {"source": j, "diff": M.is_cum(fl[j][2]), "scale": M.unit_scale(k, fl[j][0], fl[j][2])} for k, j in enumerate(dec)]
        R[b] = rows(T, maps)
    return R


def selftest():
    for n, s in M.TEST.items():
        assert len(HID[n]["fields"]) == len(s["fields"]) and HID[n]["header"] == s["header"]
        for (o, w, _), (h, w2, d) in zip(s["fields"], HID[n]["fields"]):
            assert w == w2 and h.startswith("field_") and not (ident_like(o) and o in d), (n, o)
    assert "field_02" in HID["gstreamer_rtpmanager"]["fields"][1][2]
    rng = random.Random(1)
    def mk(p_s, p_n, fm):
        out = []
        for n in M.TEST:
            t = truth3()[n]; s = [int(rng.random() < p_s) for x in t if x[0] == "same"]; nn = [int(rng.random() < p_n) for x in t if x[0] == "none"]
            out.append({"source": n, "pres": 0, "same": s, "none": nn, "false_map": sum(1 - x for x in nn) if fm else 0})
        return out
    assert M.judge(mk(0.97, 0.97, 1), {"A": mk(0.5, 0.6, 1)})[0] == "holds"
    assert M.judge(mk(0.6, 0.6, 1), {"A": mk(0.95, 0.95, 1)})[0] == "does not hold"
    print("Self-test passed (name masking does not change order, no residual own name, holds, does not hold)")


def cmd_judge():
    T = truth3(); L = {}
    for j in map(json.loads, open(OUT / "llm_hidden_deepseek.jsonl")):
        if j.get("ok"): L[(j["source"], j["pres"])] = j["mapping"]
    for n in M.TEST:
        for k in range(M.NPRES): L.setdefault((n, k), None)
    R_llm = rows(T, L); R_base = base_full(T); v, m = M.judge(R_llm, R_base)
    named = rows(T, {(j["source"], j["pres"]): (j["mapping"] if j.get("ok") else None) for j in map(json.loads, open(M.OUT / "llm_test_deepseek.jsonl"))})
    m["ba_llm_named"] = M.ba(named); m["drop_vs_named"] = m["ba_llm_named"] - m["ba_llm"]
    json.dump({"verdict": v, **m, "rows_llm": R_llm}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    ns = sum(len(r["same"]) for r in R_llm); nn = sum(len(r["none"]) for r in R_llm)
    basis = (f"With field names masked, DeepSeek same quantity {sum(sum(r['same']) for r in R_llm)}/{ns}, no-counterpart features answered missing {sum(sum(r['none']) for r in R_llm)}/{nn}, balanced accuracy {m['ba_llm']:.3f} ({m['ba_llm_named']:.3f} with real names; decrease {m['drop_vs_named']:+.3f}); full scores of the seven controls, which see the real names: " + ",".join(f"{b} {x:.3f}" for b, x in m["ba_base"].items()) + f", best: {m['best_base']}; Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; mis-mapping {m['false_map_rate']:.3f}. Ground truth version 3.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: m[k] for k in ("delta", "ci90", "ba_llm", "ba_llm_named", "ba_base", "false_map_rate")}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template)." + basis, "--basis", basis,
       "--limitations", "The description still contains other field names and code variable names in the original text; only the field's own name is masked; seven sources; names of the enclosing objects are kept; ground truth is the third, revised version.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "prompts": cmd_prompts()
    elif c == "llm": cmd_llm()
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
