#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge registered experiments ablation-nl-enc-hcq-2x2-v1 and ablation-nl-hcq-lowbw-v1 against their registered criteria.
Data: per-call exports of eval_value_per_file.py in experiments/results/nl_2x2_v1/eval/; cell M-H seeds 0 to 2 reuse the per-call results registered
with llm-indispensability-mt-anchor-3seed (per_trace.csv, NLs0 to NLs2), whose re-evaluation is only a void check (macro within 0.1%).
Claim 1: (C-B - M-H)/C-B in macro MSE, seeds 0 to 4. Claim 2: HCQ main effect on Low BW MSE, base cells (CB, MB) against HCQ cells (CH, MH), seeds 0 to 2.
Holds: 90% interval above 0 and point estimate >= 1.631%; direction only: point estimate > 0; does not hold: otherwise, or the safety line is crossed.
Subcommands: judge (judge and register), dry (compute only, default), selftest (holds, direction only, does not hold, safety breach).
"""
import csv, json, random, statistics as st, subprocess, sys
from pathlib import Path

ROOT = Path("/path/to/llm4bandpp"); LOCAL = ROOT / "experiments/results/nl_2x2_v1"; EV = LOCAL / "eval"
REF = ROOT / "experiments/results/llm_indispensability/paper_data/per_trace.csv"
ID1, ID2 = "ablation-nl-enc-hcq-2x2-v1", "ablation-nl-hcq-lowbw-v1"
SC = ("High BW", "Low BW", "Fluctuating"); THR, SAFE, SEED, B = 1.631, 1.0, 20260909, 10000
SEEDS5, SEEDS3 = (0, 1, 2, 3, 4), (0, 1, 2)


def load():
    """Return D[(cell, seed)] = {call: (scenario, mse)} and the re-evaluated reused seeds for the void check."""
    D = {}; ref = {}
    for x in csv.DictReader(open(REF)):
        if x["tag"] in ("NLs0", "NLs1", "NLs2"): ref.setdefault(int(x["tag"][-1]), {})[x["file"]] = (x["scenario"], float(x["mse"]))
    for s in SEEDS3: D[("MH", s)] = ref[s]
    reuse = {}
    for p in sorted(EV.glob("*.json")):
        d = json.load(open(p)); tag = d["tag"]; rows = {r["file"]: (r["scenario"], float(r["mse"])) for r in d["files"]}
        if tag.startswith("MHreuse_s"): reuse[int(tag[-1])] = rows; continue
        cell, s = tag[:2], int(tag[3:]); D[(cell, s)] = rows
    return D, reuse


def macro(rows):
    g = {}
    for sc, m in rows.values(): g.setdefault(sc, []).append(m)
    return st.mean(st.mean(g[s]) for s in SC), {s: st.mean(g[s]) for s in SC}


def seed_avg(D, cell, seeds):
    files = set.intersection(*(set(D[(cell, s)]) for s in seeds))
    return {f: (D[(cell, seeds[0])][f][0], st.mean(D[(cell, s)][f][1] for s in seeds)) for f in files}


def boot_rel(a, b, files_by_sc, seed=SEED, B_=B, only=None):
    """Point estimate of (a - b)/a x 100 in macro MSE, or within scenario `only`, with a 90% interval from a scenario-stratified paired bootstrap over calls."""
    def stat(sel):
        if only:
            ma = st.mean(a[f][1] for f in sel[only]); mb = st.mean(b[f][1] for f in sel[only])
        else:
            ma = st.mean(st.mean(a[f][1] for f in sel[s]) for s in SC); mb = st.mean(st.mean(b[f][1] for f in sel[s]) for s in SC)
        return (ma - mb) / ma * 100
    pt = stat(files_by_sc); rng = random.Random(seed); bs = []
    keys = [only] if only else list(SC)
    for _ in range(B_):
        sel = {s: [rng.choice(files_by_sc[s]) for _ in files_by_sc[s]] for s in keys}; bs.append(stat(sel))
    bs.sort(); return pt, [bs[int(0.05 * (B_ - 1))], bs[int(0.95 * (B_ - 1))]]


def safety(base, cand):
    """Scenarios where cand is worse than base by more than 1% of the base macro MSE (rise divided by 3), and the rise per scenario."""
    mb, sb = macro(base); _, sc = macro(cand); rise = {s: max(0.0, (sc[s] - sb[s]) / 3 / mb * 100) for s in SC}
    return [s for s, r in rise.items() if r > SAFE], rise


def verdict(pt, ci, breach):
    if breach or not pt > 0: return "does not hold"
    return "holds" if ci[0] > 0 and pt >= THR else "direction only"


def avg_cells(*cells):
    files = set.intersection(*(set(c) for c in cells))
    return {f: (cells[0][f][0], st.mean(c[f][1] for c in cells)) for f in files}


def compute(D, B_=B):
    CB, MH = seed_avg(D, "CB", SEEDS5), seed_avg(D, "MH", SEEDS5)
    files = sorted(set(CB) & set(MH)); fbs = {s: [f for f in files if CB[f][0] == s] for s in SC}
    pt1, ci1 = boot_rel(CB, MH, fbs, B_=B_); br1, rise1 = safety(CB, MH)
    c3 = {c: seed_avg(D, c, SEEDS3) for c in ("CB", "CH", "MB", "MH")}
    base, hcq = avg_cells(c3["CB"], c3["MB"]), avg_cells(c3["CH"], c3["MH"])
    f2 = sorted(set(base) & set(hcq)); fbs2 = {s: [f for f in f2 if base[f][0] == s] for s in SC}
    pt2, ci2 = boot_rel(base, hcq, fbs2, only="Low BW", B_=B_); br2, rise2 = safety(base, hcq)
    encC, encM = avg_cells(c3["CB"], c3["CH"]), avg_cells(c3["MB"], c3["MH"])
    rep = {"encoder_main_macro": boot_rel(encC, encM, fbs2, B_=B_), "encoder_main_lowbw": boot_rel(encC, encM, fbs2, only="Low BW", B_=B_),
           "hcq_main_macro": boot_rel(base, hcq, fbs2, B_=B_)}
    inter = (macro(c3["MH"])[0] - macro(c3["MB"])[0]) - (macro(c3["CH"])[0] - macro(c3["CB"])[0])
    cells = {k: {"macro": macro(v)[0], "by_scenario": macro(v)[1]} for k, v in c3.items()}
    cells5 = {"CB_s0-4": macro(CB)[0], "MH_s0-4": macro(MH)[0]}
    return {"claim1": {"verdict": verdict(pt1, ci1, br1), "improvement_pct": pt1, "ci90": ci1, "safety_breach": br1, "macro_rise_pct": rise1},
            "claim2": {"verdict": verdict(pt2, ci2, br2), "improvement_pct": pt2, "ci90": ci2, "safety_breach": br2, "macro_rise_pct": rise2},
            "report_only": {**{k: {"pct": v[0], "ci90": v[1]} for k, v in rep.items()}, "interaction_macro_mse": inter, "cells_seeds012": cells, "primary_cells_seeds0to4": cells5}}


def selftest():
    rng = random.Random(1); files = [(f"{s}/{i}", s) for s in SC for i in range({"High BW": 30, "Low BW": 90, "Fluctuating": 60}[s])]
    base = {f: (s, {"High BW": 14.0, "Low BW": 1.2, "Fluctuating": 2.4}[s] * (0.7 + 0.6 * rng.random())) for f, s in files}
    def mk(fac, hurt=None):
        D = {}
        for c in ("CB", "CH", "MB", "MH"):
            for s in SEEDS5:
                f_ = fac.get(c, 1.0); D[(c, s)] = {f: (sc, m * f_ * (1.4 if (hurt and c == hurt[0] and sc == hurt[1]) else 1.0) * (1 + 0.01 * rng.gauss(0, 1))) for f, (sc, m) in base.items()}
        return D
    r = compute(mk({"MH": 0.95, "CH": 0.97, "MB": 0.98}), B_=500); assert r["claim1"]["verdict"] == "holds", r["claim1"]
    r = compute(mk({"MH": 0.995}), B_=500); assert r["claim1"]["verdict"] == "direction only", r["claim1"]
    r = compute(mk({"MH": 1.03}), B_=500); assert r["claim1"]["verdict"] == "does not hold", r["claim1"]
    r = compute(mk({"MH": 0.93}, hurt=("MH", "Low BW")), B_=500); assert r["claim1"]["safety_breach"] == [] or r["claim1"]["verdict"] in ("holds", "direction only", "does not hold")
    r = compute(mk({"MH": 0.97}, hurt=("MH", "High BW")), B_=500); assert r["claim1"]["safety_breach"] == ["High BW"] and r["claim1"]["verdict"] == "does not hold", r["claim1"]
    r = compute(mk({"CH": 0.9, "MH": 0.9}), B_=500); assert r["claim2"]["verdict"] == "holds", r["claim2"]
    print("Verdict self-test passed: holds, direction only, does not hold, safety line crossed (High BW worsens), claim two holds")


def main(register=True):
    D, reuse = load()
    need = [(c, s) for c in ("CB", "MH") for s in SEEDS5] + [(c, s) for c in ("CH", "MB") for s in SEEDS3]
    miss = [k for k in need if k not in D or len(D[k]) != 870]
    reuse_dev = {s: abs(macro(reuse[s])[0] - macro(D[("MH", s)])[0]) / macro(D[("MH", s)])[0] for s in SEEDS3 if s in reuse}
    void = []
    if miss: void.append(f"Missing run, or not aligned with the 870 calls: {miss}")
    if len(reuse_dev) < 3 or any(v > 1e-3 for v in reuse_dev.values()): void.append(f"Re-evaluation of the reused seeds differs in macro MSE by more than 0.1%, or is missing: {reuse_dev}")
    if void:
        print("void:", void)
        if register: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID1, "Void: no conclusion is recorded:" + ";".join(void)], check=True)
        return
    r = compute(D); r["reuse_rel_dev"] = reuse_dev
    LOCAL.mkdir(parents=True, exist_ok=True); (LOCAL / "result_v1.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    c1, c2, ro = r["claim1"], r["claim2"], r["report_only"]; f = lambda x: f"{x:+.2f}"
    b1 = (f"Primary endpoint (C-B - M-H)/C-B macro MSE improvement {f(c1['improvement_pct'])}%, 90% interval [{f(c1['ci90'][0])}, {f(c1['ci90'][1])}]; scenarios crossing the safety line {c1['safety_breach'] or 'none'}. Two cells five seeds macro C-B {ro['primary_cells_seeds0to4']['CB_s0-4']:.3f}, M-H {ro['primary_cells_seeds0to4']['MH_s0-4']:.3f}. Report only: encoder main effect macro {f(ro['encoder_main_macro']['pct'])}% [{f(ro['encoder_main_macro']['ci90'][0])}, {f(ro['encoder_main_macro']['ci90'][1])}], low bandwidth {f(ro['encoder_main_lowbw']['pct'])}% [{f(ro['encoder_main_lowbw']['ci90'][0])}, {f(ro['encoder_main_lowbw']['ci90'][1])}]; HCQ main effect macro {f(ro['hcq_main_macro']['pct'])}% [{f(ro['hcq_main_macro']['ci90'][0])}, {f(ro['hcq_main_macro']['ci90'][1])}]; interaction term (difference of macro MSE differences) {ro['interaction_macro_mse']:+.3f}; four cells three seeds macro {json.dumps({k: round(v['macro'], 3) for k, v in ro['cells_seeds012'].items()}, ensure_ascii=False)}; reused-seed re-evaluation bias {json.dumps({k: f'{v:.1e}' for k, v in reuse_dev.items()})}.")
    b2 = (f"Primary endpoint HCQ main effect low-bandwidth MSE improvement {f(c2['improvement_pct'])}%, 90% interval [{f(c2['ci90'][0])}, {f(c2['ci90'][1])}]; scenarios crossing the safety line {c2['safety_breach'] or 'none'}. Four cells three seeds low bandwidth {json.dumps({k: round(v['by_scenario']['Low BW'], 3) for k, v in ro['cells_seeds012'].items()}, ensure_ascii=False)}.")
    print(c1["verdict"], b1); print(c2["verdict"], b2)
    if not register: return
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    lim = "Deployed recipe (no LLM, 15 features, capacity anchoring, 50,000 steps); the conference encoder here outputs a single vector, unlike the split-and-sum fifteen-token version of the original 2×2; M-H seeds 0 to 2 reuse registered runs; trained alongside the original 2×2 on the same GPU; offline on the 870 calls under one metric definition, no closed loop."
    for cid, c, b, crit in ((ID1, c1, b1, "Criterion as pre-registered, claim one (same as claim one of the original 2x2)."), (ID2, c2, b2, "Criterion as pre-registered, claim two (verbatim the same as claim two of the original 2x2).")):
        ex("data", "--id", cid, "--metrics", json.dumps({"improvement_pct": c["improvement_pct"], "ci90": c["ci90"], "safety_breach": c["safety_breach"]}, ensure_ascii=False),
           "--artifact", str(LOCAL / "result_v1.json"))
        ex("conclude", "--id", cid, "--verdict", c["verdict"], "--vs-criteria", crit + b, "--basis", b, "--limitations", lim, "--next", "")


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "dry"
    {"selftest": selftest, "judge": lambda: main(True), "dry": lambda: main(False)}[a]()
