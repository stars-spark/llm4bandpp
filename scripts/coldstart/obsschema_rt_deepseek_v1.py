#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Report-only extension of registered experiment obsschema-strong-baseline-v1: DeepSeek with the frozen obsschema-llm-v1 prompt on the 40 new real-name groups.
Caches replies in deepseek_new40.jsonl, writes transforms_new_deepseek.json, runs the same offline evaluation on the remote host and adds the success counts as a registry note.
Usage: python obsschema_rt_deepseek_v1.py
"""
import json, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import coldstart_rule_v1 as CR  # noqa: E402
import obsschema_llm_v1 as L  # noqa: E402
NEW = ROOT / "experiments/results/obsschema_rt_openreason_v1"; O = ROOT / "experiments/results/obsschema_strong_baseline_v1"; R_NEW = "/path/to/server/outputs/obsschema_rt_v1"
SSH = ["ssh", "-o", "ConnectTimeout=20", "-o", "BatchMode=yes"]; cache = O / "deepseek_new40.jsonl"


def main():
    P = [json.loads(l) for l in open(NEW / "prompts.jsonl") if json.loads(l)["id"].endswith("|LLM")]
    done = {json.loads(l)["gid"] for l in open(cache)} if cache.exists() else set(); lock = threading.Lock()
    def work(r):
        gid = r["id"].split("|")[1]
        if gid in done: return
        x = CR.ask(r["prompt"], 48000); txt = x["choices"][0]["message"].get("content") or ""
        try: mp, ok = L.parse(txt), True
        except Exception: mp, ok = None, False
        with lock: cache.open("a").write(json.dumps({"gid": gid, "ok": ok, "mapping": mp, "usage": x.get("usage", {})}) + "\n")
        print(gid, "parsed" if ok else "parse failure", x.get("usage", {}).get("completion_tokens"), flush=True)
    todo = [r for r in P if r["id"].split("|")[1] not in done]
    for b in range(0, len(todo), 10):
        if not CR.AR.ok_to_send() or CR.AR.balance(CR.AR.KEY.read_text().strip()) < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping"); sys.exit(2)
        with ThreadPoolExecutor(5) as ex: list(ex.map(work, todo[b:b + 10]))
    T = {}
    for l in open(cache):
        j = json.loads(l)
        if j["ok"]: T[j["gid"]] = {"DEEPSEEK": j["mapping"]}
    (O / "transforms_new_deepseek.json").write_text(json.dumps(T))
    subprocess.run(["scp", "-q", str(O / "transforms_new_deepseek.json"), f"gpu-server-1:{R_NEW}/transforms_deepseek.json"], check=True)
    py = "python3"
    subprocess.run(SSH + ["gpu-server-1", f"cd /path/to/server/work && {py} obsschema_rt_offline_v1.py eval {R_NEW}/transforms_deepseek.json deepseek > {R_NEW}/eval_deepseek.log 2>&1"], stdin=subprocess.DEVNULL, timeout=7200, check=True)
    subprocess.run(["scp", "-q", f"gpu-server-1:{R_NEW}/eval_deepseek.json", str(O / "eval_new_deepseek.json")], check=True)
    E = json.load(open(O / "eval_new_deepseek.json"))["results"]; B = json.load(open(O / "eval_new_unitname.json"))["results"]
    med = lambda res, m: (lambda xs: float(np.nanmedian(xs)) if any(x == x for x in xs) else float("nan"))([r.get(m, np.nan) for r in res.values()])
    ds = sum(med(E[g], "DEEPSEEK") <= 1.2 for g in E); ub = sum(med(B[g], "UNITNAME") <= 1.2 for g in B); n = len(E); parsed = len(T)
    msg = f"Report-only results: on the new 40 groups, DeepSeek per-client mapping succeeded {ds}/{n} (parseable {parsed}/40), the rule-based matcher {ub}/{n} on the same groups; with the old 32 groups (DeepSeek 32/32, rule-based matcher 32/32), over all 72 groups DeepSeek {32 + ds}, rule-based matcher {32 + ub}."
    print(msg); subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", "obsschema-strong-baseline-v1", msg], check=True)


if __name__ == "__main__":
    main()
