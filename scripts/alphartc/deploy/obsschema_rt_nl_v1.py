#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch obsschema-closedloop-nl-v1: the adapter closed loop with the no-LLM multi-scale estimator and probing envelope v6 downstream (arm_nl_schema).
Windows, conditions, frozen maps and the decision function (obsschema_cl2_v1.judge) are those of obsschema-closedloop-llm4bandpp-v2, the batch with the one-token LLM variant downstream; synthetic schemas test_g to test_j plus rt_getstats.
Usage: obsschema_rt_nl_v1.py smoke OUT | maps | jobs OUT | judge [--selftest]
"""
import json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/obsschema-closedloop-nl-v1"); ID = "obsschema-closedloop-nl-v1"
K_V1 = Path("/path/to/testbed/results/obsschema-closedloop-llm4bandpp-v2"); MAPS_SHA = "5a22ce3e0dfca21c7ed1ddb7fb5099dd767421ae9f3251aa4f4a9af5990198ea"
P = ROOT / "scripts/alphartc/deploy/profiles/obsschema_rt"; PE = ROOT / "scripts/alphartc/deploy/profiles/obsschema_cl2"; ARM = "arm_nl_schema"
WINS = [f"rt_{i}" for i in range(1, 9)]; SCHEMAS = ["test_g", "test_h", "test_i", "test_j", "rt_getstats"]; METHODS = ["NONE", "LLM", "DIST", "NAME"]
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402
import obsschema_cl2_v1 as C  # noqa: E402
C.WINS, C.SCHEMAS = WINS, SCHEMAS


def spec(name, J, pairs):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": name, "K": str(K / name) if name == "smoke" else str(K), "log": str(ROOT / "logs/obsschema_rt_nl_v1.log"),
            "runner": str(ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v17.sh"), "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py",
            "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"], "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": (2 if name == "smoke" else 1), "max_pending": 3,
            "stagger_s": 7, "common_env": env, "phases": [{"name": name, "pairs": pairs, "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in J]}


def smoke(out):
    """Write smoke jobs on evidence window es_1 (not counted): one correct-interface run and one rt_getstats run without adapter, to check validity, startup log and timing."""
    J = [{"cond": "es_1__CLEAN", "arm": ARM, "profile": str(PE / "es_1.profile"), "env": {}},
         {"cond": "es_1__rt_getstats__NONE", "arm": ARM, "profile": str(PE / "es_1.profile"), "env": {"STALENESS_OBS_SCHEMA": "rt_getstats", "STALENESS_OBS_MAP": "IDENTITY"}}]
    Path(out).write_text(json.dumps(spec("smoke", J, [1, 2]), ensure_ascii=False, indent=1)); print("smoke jobs:", len(J))


def maps():
    """Copy the frozen maps into this batch directory unchanged, with no new LLM call, and stop on a hash mismatch."""
    import hashlib, shutil
    K.mkdir(parents=True, exist_ok=True)
    if not (K / "maps.json").is_file(): shutil.copy(K_V1 / "maps.json", K / "maps.json")
    h = hashlib.sha256((K / "maps.json").read_bytes()).hexdigest()
    if h != MAPS_SHA: raise SystemExit(f"maps.json hash {h} does not match the v1 frozen mapping")
    print("mapping follows v1, hashes match", h)


def jobs(out):
    M = json.load(open(K / "maps.json"))["schemas"]; J = []
    for w in WINS:
        conds = ["CLEAN"] + [f"{s}__{m}" for s in SCHEMAS for m in METHODS]; random.Random(f"obsschema_rt_v1/{w}").shuffle(conds)
        for c in conds:
            env = {}
            if c != "CLEAN":
                s, m = c.split("__"); mp = M[s][m] if m != "NONE" else None
                env = {"STALENESS_OBS_SCHEMA": s, "STALENESS_OBS_MAP": "IDENTITY" if mp is None else json.dumps(mp, separators=(",", ":"))}
            J.append({"cond": f"{w}__{c}", "arm": ARM, "profile": str(P / f"{w}.profile"), "env": env})
    Path(out).write_text(json.dumps(spec("main", J, [1, 2]), ensure_ascii=False, indent=1)); print("jobs:", len(J))


def main():
    import cl_condition_audit_v1 as CA
    au = CA.audit(K, [K / "jobs_main.json"]); au_txt = CA.summary_text(au)
    if au["hard_fail"]:
        (K / "AUDIT_FAILED").write_text(json.dumps(au["hard_fail"], ensure_ascii=False)); print("condition audit failed; no verdict", au_txt)
        subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, "condition audit failed; no verdict:" + au_txt + " " + json.dumps(au["hard_fail"], ensure_ascii=False)[:1500]], check=True); return
    U, Q, pairU, CP = {}, {}, {}, []
    for dd in K.glob("rt_*__*"):
        w, c = dd.name.split("__", 1); js = dd / f"{ARM}__{w}__d0__r1.json"
        if js.is_file() and not list(dd.glob("invalid_*")):
            j = json.load(open(js)); U[(w, c)] = j["network"]["utility"]; CP.append(j["decisions"]["compute_p95_ms"]); q = dd / f"quality_{ARM}__{w}__d0__r1.json"
            if q.is_file(): Q[(w, c)] = json.load(open(q)).get("vmaf")
            if c == "CLEAN" and (dd / "run_meta.json").is_file(): pairU.setdefault(str(json.load(open(dd / "run_meta.json"))["pair"]), []).append(U[(w, c)])
    v, m = C.judge(U); M = json.load(open(K / "maps.json"))["schemas"]
    per = {s: {k: (round(st.mean([abs(U[(w, f"{s}__{k}")] - U[(w, "CLEAN")]) for w in WINS if (w, f"{s}__{k}") in U and (w, "CLEAN") in U]), 2)
                   if any((w, f"{s}__{k}") in U and (w, "CLEAN") in U for w in WINS) else None) for k in METHODS} for s in SCHEMAS}
    meanU = {k: (st.mean([U[(w, f"{s}__{k}")] for s in SCHEMAS for w in WINS if (w, f"{s}__{k}") in U]) if k != "CLEAN" else st.mean([U[(w, "CLEAN")] for w in WINS if (w, "CLEAN") in U])) for k in ["CLEAN"] + METHODS}
    meanQ = {k: (lambda xs: st.mean(xs) if xs else None)([Q[(w, c)] for (w, c) in Q if Q[(w, c)] is not None and (c == "CLEAN" if k == "CLEAN" else c.endswith("__" + k))]) for k in ["CLEAN"] + METHODS}
    res = {"verdict": v, **m, "mean_dev_by_schema": per, "mean_U": meanU, "mean_vmaf": meanQ, "mapping_correct": {s: M[s]["correct"] for s in SCHEMAS}, "clean_U_by_pair": pairU,
           "compute_p95_median_ms": (st.median(CP) if CP else None), "condition_audit": au_txt, "n_runs": len(U), "n_expected": len(WINS) * 21}
    (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    basis = (f"Primary endpoint: mean deviation from the true mapping LLM {m['mean_dev']['LLM']:.2f}, distribution matching {m['mean_dev']['DIST']:.2f}, name matching {m['mean_dev']['NAME']:.2f}, not adapted {m['mean_dev']['NONE']:.2f}; Δ ({m['best_nonllm']} minus LLM) {m['delta']:+.2f}, 90% interval [{m['ci90'][0]:+.2f}, {m['ci90'][1]:+.2f}]; safety line (number of cells where the LLM is more than 10 points below the true mapping) {m['severe_loss']['LLM']}. Report only: per schema deviation {json.dumps(per, ensure_ascii=False)}; number of cells more than 10 points below the true mapping {json.dumps(m['severe_loss'], ensure_ascii=False)}; mean utility {json.dumps({k: round(x, 1) for k, x in meanU.items()}, ensure_ascii=False)}; mean quality {json.dumps({k: (round(x, 1) if x else None) for k, x in meanQ.items()}, ensure_ascii=False)}; mappings correct field by field {json.dumps(res['mapping_correct'], ensure_ascii=False)}; median over runs of the 95th-percentile compute time (ms) {res['compute_p95_median_ms']}; valid runs {len(U)}/{len(WINS) * 21}.{au_txt}")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: res[k] for k in ("delta", "ci90", "best_nonllm", "mean_dev", "severe_loss", "mean_dev_by_schema", "mean_U", "mean_vmaf")}, ensure_ascii=False, default=str), "--artifact", str(K / "result_v1.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmation, the same decision function as obsschema-closedloop-v2)." + basis, "--basis", basis,
       "--limitations", "Downstream is the multi-scale variant without the LLM behind envelope v6 (after congestion it outputs the shadow GCC rate, which narrows the differences between mappings; the shadow GCC reads native packet reports, bypassing the adapter); the same windows as obsschema-closedloop-llm4bandpp-v2, eight Norwegian 3G windows, one run per condition; the four held-out schemas differ only in order and units, rt_getstats only borrows the getStats naming and unit conventions, the field meanings are still the 15 interface features; the mappings of the four held-out schemas follow obsschema-closedloop-v2, the mappings of the five schemas are those of v1 of this experiment, unchanged; the probing envelope rewrites most decisions; two container pairs in parallel on one machine; receiver-side inference is asynchronous (run script v14: when inference takes longer than 40 ms, the previous estimate is returned and the new one applies once it is ready); v1 is void because synchronous inference dropped observations.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "maps": maps()
    elif c == "smoke": smoke(sys.argv[2])
    elif c == "jobs": jobs(sys.argv[2])
    elif c == "judge": C.selftest() if "--selftest" in sys.argv else main()
