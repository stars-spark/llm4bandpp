#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deployment closure with median filling (realtel-closure-v2, the browser getStats row of Table IV): as closure_v1.py except that missing features are filled with the per-feature
training median (short windows from short-window medians, long from long), taken from the ref block of obsschema_rt_openreason_v1/evidence.json; the all-missing arm becomes
all-median (ALLMED).
Version 2: imports every other function from closure_v1.py. Needs onnxruntime. Usage: closure_v2.py judge [--selftest]
"""
import hashlib, json, math, random, subprocess, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(HERE))
import closure_v1 as C  # noqa: E402
OUT = C.OUT / "v2"; ID = "realtel-closure-v2"; REF_SHA = "aeccde6eac2e7b67"
_ref = json.load(open(ROOT / "experiments/results/obsschema_rt_openreason_v1/evidence.json"))["ref"]
assert hashlib.sha256(json.dumps(_ref, sort_keys=True).encode()).hexdigest()[:16] == REF_SHA, "ref differs from pre-registration"
MED = [_ref[str(f)]["short"][2] if s < 5 else _ref[str(f)]["long"][2] for f in range(15) for s in range(10)]


def assemble_med(S, feat):
    """Same as closure_v1.assemble, but fill missing values with the matching training median from MED instead of 0."""
    O0, er, cache = C.assemble(S, feat); O = O0.copy()
    for i in range(C.WARM, len(S)):
        sl = [(i - k - 1, i - k) for k in range(5)] + [(i - 10 * (k + 1), i - 10 * k) for k in range(5)]
        for s, (a, b) in enumerate(sl):
            v, _ = cache[(a, b)]
            for f in range(12):
                if v[f] is None: O[i, f * 10 + s] = MED[f * 10 + s]
    return O, er


def judge(D, seed=20261008, B=5000):
    runs = sorted(D["LLM_CODE"]); base = [m for m in D if (m.startswith("MAP_") and m != "MAP_LLM") or m == "ALLMED"]
    mean = lambda m, sel: sum(D[m][r] for r in sel) / len(sel); best = min(base, key=lambda m: mean(m, runs))
    d = lambda sel: mean(best, sel) - mean("LLM_CODE", sel)
    Dl = d(runs); rng = random.Random(seed); boots = sorted(d([rng.choice(runs) for _ in runs]) for _ in range(B))
    return Dl, boots[int(0.05 * B)], boots[int(0.95 * B) - 1], best


def selftest():
    S = [(1000.0 + 60 * i, {"x": {"type": "inbound-rtp", "kind": "video", "packetsReceived": i}}) for i in range(80)]
    O, er = assemble_med(S, lambda p, c: [C.video_in(c)["packetsReceived"] - C.video_in(p)["packetsReceived"]] + [None] * 14)
    assert O[60][0] == 1 and O[60][5] == 10 and O[60][30] == MED[30] and O[60][35] == MED[35] and O[60][-1] == C.MEDIA_PROPORTION[-1] and er == 0
    D = {"LLM_CODE": {f"r{i}": 0.1 for i in range(8)}, "MAP_A": {f"r{i}": 0.4 for i in range(8)}, "ALLMED": {f"r{i}": 0.6 for i in range(8)}, "MAP_LLM": {f"r{i}": 0.01 for i in range(8)}}
    Dl, lo, hi, best = judge(D); assert best == "MAP_A" and abs(Dl - 0.3) < 1e-9 and lo > 0
    print("Self-test passed (median fill, slots, coverage, decision, best control excludes LLM mapping)")


def cmd_judge():
    runs = sorted(p for p in (OUT / "runs").iterdir() if (p / "OK").exists()); assert len(runs) == 8, len(runs)
    assert hashlib.sha256((C.OUT / "design_frozen.py").read_bytes()).hexdigest().startswith("1ca44ae99fd8"), "LLM code differs from the frozen version"
    import realtel_adapter_v1 as M, realtel_baselines_v2 as V
    fl = M.TEST["w3c_webrtc_stats"]["fields"]
    Lm = {(j["source"], j["pres"]): j["mapping"] for j in map(json.loads, open(M.OUT / "llm_test_deepseek.jsonl")) if j.get("ok")}[("w3c_webrtc_stats", 0)]
    arms = {"LLM_CODE": C.code_feat(C.OUT / "design_frozen.py"), "MAP_LLM": C.mapping_feat([None if m is None else (fl[m["source"]][0], m["diff"], m["scale"]) for m in Lm]),
            "ALLMED": lambda p, c: [None] * 15, "OPEN_CODE": C.code_feat(C.OUT / "design_open_frozen.py")}
    Sc = V.classic_scores(); Sc.update(json.load(open(V.OUT / "scores_valentine.json"))); Sc.update(json.load(open(V.OUT / "scores_embed.json"))); taus = json.load(open(V.OUT / "judge.json"))["baselines"]
    for b, sc in Sc.items():
        dec = V.decide(sc["test"]["w3c_webrtc_stats"], taus[b]["tau"])
        arms["MAP_" + b] = C.mapping_feat([None if j is None else (fl[j][0], M.is_cum(fl[j][2]), M.unit_scale(k, fl[j][0], fl[j][2])) for k, j in enumerate(dec)])
    D = {m: {} for m in arms}; ERR = {}
    for d in runs:
        S, sdp = C.snapshots(d); P = C.packets(d, S, sdp); T0, _ = C.truth_obs(S, P); y0 = C.run_onnx(T0)
        for m, f in arms.items():
            O, er = assemble_med(S, f); D[m][d.name] = C.deviation(C.run_onnx(O), y0)
            if m == "LLM_CODE": ERR[d.name] = er
        print(d.name, {m: round(D[m][d.name], 3) for m in D}, flush=True)
    Dl, lo, hi, best = judge(D); gross = max(ERR.values()) > 0.05
    v = "does not hold" if (Dl <= 0 or gross) else ("holds" if lo > 0 and Dl >= C.DELTA else "direction only")
    mean = {m: sum(D[m].values()) / len(D[m]) for m in D}
    json.dump({"verdict": v, "delta": Dl, "ci90": [lo, hi], "best_base": best, "mean_dev": mean, "dev": D, "llm_code_err_rate": ERR}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1)
    by = lambda m, key: sum(D[m][r] for r in D[m] if key in r) / sum(1 for r in D[m] if key in r)
    basis = (f"8 new runs, missing filled with training median: LLM code {mean['LLM_CODE']:.3f}; best non-LLM {best} {mean[best]:.3f}; all filled with median {mean['ALLMED']:.3f}; Δ {Dl:+.3f}, 90% interval [{lo:+.3f}, {hi:+.3f}]; LLM code has the largest anomaly rate {max(ERR.values()):.3f}. By bandwidth (report only): 1 Mbit/s LLM code {by('LLM_CODE', 'r1000'):.3f} versus {best} {by(best, 'r1000'):.3f}, 2.5 Mbit/s {by('LLM_CODE', 'r2500'):.3f} versus {by(best, 'r2500'):.3f}. Report only: LLM field mapping {mean['MAP_LLM']:.3f}, open-source code {mean['OPEN_CODE']:.3f}; each method " + ",".join(f"{m} {x:.3f}" for m, x in mean.items()) + ".")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"delta": Dl, "ci90": [lo, hi], "mean_dev": mean, "best_base": best}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (confirmatory template, the same as the first version, only the missing-value imputation is changed)." + basis, "--basis", basis,
       "--limitations", "Loopback interface with netem, single estimator, open-loop comparison of estimator output; getStats has no per-packet delay, so delay-type features can only be filled with the median; with them set to 0 the first version does not hold, and both versions are reported side by side.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
