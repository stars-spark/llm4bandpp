#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Open reasoning models on five new synthetic schemas, test_g to test_j and rt_getstats (registered experiment obsschema-openreason-newschema-v1).
40 new call groups, each prompted with real and with masked field names; the prompt is the frozen obsschema-llm-v1 template (hash checked).
Main arm: DeepSeek-R1-Distill-Qwen 32B, 4-bit; the 14B model is report only. Temperature 0.6, at most 32768 tokens, one sample per group.
Usage: obsschema_rt_openreason_v1.py prep | finalize TAG MODEL HOST | judge
prep fetches the evidence and writes the prompts; finalize waits for the remote run, parses, evaluates offline, judges and records; judge runs the self-test.
"""
import hashlib, json, random, re, subprocess, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import obsschema_llm_v1 as L  # noqa: E402
O = ROOT / "experiments/results/obsschema_rt_openreason_v1"; ID = "obsschema-openreason-newschema-v1"; RO = "/path/to/server/outputs/obsschema_rt_v1"; W = "/path/to/server/work/openreason_v1"
SSH = ["ssh", "-o", "ConnectTimeout=20", "-o", "BatchMode=yes"]; SCHEMAS = ["test_g", "test_h", "test_i", "test_j", "rt_getstats"]; DELTA = 0.25


def sh(host, cmd, **kw): return subprocess.run(SSH + [host, cmd], stdin=subprocess.DEVNULL, capture_output=True, text=True, **kw)


def prep():
    O.mkdir(parents=True, exist_ok=True)
    th = hashlib.sha256((L.TEMPLATE + json.dumps(L.OR.FEAT)).encode()).hexdigest(); assert th == (L.O / "prompt_hash_frozen.txt").read_text().strip(), "prompt differs from the frozen version"
    for f in ("groups.json", "evidence.json"): subprocess.run(["scp", "-q", f"gpu-server-1:{RO}/{f}", str(O / f)], check=True)
    G = json.load(open(O / "groups.json"))["groups"]; E = json.load(open(O / "evidence.json")); n = 0
    with open(O / "prompts.jsonl", "w") as f:
        for g in G:
            e = E["groups"][str(g["id"])]
            for a in ("LLM", "LLM_OBF"):
                names = e["names"] if a == "LLM" else [f"field_{j + 1:02d}" for j in range(15)]
                f.write(json.dumps({"id": f"obsschema|{g['id']}|{a}", "prompt": L.build(E["ref"], names, e["stats"])}, ensure_ascii=False) + "\n"); n += 1
    (O / "prompt_hash.txt").write_text(th); print("prompt", n, "group", len(G), "template hash", th[:12])


def judge(rows, seed=20261008, B=5000):
    """Apply the registered criterion: delta = (LLM real-name successes - better of DIST and NAME) / groups, call-set bootstrap; holds at lower 90% bound > 0 and delta >= 0.25, does not hold on delta <= 0 or more severe failures (median ratio > 2) than that baseline."""
    n = len(rows); s = {m: sum(r[m] for r in rows) for m in ("LLM", "LLM_OBF", "DIST", "NAME")}; best = max(("DIST", "NAME"), key=lambda m: s[m])
    d = lambda rs: (sum(r["LLM"] - r[best] for r in rs) / len(rs)) if rs else float("nan")
    D = d(rows); cs = sorted({r["cs"] for r in rows}); rng = random.Random(seed); boots = []
    for _ in range(B): pick = [rng.choice(cs) for _ in cs]; boots.append(d([r for c in pick for r in rows if r["cs"] == c]))
    lo, hi = float(np.percentile(boots, 5)), float(np.percentile(boots, 95))
    sev = {m: sum(1 for r in rows if not (r["med_" + m] <= 2)) for m in ("LLM", "DIST", "NAME")}; safe = sev["LLM"] <= sev[best]
    v = "does not hold" if (not D > 0 or not safe) else ("holds" if lo > 0 and D >= DELTA else "direction only")
    return v, {"n": n, "success": s, "best_nonllm": best, "delta": D, "ci90": [lo, hi], "severe": sev, "safe": safe,
               "mechanism_names_matter": (s["LLM"] - s["LLM_OBF"]) >= DELTA * n, "per_schema": {sc: {m: sum(r[m] for r in rows if r["schema"] == sc) for m in ("LLM", "LLM_OBF", "DIST", "NAME")} for sc in SCHEMAS}}


def selftest():
    def mk(pl, pb, plo=0.5):
        r = random.Random(1); out = []
        for i in range(40):
            L_ = int(r.random() < pl); b = int(r.random() < pb)
            out.append({"cs": i % 8, "schema": SCHEMAS[i % 5], "LLM": L_, "LLM_OBF": int(r.random() < plo), "DIST": b, "NAME": 0, "med_LLM": 1.0 if L_ else 1.5, "med_DIST": 1.0 if b else 1.5, "med_NAME": 5.0})
        return out
    assert judge(mk(0.9, 0.1))[0] == "holds"
    assert judge(mk(0.3, 0.6))[0] == "does not hold"
    assert judge(mk(0.5, 0.4))[0] in ("direction only", "does not hold")
    rows = mk(0.9, 0.1); rows[0]["med_LLM"] = 9; rows[1]["med_LLM"] = 9
    for r in rows: r["med_DIST"] = 1.0
    assert judge(rows)[0] == "does not hold"
    print("Verdict self-test passed (holds, does not hold, safety line)")


def finalize(tag, model, host):
    log = lambda m: print(time.strftime("[%F %T] ") + m, flush=True)
    for _ in range(24 * 12):
        r = sh(host, f"test -f {W}/out_{tag}.jsonl.DONE && echo yes; test -f {W}/FAILED_{tag} && echo failed")
        if "yes" in r.stdout or "failed" in r.stdout: break
        time.sleep(300)
    else: log("24 hours not completed, stopped"); sys.exit(1)
    if "failed" in r.stdout: log(f"{host} reported failure, stop"); sys.exit(1)
    outp = O / f"out_{tag}.jsonl"; subprocess.run(["scp", "-q", f"{host}:{W}/out_{tag}.jsonl", str(outp)], check=True)
    T, st = {}, [0, 0, 0]
    for r in map(json.loads, open(outp)):
        _, gid, arm = r["id"].split("|"); a = r["text"].split("</think>")[-1]; st[0] += 1; st[2] += r.get("finish_reason") == "length"
        try: T.setdefault(gid, {})[arm] = L.parse(a); st[1] += 1
        except Exception: pass
    tp = O / f"transforms_{tag}.json"; tp.write_text(json.dumps(T, ensure_ascii=False))
    subprocess.run(["scp", "-q", str(tp), f"gpu-server-1:{RO}/transforms_{tag}.json"], check=True)
    r = sh("gpu-server-1", f"cd /path/to/server/work && python3 obsschema_rt_offline_v1.py eval {RO}/transforms_{tag}.json {tag} > {RO}/eval_{tag}.log 2>&1; echo rc=$?", timeout=7200); log("gpu-server-1 evaluation " + r.stdout.strip())
    subprocess.run(["scp", "-q", f"gpu-server-1:{RO}/eval_{tag}.json", str(O / f"eval_{tag}.json")], check=True)
    E = json.load(open(O / f"eval_{tag}.json")); G = {g["id"]: g for g in json.load(open(O / "groups.json"))["groups"]}; rows = []
    for gid, res in E["results"].items():
        g = G[int(gid)]; med = {m: float(np.nanmedian([x.get(m, np.nan) for x in res.values()])) if any(m in x for x in res.values()) else float("nan") for m in ("LLM", "LLM_OBF", "DIST", "NAME", "ORACLE")}
        rows.append({"id": int(gid), "cs": f"{g['scen']}|{g['draw']}", "schema": g["schema"], **{m: int(med[m] <= 1.2) for m in med}, **{"med_" + m: med[m] for m in med}})
    v, info = judge(rows); res = {"verdict": v if len(rows) == 40 else "incomplete, not adjudicated", **info, "parse": {"n": st[0], "parsed": st[1], "hit_limit": st[2]}, "rows": rows}
    (O / f"judge_{tag}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    sc = info["success"]
    basis = (f"{model}: real names success {sc['LLM']}/{info['n']}, shuffled field names {sc['LLM_OBF']}/{info['n']}, distribution matching {sc['DIST']}, name matching {sc['NAME']}; Δ (real names minus the better statistical method {info['best_nonllm']}, by group proportion) {info['delta']:+.3f}, 90% interval [{info['ci90'][0]:+.3f}, {info['ci90'][1]:+.3f}]; severe failure (median ratio over 2) {json.dumps(info['severe'], ensure_ascii=False)}; report only: by schema {json.dumps(info['per_schema'], ensure_ascii=False)}; mechanism reading (real names at least 10 groups more than shuffled) {'holds' if info['mechanism_names_matter'] else 'does not hold'}; parsing {res['parse']}.")
    log(f"{tag} {res['verdict']} {basis}")
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"tag": tag, "verdict": res["verdict"], **{k: info[k] for k in ("success", "delta", "ci90", "severe", "per_schema")}}, ensure_ascii=False), "--artifact", str(O / f"judge_{tag}.json"))
    if tag == "rt_r1_32b" and res["verdict"] in ("holds", "direction only", "does not hold"):
        ex("conclude", "--id", ID, "--verdict", res["verdict"], "--vs-criteria", "Criterion as pre-registered (confirmatory template)." + basis, "--basis", basis,
           "--limitations", "Single open-source reasoning model with four-bit quantization, one sample per group (temperature 0.6); offline evaluation uses step-by-step replay of the challenge baseline, not closed loop; rt_getstats only borrows the getStats naming and unit conventions.", "--next", "")
    else: ex("note", "--id", ID, f"Report only arm {tag}: {res['verdict']} (computed by the same criterion as the primary arm, no conclusion drawn). {basis}")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "prep": prep()
    elif c == "finalize": finalize(sys.argv[2], sys.argv[3], sys.argv[4])
    elif c == "judge": selftest()
