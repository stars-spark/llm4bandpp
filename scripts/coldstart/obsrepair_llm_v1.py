#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM arm for collector repair: one deepseek-flash call per group.
A new client's collector may have a wrong unit, a constant offset or swapped short and long windows, while the network itself may legitimately differ from the reference.
The prompt gives the interface specification, reference percentiles of correctly collected calls and the new client's percentiles over its first three calls;
the model returns a diagnosis and correction ops (window swap, per-feature scale and offset) as JSON.
Writes experiments/results/obsrepair_v1/transforms_<phase>.json (group id -> ops) and caches replies in llm_<phase>.jsonl so runs can resume.
In the test phase the prompt template hash must equal the hash frozen after the dev phase. Usage: python obsrepair_llm_v1.py dev|test
"""
import hashlib, json, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import coldstart_rule_v1 as CR  # noqa: E402
O = ROOT / "experiments/results/obsrepair_v1"
FEAT = ["receiving rate (bits per second over the window)", "number of packets received in the window", "number of bytes received in the window",
        "queuing delay (ms): mean one-way delay minus the minimum one-way delay seen so far, non-negative",
        "mean one-way delay (ms), measured between unsynchronized sender and receiver clocks, so it contains an unknown constant offset and can be negative",
        "minimum one-way delay seen so far (ms), with the same unknown clock offset as feature 4",
        "delay ratio: mean one-way delay divided by the minimum delay (dimensionless, close to 1; 0 when no packet arrived)",
        "mean one-way delay minus the minimum one-way delay within the window (ms, non-negative)", "mean packet inter-arrival time (ms)",
        "packet jitter (ms)", "packet loss ratio (fraction between 0 and 1)", "mean number of lost packets per loss event", "share of video packets (fraction)",
        "share of audio packets (fraction)", "share of probing packets (fraction)"]
TEMPLATE = """You maintain the observation interface of a learned bandwidth estimator for real-time video calls. The estimator reads, every 60 ms, a 150-number observation:
15 features, each measured over 10 windows: windows 1 to 5 are five consecutive 60 ms windows (short), windows 6 to 10 are five consecutive 600 ms windows (long). The interface specification of the 15 features:
{spec}

A new client version has just been connected to a network. Its collector may have been implemented with mistakes, such as a wrong unit, a constant offset, or short and long windows in the wrong order. The network itself may also legitimately differ from the reference: higher or lower bandwidth, more delay, more loss. Wrongly "correcting" a legitimate difference damages the estimator as much as an uncorrected mistake.

Reference: percentiles (5th, 25th, 50th, 75th, 95th) of each feature over many correctly collected calls, short windows and long windows separately:
{ref}

New client: the same percentiles over the first 30 seconds of its first 3 calls:
{ev}

Decide whether the new client's observations contain collection mistakes, using what each feature means and how the features must relate to each other, not only how far they are from the reference. Then give the correction to apply to every future observation of this client, as JSON in a single ```json code block:
{{"diagnosis": "short explanation", "ops": [ ... ]}}
Each op is either {{"swap_windows": true}} (exchange short and long windows for every feature; applied first) or {{"feature": k, "windows": "all" or "short" or "long", "scale": a, "offset": b}} (value becomes value*a + b; k is the feature number 0 to 14 in the order listed). If the observations are consistent with the specification, say so and give an empty list; do not keep searching. Keep your reasoning brief."""


def fmt_q(d): return "\n".join(f"{k} {FEAT[k].split(' (')[0].split(':')[0]}: short {d[str(k)]['short']}; long {d[str(k)]['long']}" for k in range(15))


def build(ref, ev):
    spec = "\n".join(f"{k}. {s}" for k, s in enumerate(FEAT)); return TEMPLATE.format(spec=spec, ref=fmt_q(ref), ev=fmt_q(ev))


def main(phase):
    if not CR.AR.ok_to_send() or CR.AR.balance(CR.AR.KEY.read_text().strip()) < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE"); sys.exit(2)
    th = hashlib.sha256((TEMPLATE + json.dumps(FEAT)).encode()).hexdigest()
    if phase == "test":
        frozen = (O / "prompt_hash_frozen.txt").read_text().strip(); assert th == frozen, f"prompt template differs from the frozen version: {th[:12]} versus {frozen[:12]}"
    G = json.load(open(O / "groups.json")); E = json.load(open(O / "evidence.json")); cache = O / f"llm_{phase}.jsonl"; done = {}
    if cache.exists(): done = {j["id"]: j for j in map(json.loads, open(cache)) if j.get("ok")}
    jobs = sorted([g for g in G["groups"] if g["phase"] == phase and g["id"] not in done], key=lambda g: (g["draw"], g["id"])); lock = threading.Lock(); print("to run group", len(jobs), "template hash", th[:12], flush=True)
    def work(g):
        r = CR.ask(build(E["ref"], E["groups"][str(g["id"])]), 48000); txt = r["choices"][0]["message"].get("content") or ""; m = re.findall(r"```json\s*(.*?)```", txt, re.S)
        try: js = json.loads(m[-1]); ops = js.get("ops", []); ok = isinstance(ops, list)
        except Exception: js, ops, ok = {}, [], False
        rec = {"id": g["id"], "scen": g["scen"], "fault": g["fault"], "draw": g["draw"], "ops": ops, "diagnosis": js.get("diagnosis", ""), "ok": ok, "tail": txt[-400:], "usage": r.get("usage", {})}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); done[g["id"]] = rec; print(g["scen"], g["fault"], g["draw"], "ops", len(ops), "parsed" if ok else "parse failure", "output token", r.get("usage", {}).get("completion_tokens"), flush=True)
    for b in range(0, len(jobs), 10):
        if not CR.AR.ok_to_send(): print("peak hours started; stopping", flush=True); break
        bal = CR.AR.balance(CR.AR.KEY.read_text().strip())
        if bal < CR.AR.MIN_BALANCE: print(f"balance {bal} below {CR.AR.MIN_BALANCE}, stop", flush=True); break
        with ThreadPoolExecutor(5) as ex: list(ex.map(work, jobs[b:b + 10]))
        print("balance", bal, "Completed", min(b + 10, len(jobs)), "/", len(jobs), flush=True)
    T = {str(i): {"ops": d["ops"]} for i, d in done.items() if d.get("ok")}; (O / f"transforms_{phase}.json").write_text(json.dumps(T, ensure_ascii=False, indent=1))
    (O / f"prompt_hash_{phase}.txt").write_text(th); print("write out", len(T), "groups' correction ops")


if __name__ == "__main__":
    main(sys.argv[1])
