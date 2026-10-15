#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Value-rule baselines on real software telemetry: can a baseline infer counter differencing from the observed values?
Reuses the 24 runs and all scoring functions of realtel-e2e-v1 (realtel_e2e_v1.py); the tcp_info byte count (k=2) is dropped, leaving 42 cells.
Designer: DEEPSEEK mappings as in realtel-e2e-v1 (first field order). Baselines: the seven non-LLM matchers and the same hosted model as a generic schema matcher (GENERIC, spec7 set of llm_schema_match_v1), each keeping its chosen field.
diff is set from values: true if the field's snapshot series in that run never decreases and grows at least once; scale keeps the original rule.
Primary endpoint: delta = designer correct share - best value-rule baseline, run-block bootstrap, 90% interval; holds at lower bound > 0 and delta >= 0.15, direction only if delta > 0.
Usage: e2e_valuerule_v1.py judge [--selftest]
"""
import json, random, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/realtel_e2e")); sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_e2e_v1 as E  # noqa: E402
M = E.M
OUT = ROOT / "experiments/results/realtel_e2e_valuerule_v1"; ID = "realtel-e2e-valuerule-v1"; DELTA = 0.15; SEED = 20261007; B = 5000
GEN = ROOT / "experiments/results/llm_schema_match_v1/llm_generic.jsonl"; DROP = {("tcpinfo", 2)}


def series(W, name):
    """Return a field's numeric snapshot values over a run in time order, taken from r0 and r1 of each window; non-numeric values are skipped."""
    xs = []
    for w in W:
        for side in ("r0", "r1"):
            r = w.get(side)
            if r is None: continue
            v = r.get(name)
            if isinstance(v, (int, float)) and not isinstance(v, bool): xs.append(v)
    return xs


def monotone(xs):
    return len(xs) >= 3 and all(b >= a for a, b in zip(xs, xs[1:])) and xs[-1] > xs[0]


def value_rule(a, W):
    """Replace the diff flag of a (field, diff, scale) adapter with the value-based rule; field and scale stay."""
    if a is None: return None
    name, _, sc = a; return (name, monotone(series(W, name)), sc)


def generic_adapters():
    out = {}
    for j in map(json.loads, open(GEN)):
        if j.get("set") != "spec7" or j.get("pres") != 0 or not j.get("ok"): continue
        out[j["source"]] = j["mapping"]
    res = {}
    for e, s in E.SRC.items():
        mp = out.get(s); fl = M.TEST[s]["fields"]
        res[e] = {k: (None if (mp is None or mp[k] is None) else (fl[mp[k]["source"]][0], bool(mp[k]["diff"]), float(mp[k]["scale"]))) for k in range(15)}
    return res


def judge_vs(R, best_pool, seed=SEED, B_=B):
    rate = lambda rows: sum(x["ok"] for x in rows) / len(rows)
    best = max(best_pool, key=lambda m: rate(R[m])); runs = sorted({x["run"] for x in R["DEEPSEEK"]})
    def d(sel):
        a = [x for r in sel for x in R["DEEPSEEK"] if x["run"] == r]; b = [x for r in sel for x in R[best] if x["run"] == r]; return rate(a) - rate(b)
    D = d(runs); rng = random.Random(seed); bs = sorted(d([rng.choice(runs) for _ in runs]) for _ in range(B_)); lo, hi = bs[int(0.05 * B_)], bs[int(0.95 * B_) - 1]
    v = "does not hold" if not D > 0 else ("holds" if lo > 0 and D >= DELTA else "direction only")
    return v, {"delta": D, "ci90": [lo, hi], "best": best, "rate": {m: rate(r) for m, r in R.items()}}


def selftest():
    assert monotone([1, 2, 2, 5]) and not monotone([5, 5, 5]) and not monotone([1, 3, 2]) and not monotone([1, 2])
    W = [{"r0": {"x": 100, "y": 7}, "r1": {"x": 200, "y": 5}}, {"r0": {"x": 200, "y": 5}, "r1": {"x": 310, "y": 6}}]
    assert value_rule(("x", False, 1.0), W) == ("x", True, 1.0) and value_rule(("y", True, 2.0), W) == ("y", False, 2.0) and value_rule(None, W) is None
    W2 = [{"r0": None, "r1": {"p": 10}}, {"r0": None, "r1": {"p": 12}}, {"r0": None, "r1": {"p": 15}}]
    assert value_rule(("p", False, 1.0), W2) == ("p", True, 1.0)
    mk = lambda p: [{"run": f"r{i % 21}", "ok": int(random.Random(i * 13 + int(p * 100)).random() < p), "err": 0.0, "k": 1} for i in range(42)]
    assert judge_vs({"DEEPSEEK": mk(1.0), "A": mk(0.5)}, ["A"], B_=1000)[0] == "holds"
    assert judge_vs({"DEEPSEEK": mk(0.9), "A": mk(0.85)}, ["A"], B_=1000)[0] in ("direction only", "does not hold")
    assert judge_vs({"DEEPSEEK": mk(0.5), "A": mk(0.9)}, ["A"], B_=1000)[0] == "does not hold"
    g = generic_adapters(); assert set(g) == set(E.SRC) and all(len(v) == 15 for v in g.values())
    print("Self-test passed: monotonicity test, value rule replacing the diff flag, holds, does not hold; the generic matcher has complete mappings for all four sources")


def main():
    A = E.adapters(); A["GENERIC"] = generic_adapters(); base = ["NAME", "TFIDF", "COMA", "CUPID", "SF", "BGE", "MPNET"]
    assert all(b in A for b in base), sorted(A)
    R = {m: [] for m in ["DEEPSEEK", "GENERIC"] + base + [b + "+VAL" for b in base + ["GENERIC"]]}; detail = {}
    for d in sorted((E.OUT / "runs").iterdir()):
        if not d.is_dir() or not (d / "OK").exists(): continue
        src = d.name.split("_")[0]; W = E.LOAD[src](d)
        for k in E.FEATS[src]:
            if (src, k) in DROP: continue
            for m in ["DEEPSEEK", "GENERIC"] + base:
                a = A[m][src].get(k); e, ok = E.unit_err(W, k, a); R[m].append({"run": d.name, "k": k, "src": src, "ok": int(ok), "err": e})
                if m != "DEEPSEEK":
                    av = value_rule(a, W); ev, okv = E.unit_err(W, k, av); R[m + "+VAL"].append({"run": d.name, "k": k, "src": src, "ok": int(okv), "err": ev})
                    detail.setdefault(d.name, {}).setdefault(k, {})[m] = {"orig": [a, int(ok)], "val": [av, int(okv)]}
    n = {m: len(r) for m, r in R.items()}; assert len(set(n.values())) == 1 and n["DEEPSEEK"] == 42, n
    v, m = judge_vs(R, [b + "+VAL" for b in base + ["GENERIC"]])
    by_src = {mm: {s: (lambda rows: round(sum(x["ok"] for x in rows) / len(rows), 3) if rows else None)([x for x in R[mm] if x["src"] == s]) for s in E.SRC} for mm in R}
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump({"verdict": v, **m, "by_source": by_src, "detail": detail, "units": R}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1, default=str)
    rt = m["rate"]; f = lambda keys: ",".join(f"{k} {rt[k]:.3f}" for k in keys)
    basis = (f"24 runs, 42 cells: designer judged correct {rt['DEEPSEEK']:.3f}; numeric-rule control {f([b + '+VAL' for b in base + ['GENERIC']])} (best {m['best']}); Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]. Report only: original rules {f(base + ['GENERIC'])}; per-source judged correct {json.dumps({k: by_src[k] for k in ['DEEPSEEK', m['best']]}, ensure_ascii=False)}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"delta": m["delta"], "ci90": m["ci90"], "best": m["best"], "rate": rt}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (Delta lower bound greater than 0 and not less than 0.15, the same as realtel-e2e-v1)." + basis, "--basis", basis,
       "--limitations", "Reuses the 24 runs of realtel-e2e-v1 (netem on loopback); differencing is inferred from the values of the same run, which favours the baseline; the coefficients follow the original rule; the unit-aware matcher itself does not do differencing and infers coefficients from the training window, so it does not apply directly to per-second real telemetry and is not listed separately.",
       "--next", "")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
