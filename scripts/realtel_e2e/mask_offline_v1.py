#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline masking of the deployed estimator by real-stack feature coverage (registered experiment realtel-mask-offline-v2 with --v2); a measurement with no pass criterion.
Fetches the remote mask runs (M*.json: deployed estimator seed 1, original evaluation script, CPU, 870 calls) and computes the scenario-weighted macro MSE.
Control Mall keeps features 0 to 11, so the wrapper changes no input; it must reproduce the unmasked 5.795 (relative difference < 1e-4) or nothing is recorded.
Each stack keeps the features marked same in the realtel-scale-v1 ground truth; features 12 to 14 are untouched. --v2 reads the runs that fill missing features with training medians.
Usage: python3 mask_offline_v1.py [--v2] [--register]
"""
import json, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; V2 = "--v2" in sys.argv
OUT = ROOT / ("experiments/results/realtel_mask_offline_v2" if V2 else "experiments/results/realtel_mask_offline_v1"); ID = "realtel-mask-offline-v2" if V2 else "realtel-mask-offline-v1"; RD = "out_mask2" if V2 else "out_mask"
REF = 5.795321406627085


def macro(rows):
    g = {}
    for r in rows: g.setdefault(r["scenario"], []).append(float(r["mse"]))
    return st.mean(st.mean(v) for v in g.values()), {k: st.mean(v) for k, v in g.items()}


def main(register):
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"gpu-server-1:work/ch_equiv_v1/{RD}/*.json", f"gpu-server-1:work/ch_equiv_v1/{RD}/sha256sums.txt", str(OUT)], check=True)
    S = json.load(open(ROOT / "experiments/results/realtel_scale_v1/sources.json"))
    keep = {n: [k for k, t in enumerate(s["truth"]) if t[0] == "same"] for n, s in S.items()}
    tag = lambda ks: "M" + ("_".join(map(str, ks)) if ks else "none")
    M = {}
    for f in sorted(OUT.glob("M*.json")):
        d = json.load(open(f)); rows = d.get("files", d.get("rows")); assert len(rows) == 870, (f, len(rows)); M[f.stem] = macro(rows)
    ok = abs(M["Mall"][0] - REF) / REF < 1e-4
    per_stack = {n: {"keep": ks, "macro": M[tag(ks)][0], "by_scen": M[tag(ks)][1]} for n, ks in keep.items()}
    res = {"control_Mall": {"macro": M["Mall"][0], "ref": REF, "pass": ok}, "masks": {k: {"macro": v[0], "by_scen": v[1]} for k, v in M.items()}, "per_stack": per_stack}
    json.dump(res, open(OUT / "summary.json", "w"), ensure_ascii=False, indent=1)
    r2 = lambda x: round(x, 2)
    basis = (f"Wrapper comparison Mall {M['Mall'][0]:.4f} versus unmasked {REF:.4f} ({'pass' if ok else 'fail'}). Per stack (retained features, macro MSE):" +
             ";".join(f"{n} {ks} {r2(per_stack[n]['macro'])}" for n, ks in keep.items()) + ". Each mask is split by scenario:" +
             ";".join(f"{k} " + json.dumps({s: r2(x) for s, x in v[1].items()}) for k, v in M.items()) + ".")
    print(basis)
    if not ok: print("control Mall does not reproduce the unmasked MSE; not registered"); sys.exit(1)
    if not register: return
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({n: r2(v["macro"]) for n, v in per_stack.items()} | {"Mall": M["Mall"][0]}, ensure_ascii=False), "--artifact", str(OUT / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", "holds", "--vs-criteria", "Measurement only, no verdict; \"holds\" here means only that all seven masks and the wrapper-layer comparison are evaluated, and the comparison reproduces the unmasked readings." + basis, "--basis", basis,
       "--limitations", "Only features that can be mapped from a single field are kept; features the designer could derive from multiple fields (such as deriving the receiving rate from byte counts) are not counted;" + ("Missing features are filled with the training median, same as realtel-closure-v2;" if V2 else "Missing features are set to 0, same as the adapter layer of the synthetic-mode closed loop;") + "offline 870 calls, not closed-loop; features 12 to 14 keep the recorded values, and in deployment the collector sets them to the training constants.",
       "--next", "")


if __name__ == "__main__":
    main("--register" in sys.argv)
