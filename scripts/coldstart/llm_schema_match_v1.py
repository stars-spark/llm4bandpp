#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM schema-matching baseline for the designer (registered experiment llm-schema-match-baseline-v1).
The same hosted model (deepseek-flash, temperature 0) gets a generic schema-matching prompt: for each of the 15 interface features, name the matching source field or null.
The prompt says nothing about units, counter differencing or window semantics and asks for no adapter. Targets and source presentation (header, field names, location, text, three field orders) match what the designer sees in realtel_adapter_v1.
Matched fields get diff and scale from the keyword rules of the non-LLM baselines (is_cum, unit_scale) and are scored by the same function; a field-only score is also reported.
Sources: the 12 client stacks of realtel-scale-v1 (primary) and the 7 specifications of realtel-adapter-v1 (report only); designer mappings are read from those experiments' cached outputs.
Usage: llm_schema_match_v1.py hash | llm | judge [--selftest]
"""
import hashlib, json, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_scale_v1 as SC  # noqa: E402
OUT = ROOT / "experiments/results/llm_schema_match_v1"; ID = "llm-schema-match-baseline-v1"

GENERIC = """You are a schema matching system. Find the correspondences between the attributes of a source schema and the attributes of a target schema.

Target schema (15 attributes):
{targets}

Source schema: {header}
Source attributes, each with where it lives and the documentation text that defines it:
{fields}

For each target attribute, give the name of the source attribute that corresponds to it, or null if no source attribute corresponds to it. A source attribute may correspond to more than one target attribute. Answer as JSON in a single ```json code block: {{"matches": {{"T0": "source attribute name" or null, "T1": ..., one entry for each of T0 to T14}}}}. Keep your reasoning brief."""


def tmpl_hash(): return hashlib.sha256((GENERIC + json.dumps(M.FEAT) + json.dumps(M.SHORT)).encode()).hexdigest()


def build_prompt(src, k):
    f, _ = M.present(src, k)
    targets = "\n".join(f"T{i}: {M.SHORT[i]} - {M.FEAT[i]}" for i in range(15))
    fields = "\n".join(f"{n} | {w} | {d}" for (n, w, d) in f)
    return GENERIC.format(targets=targets, header=src["header"], fields=fields)


def parse(txt, f):
    """Parse the matcher's JSON into a per-feature mapping with rule-based diff and scale; return (mapping, count of names that match no field)."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", txt, re.S) or re.search(r"(\{\s*\"matches\".*\})", txt, re.S)
    d = json.loads(m.group(1))["matches"]; idx = {n: j for j, (n, _, _) in enumerate(f)}; out, bad = [], 0
    for k in range(15):
        v = d.get(f"T{k}")
        if v is None or (isinstance(v, str) and v.strip().lower() in ("", "null", "none")): out.append(None); continue
        j = idx.get(str(v).strip())
        if j is None: bad += 1; out.append(None); continue
        n, w, doc = f[j]; out.append({"source": j, "diff": M.is_cum(doc), "scale": M.unit_scale(k, n, doc)})
    return out, bad


def sets():
    S12 = SC.load_sources()
    S7 = {n: {"header": s["header"], "fields": [tuple(x) for x in s["fields"]], "truth": [list(t) for t in M.truth(s)]} for n, s in M.TEST.items()}
    return {"scale12": S12, "spec7": S7}


def cmd_llm():
    import coldstart_rule_v1 as CR
    OUT.mkdir(parents=True, exist_ok=True); h = tmpl_hash(); fz = OUT / "prompt_hash_frozen.txt"
    if fz.exists(): assert fz.read_text().strip() == h, "prompt differs from the frozen version"
    else: fz.write_text(h)
    cache = OUT / "llm_generic.jsonl"; done = set()
    if cache.exists(): done = {(j["set"], j["source"], j["pres"]) for j in map(json.loads, open(cache)) if j.get("ok")}
    SS = sets(); jobs = [(s, n, k) for s, S in SS.items() for n in S for k in range(M.NPRES) if (s, n, k) not in done]; lock = threading.Lock(); print("to run", len(jobs), flush=True)
    def work(job):
        s, n, k = job; src = SS[s][n]; f, _ = M.present(src, k); p = build_prompt(src, k); t0 = time.time(); r = CR.ask(p, 48000); wall = time.time() - t0
        txt = r["choices"][0]["message"].get("content") or ""
        try: mp, bad = parse(txt, f); ok = True
        except Exception: mp, bad, ok = None, None, False
        rec = {"set": s, "source": n, "pres": k, "mapping": mp, "unmatched_names": bad, "ok": ok, "wall_s": wall, "usage": r.get("usage", {}), "tail": txt[-300:]}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); print(s, n, k, "parsed" if ok else "parse failure", round(wall, 1), "seconds", flush=True)
    bal = CR.AR.balance(CR.AR.KEY.read_text().strip())
    if not CR.AR.ok_to_send() or bal < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping", bal); return
    with ThreadPoolExecutor(6) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


def rows(S, maps):
    out = []
    for (n, k), mp in maps.items():
        f, _ = M.present(S[n], k); r = M.score(S[n]["truth"], f, mp); r.update({"source": n, "pres": k}); out.append(r)
    return out


def strip(S, L):
    """Drop diff and scale from both ground truth and mappings so that only field identity is scored."""
    Si = {n: dict(s, truth=[["same", t[1], False, 1.0] if t[0] == "same" else t for t in s["truth"]]) for n, s in S.items()}
    Li = {key: (None if mp is None else [None if x is None else {"source": x["source"], "diff": False, "scale": 1.0} for x in mp]) for key, mp in L.items()}
    return Si, Li


def load_maps(path, setname=None):
    L = {}
    for j in map(json.loads, open(path)):
        if setname and j.get("set") != setname: continue
        L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    return L


def selftest():
    SC.selftest()
    f = [("bytesReceived", "x", "Total number of bytes received"), ("jitter", "x", "Packet jitter in seconds")]
    txt = 'reason\n```json\n{"matches": {"T2": "bytesReceived", "T7": "jitter", "T0": "nonexistent"}}\n```'
    mp, bad = parse(txt, f); assert bad == 1 and mp[2]["source"] == 0 and mp[2]["diff"] is True and mp[7]["source"] == 1 and mp[0] is None and mp[1] is None
    try: parse("no json here", f); raise AssertionError("Should fail to parse")
    except AssertionError: raise
    except Exception: pass
    print("Parsing self-test passed (names match, names that do not match count as missing, cumulative counters filled by differencing, no JSON judged as failure)")


def cmd_judge():
    SS = sets(); res = {}
    for s, S, dpath in (("scale12", SS["scale12"], SC.OUT / "llm_deepseek.jsonl"), ("spec7", SS["spec7"], M.OUT / "llm_test_deepseek.jsonl")):
        Ld = load_maps(dpath); Lg = load_maps(OUT / "llm_generic.jsonl", s)
        for n in S:
            for k in range(M.NPRES): Ld.setdefault((n, k), None); Lg.setdefault((n, k), None)
        Rd, Rg = rows(S, Ld), rows(S, Lg)
        v, m = M.judge(Rd, {"LLM_MATCH": Rg})
        Si, Ldi = strip(S, Ld); _, Lgi = strip(S, Lg); vi, mi = M.judge(rows(Si, Ldi), {"LLM_MATCH": rows(Si, Lgi)})
        gen = [json.loads(l) for l in open(OUT / "llm_generic.jsonl")]; gen = [g for g in gen if g["set"] == s]
        res[s] = {"verdict": v, **{k: m[k] for k in ("delta", "ci90", "ba_llm", "ba_base", "false_map_rate")}, "ba_designer": m["ba_llm"], "ba_llm_match": m["ba_base"]["LLM_MATCH"],
                  "id_only": {"verdict": vi, "delta": mi["delta"], "ci90": mi["ci90"], "ba_designer": mi["ba_llm"], "ba_llm_match": mi["ba_base"]["LLM_MATCH"]},
                  "llm_match_false_map_rate": sum(r["false_map"] for r in Rg) / max(1, sum(len(r["none"]) for r in Rg)),
                  "parse_fail": sum(1 for g in gen if not g["ok"]), "unmatched_names": sum(g["unmatched_names"] or 0 for g in gen if g["ok"]), "calls": len(gen),
                  "rows_designer": Rd, "rows_llm_match": Rg}
    OUT.mkdir(parents=True, exist_ok=True); json.dump(res, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    a, b = res["scale12"], res["spec7"]; jb = json.load(open(SC.OUT / "judge.json"))
    basis = (f"12 sources (3 field orders per source): designer BA {a['ba_designer']:.3f}, LLM schema matching {a['ba_llm_match']:.3f} (best of seven non-LLM controls {jb['best_base']} is {jb['ba_base'][jb['best_base']]:.3f}); Δ (designer minus schema matching) {a['delta']:+.3f}, 90% interval [{a['ci90'][0]:+.3f}, {a['ci90'][1]:+.3f}]. Report only: fields only designer {a['id_only']['ba_designer']:.3f}, schema matching {a['id_only']['ba_llm_match']:.3f}, Δ {a['id_only']['delta']:+.3f} [{a['id_only']['ci90'][0]:+.3f}, {a['id_only']['ci90'][1]:+.3f}]; schema matching mis-mapping rate {a['llm_match_false_map_rate']:.3f}, parse failures {a['parse_fail']}/{a['calls']}, name mismatches {a['unmatched_names']} items; 7 specifications (report only) designer {b['ba_designer']:.3f}, schema matching {b['ba_llm_match']:.3f}, Δ {b['delta']:+.3f} [{b['ci90'][0]:+.3f}, {b['ci90'][1]:+.3f}], fields only Δ {b['id_only']['delta']:+.3f}.")
    print(a["verdict"], basis)
    ex = lambda *x: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *x], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({s: {k: res[s][k] for k in ("delta", "ci90", "ba_designer", "ba_llm_match", "parse_fail", "unmatched_names")} | {"id_only": res[s]["id_only"]} for s in res}, ensure_ascii=False),
       "--artifact", str(OUT / "judge.json"), "--artifact", str(OUT / "llm_generic.jsonl"))
    ex("conclude", "--id", ID, "--verdict", a["verdict"], "--vs-criteria", "Criterion as pre-registered (the same template as realtel-scale-v1, with the control replaced by generic schema matching of the same hosted model)." + basis, "--basis", basis,
       "--limitations", "The general prompt has only one version, written and frozen following the approach of [35] to [37], not tuned; differencing and scale for the matched fields come from our keyword rules (as for the seven baselines); 12 sources, resampled by source; ground truth transcribed by the LLM, before the external blind labelling; 7 specifications report only.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "hash": print(tmpl_hash())
    elif c == "llm": cmd_llm()
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
