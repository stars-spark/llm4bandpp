#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM arm for interface adaptation on the synthetic schema: one deepseek-flash call per group and prompt variant.
NAMED shows the client's real field names; OBF replaces them with field_01 to field_15 (masked field names ablation).
Both show per-field percentiles next to the interface reference percentiles; the model maps each interface feature to one field and a scale factor.
Writes experiments/results/obsschema_v1/transforms_<phase>.json (group id -> {"LLM": mapping, "LLM_OBF": mapping}) and caches replies in llm_<phase>.jsonl so runs can resume.
In the test phase the prompt template hash must equal the frozen dev-phase hash. Usage: python obsschema_llm_v1.py dev|test
"""
import hashlib, json, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import coldstart_rule_v1 as CR  # noqa: E402
import obsrepair_llm_v1 as OR
O = ROOT / "experiments/results/obsschema_v1"
TEMPLATE = """A learned bandwidth estimator for real-time video calls reads, every 60 ms, an observation of 15 interface features, each measured over 10 windows (windows 1 to 5: five 60 ms windows; windows 6 to 10: five 600 ms windows). The interface specification:
{spec}

Reference: percentiles (5th, 25th, 50th, 75th, 95th) of each interface feature over many calls, short and long windows separately:
{ref}

A new client stack reports, for the same windows, 15 telemetry fields with its own names, units and order. They carry the same information as the interface features, but the units may differ (for example kbit/s instead of bit/s, seconds or microseconds instead of milliseconds, percent instead of fraction, bits instead of bytes). The fields and their percentiles over the first 30 seconds of its first 3 calls:
{fields}

Map the client's fields to the interface: for every interface feature, give the field index that carries it and the factor that converts the field's value into the interface unit (interface value = field value * scale). Use each field once. Answer as JSON in a single ```json code block: {{"mapping": [{{"feature": 0, "source": j, "scale": a}}, ... one entry for each feature 0 to 14]}}. Keep your reasoning brief."""


def fields_text(names, stats): return "\n".join(f"field {j} '{names[j]}': short {stats[j]['short']}; long {stats[j]['long']}" for j in range(len(names)))


def build(ref, names, stats):
    spec = "\n".join(f"{k}. {s}" for k, s in enumerate(OR.FEAT)); return TEMPLATE.format(spec=spec, ref=OR.fmt_q(ref), fields=fields_text(names, stats))


def parse(txt):
    """Read the last json block, strip // comments and turn a/b fractions into decimals, then return the 15-entry mapping."""
    m = re.findall(r"```json\s*(.*?)```", txt, re.S); body = re.sub(r"//[^\n]*", "", m[-1]); body = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\w.])", lambda q: repr(float(q.group(1)) / float(q.group(2))), body); js = json.loads(body); mp = [None] * 15
    for e in js["mapping"]: mp[int(e["feature"])] = {"source": int(e["source"]), "scale": float(e.get("scale", 1.0))}
    return mp


def main(phase):
    th = hashlib.sha256((TEMPLATE + json.dumps(OR.FEAT)).encode()).hexdigest()
    if phase == "test": assert th == (O / "prompt_hash_frozen.txt").read_text().strip(), "prompt template differs from the frozen version"
    G = json.load(open(O / "groups.json")); E = json.load(open(O / "evidence.json")); cache = O / f"llm_{phase}.jsonl"; done = {}
    if cache.exists(): done = {(j["id"], j["arm"]): j for j in map(json.loads, open(cache)) if j.get("ok")}
    jobs = sorted([(g, a) for g in G["groups"] if g["phase"] == phase for a in ("LLM", "LLM_OBF") if (g["id"], a) not in done], key=lambda x: (x[0].get("draw", 0), x[0]["id"], x[1]))
    lock = threading.Lock(); print("to run", len(jobs), "template hash", th[:12], flush=True)
    def work(ga):
        g, a = ga; e = E["groups"][str(g["id"])]; names = e["names"] if a == "LLM" else [f"field_{j + 1:02d}" for j in range(15)]
        r = CR.ask(build(E["ref"], names, e["stats"]), 48000); txt = r["choices"][0]["message"].get("content") or ""
        try: mp = parse(txt); ok = True
        except Exception: mp, ok = None, False
        rec = {"id": g["id"], "arm": a, "schema": g["schema"], "scen": g["scen"], "mapping": mp, "ok": ok, "tail": txt[-300:], "usage": r.get("usage", {})}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); done[(g["id"], a)] = rec; print(g["schema"], g["scen"][:12], a, "parsed" if ok else "parse failure", r.get("usage", {}).get("completion_tokens"), flush=True)
    for b in range(0, len(jobs), 10):
        if not CR.AR.ok_to_send(): print("peak hours started; stopping", flush=True); break
        bal = CR.AR.balance(CR.AR.KEY.read_text().strip())
        if bal < CR.AR.MIN_BALANCE: print(f"balance {bal} below {CR.AR.MIN_BALANCE}, stop", flush=True); break
        with ThreadPoolExecutor(5) as ex: list(ex.map(work, jobs[b:b + 10]))
        print("balance", bal, "Completed", min(b + 10, len(jobs)), "/", len(jobs), flush=True)
    T = {}
    for (i, a), d in done.items(): T.setdefault(str(i), {})[a] = d["mapping"]
    (O / f"transforms_{phase}.json").write_text(json.dumps(T, ensure_ascii=False)); (O / f"prompt_hash_{phase}.txt").write_text(th); print("write out", len(T), "group")


if __name__ == "__main__":
    main(sys.argv[1])
