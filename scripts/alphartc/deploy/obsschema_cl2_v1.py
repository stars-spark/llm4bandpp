#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch obsschema-closedloop-v2: closed-loop check of the adapter for a new client interface.
Evidence windows es_1 to es_3 run the true mapping once each; windows sd_1 to sd_8 run 17 conditions each (true mapping, and four held-out synthetic schemas test_g to test_j with no adapter, LLM designer, distribution match, name match). Main endpoint: delta = best statistical method's mean deviation |U(method) - U(correct)| minus the LLM's, window-block bootstrap; holds if the 90% lower bound is above 0 and delta is at least 3.
Usage: obsschema_cl2_v1.py evjobs OUT | jobs OUT | judge [--selftest]
"""
import json, random, statistics as st, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/obsschema-closedloop-v2"); ID = "obsschema-closedloop-v2"
P = ROOT / "scripts/alphartc/deploy/profiles/obsschema_cl2"; ARM = "arm_default_schema"
WINS = [f"sd_{i}" for i in range(1, 9)]; SCHEMAS = ["test_g", "test_h", "test_i", "test_j"]; METHODS = ["NONE", "LLM", "DIST", "NAME"]; DELTA, SEVERE = 3.0, 10.0
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402


def spec(name, J, media):
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1" if media else "0"
    return {"name": name, "K": str(K), "log": "/path/to/llm4bandpp/logs/obsschema_cl2_v1.log", "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v10.sh"),
            "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py", "quality_args": ["--ocr-jobs", "6", "--vmaf-threads", "6"], "source": "testmedia/qoe_labeled_medium_320x240.yuv",
            "media": media, "vmaf_workers": 2, "max_pending": 4, "stagger_s": 7, "common_env": env, "machine": "aliyun-tb", "phases": [{"name": name, "pairs": [1, 2], "vmaf": "async"}],
            "jobs": [dict(j, phase=name) for j in J]}


def evjobs(out):
    J = [{"cond": f"{w}__CLEAN", "arm": ARM, "profile": str(P / f"{w}.profile"), "env": {}} for w in ("es_1", "es_2", "es_3")]
    Path(out).write_text(json.dumps(spec("ev", J, False), ensure_ascii=False, indent=1)); print("evidence task", len(J))


def jobs(out):
    M = json.load(open(K / "maps.json"))["schemas"]; J = []
    for w in WINS:
        conds = ["CLEAN"] + [f"{s}__{m}" for s in SCHEMAS for m in METHODS]; random.Random(f"obsschema_cl2_v1/{w}").shuffle(conds)
        for c in conds:
            env = {}
            if c != "CLEAN":
                s, m = c.split("__"); mp = M[s][m] if m != "NONE" else None
                env = {"STALENESS_OBS_SCHEMA": s, "STALENESS_OBS_MAP": "IDENTITY" if mp is None else json.dumps(mp, separators=(",", ":"))}
            J.append({"cond": f"{w}__{c}", "arm": ARM, "profile": str(P / f"{w}.profile"), "env": env})
    Path(out).write_text(json.dumps(spec("main", J, True), ensure_ascii=False, indent=1)); print("jobs:", len(J))


def judge(U, seed=20261005, B=5000):
    """Return (verdict, metrics); U maps (window, condition) to utility."""
    dev = {m: {} for m in METHODS}; severe = {m: 0 for m in METHODS}; n = {m: 0 for m in METHODS}
    for s in SCHEMAS:
        for w in WINS:
            if (w, "CLEAN") not in U: continue
            for m in METHODS:
                if (w, f"{s}__{m}") in U:
                    d = U[(w, f"{s}__{m}")] - U[(w, "CLEAN")]; dev[m][(s, w)] = abs(d); severe[m] += d < -SEVERE; n[m] += 1
    mean_dev = {m: (st.mean(dev[m].values()) if dev[m] else float("nan")) for m in METHODS}
    best = min(("DIST", "NAME"), key=lambda m: mean_dev[m])
    units = [u for u in dev["LLM"] if u in dev[best]]
    delta_of = lambda us: st.mean(dev[best][u] - dev["LLM"][u] for u in us) if us else float("nan")
    D = delta_of(units); rng = random.Random(seed); ws = sorted({w for _, w in units}); boots = []
    for _ in range(B):
        pick = [rng.choice(ws) for _ in ws]; us = [u for w in pick for u in units if u[1] == w]; boots.append(delta_of(us))
    lo, hi = float(np.percentile(boots, 5)), float(np.percentile(boots, 95)); safe = severe["LLM"] == 0
    if D <= 0 or not safe: v = "does not hold"
    elif lo > 0 and D >= DELTA: v = "holds"
    else: v = "direction only"
    return v, {"delta": D, "ci90": [lo, hi], "best_nonllm": best, "mean_dev": mean_dev, "severe_loss": severe, "n_units": n, "llm_safe": safe}


def selftest():
    def mk(llm_dev, cmp_dev, llm_sev=False, seed=0):
        r = random.Random(seed); U = {}
        for w in WINS:
            U[(w, "CLEAN")] = 85 + r.gauss(0, 2)
            for s in SCHEMAS:
                U[(w, f"{s}__NONE")] = 60; U[(w, f"{s}__LLM")] = U[(w, "CLEAN")] + r.choice([-1, 1]) * llm_dev
                U[(w, f"{s}__DIST")] = U[(w, "CLEAN")] - cmp_dev + r.gauss(0, 1); U[(w, f"{s}__NAME")] = U[(w, "CLEAN")] + cmp_dev * 1.2
        if llm_sev: U[(WINS[0], "test_g__LLM")] = U[(WINS[0], "CLEAN")] - 15
        return U
    assert judge(mk(0.5, 8))[0] == "holds"
    assert judge(mk(0.5, 1.5))[0] == "direction only"
    assert judge(mk(4, 2))[0] == "does not hold"
    assert judge(mk(0.5, 8, llm_sev=True))[0] == "does not hold"
    print("Verdict self-test passed (holds, direction only, two kinds of does not hold)")


def main():
    import cl_condition_audit_v1 as CA
    au = CA.audit(K, [K / "jobs_ev.json", K / "jobs_main.json"], use_monitor=False); au_txt = CA.summary_text(au)
    if au["hard_fail"]:
        (K / "AUDIT_FAILED").write_text(json.dumps(au["hard_fail"], ensure_ascii=False)); print("condition audit failed; no verdict", au_txt)
        subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, "condition audit failed; no verdict:" + au_txt + " " + json.dumps(au["hard_fail"], ensure_ascii=False)[:1500]], check=True); return
    U, Q, pairU = {}, {}, {}
    for dd in K.glob("sd_*__*"):
        w, c = dd.name.split("__", 1); js = dd / f"{ARM}__{w}__d0__r1.json"
        if js.is_file() and not list(dd.glob("invalid_*")):
            U[(w, c)] = json.load(open(js))["network"]["utility"]; q = dd / f"quality_{ARM}__{w}__d0__r1.json"
            if q.is_file(): Q[(w, c)] = json.load(open(q)).get("vmaf")
            if c == "CLEAN" and (dd / "run_meta.json").is_file(): pairU.setdefault(str(json.load(open(dd / "run_meta.json"))["pair"]), []).append(U[(w, c)])
    v, m = judge(U); M = json.load(open(K / "maps.json"))["schemas"]
    meanU = {k: (st.mean([U[(w, f"{s}__{k}")] for s in SCHEMAS for w in WINS if (w, f"{s}__{k}") in U]) if k != "CLEAN" else st.mean([U[(w, "CLEAN")] for w in WINS if (w, "CLEAN") in U])) for k in ["CLEAN"] + METHODS}
    meanQ = {k: (lambda xs: st.mean(xs) if xs else None)([Q[(w, c)] for (w, c) in Q if (c == "CLEAN" if k == "CLEAN" else c.endswith("__" + k))]) for k in ["CLEAN"] + METHODS}
    res = {"verdict": v, **m, "mean_U": meanU, "mean_vmaf": meanQ, "mapping_correct": {s: M[s]["correct"] for s in SCHEMAS}, "clean_U_by_pair": pairU, "condition_audit": au_txt, "n_runs": len(U), "n_expected": len(WINS) * 17}
    (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    f1 = lambda x: "none" if x is None else f"{x:.1f}"
    basis = (f"Primary endpoint: mean deviation from the true mapping LLM {m['mean_dev']['LLM']:.2f}, distribution matching {m['mean_dev']['DIST']:.2f}, name matching {m['mean_dev']['NAME']:.2f}, not adapted {m['mean_dev']['NONE']:.2f}; Δ ({m['best_nonllm']} minus LLM) {m['delta']:+.2f}, 90% interval [{m['ci90'][0]:+.2f}, {m['ci90'][1]:+.2f}]; safety line (number of cells where the LLM is more than 10 points below the true mapping) {m['severe_loss']['LLM']}. Report only: number of cells more than 10 points below the true mapping {json.dumps(m['severe_loss'], ensure_ascii=False)}; mean utility {json.dumps({k: round(x, 1) for k, x in meanU.items()}, ensure_ascii=False)}; mean quality {json.dumps({k: (round(x, 1) if x else None) for k, x in meanQ.items()}, ensure_ascii=False)}; mappings correct field by field {json.dumps(res['mapping_correct'], ensure_ascii=False)}; valid runs {len(U)}/{len(WINS) * 17}.{au_txt}")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: res[k] for k in ("delta", "ci90", "best_nonllm", "mean_dev", "severe_loss", "mean_U", "mean_vmaf")}, ensure_ascii=False), "--artifact", str(K / "result_v1.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmation, the relaxed template)." + basis, "--basis", basis,
       "--limitations", "Eight Norwegian 3G windows, one run per condition; the four held-out schemas differ only in order and units; the evidence calls run the reference collector with the challenge baseline; the cloud testbed runs two container pairs in parallel.", "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "evjobs": evjobs(sys.argv[2])
    elif c == "jobs": jobs(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
