#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered experiment anchor-ablation-v1: collect and summarize the capacity-anchor ablation. Measurement only, no registered criterion.
Without the anchor (capacity_aux_weight 0): λ 0 and 0.4, seeds 0 to 2, evaluation JSONs A0l{00,04}s{0,1,2}.json copied from the training server.
With the anchor: cells CB and CH of ablation-nl-enc-hcq-2x2-v1, seeds 0 to 2 (same training and evaluation scripts; only the anchor differs).
Per cell: three-seed mean, min and max of macro MSE and of per-scenario MSE, e+ and e−; also the anchor contribution (no anchor minus anchor,
macro mean) and the Table I references LLM4Band 6.927 and Schaferct-R 7.074. Writes summary.json; --register records it in the registry.
Usage: anchor_ablation_v1.py fetch | summarize [--register]
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; OUT = ROOT / "experiments/results/anchor_ablation_v1"; NL = ROOT / "experiments/results/nl_2x2_v1/eval"
ID = "anchor-ablation-v1"; R = "/path/to/server/outputs/anchor_ablation_v1"; SC = ("High BW", "Low BW", "Fluctuating")
SRC = {"CB anchor": [NL / f"CBs{s}.json" for s in range(3)], "CH anchor": [NL / f"CHs{s}.json" for s in range(3)],
       "CB no anchor": [OUT / "eval" / f"A0l00s{s}.json" for s in range(3)], "CH no anchor": [OUT / "eval" / f"A0l04s{s}.json" for s in range(3)]}
BASE = {"LLM4Band": 6.927, "Schaferct-R": 7.074}


def fetch():
    r = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", "gpu-server-2", f"test -f {R}/QUEUE_DONE && ls {R}/eval | wc -l"], capture_output=True, text=True)
    assert r.stdout.strip() == "6", f"gpu-server-2 not complete: {r.stdout!r}"
    (OUT / "eval").mkdir(parents=True, exist_ok=True)
    subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"gpu-server-2:{R}/eval/*.json", str(OUT / "eval")], check=True); print("Retrieved 6 evaluation files")


def summarize(register):
    rows, T = {}, {}
    for l, fs in SRC.items():
        D = [json.load(open(f)) for f in fs]
        for d, f in zip(D, fs):
            assert len(d["files"]) == 870 and d["limit"] == 0, f
            assert abs(d["macro_mse"] - sum(d["summaries"][s]["mse"] for s in SC) / 3) < 1e-9, f
        st = lambda xs: {"mean": sum(xs) / len(xs), "min": min(xs), "max": max(xs)}
        T[l] = {"macro": st([d["macro_mse"] for d in D]), **{f"{s}|{k}": st([d["summaries"][s][k] for d in D]) for s in SC for k in ("mse", "over", "under")},
                "sources": [str(f.relative_to(ROOT)) for f in fs]}
    # Two cells with the same macro mean would mean one checkpoint was evaluated twice.
    assert len({round(T[l]["macro"]["mean"], 9) for l in T}) == len(T), "two cells have identical macro means; the same checkpoint may have been evaluated twice"
    for l in T:
        t = T[l]; print(f"{l} macro {t['macro']['mean']:.3f} ({t['macro']['min']:.3f} to {t['macro']['max']:.3f})",
                         " ".join(f"{s} {t[s + '|mse']['mean']:.3f}" for s in SC), f"low bandwidth e+ {t['Low BW|over']['mean']:.3f} e− {t['Low BW|under']['mean']:.3f}")
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "summary.json").write_text(json.dumps({"cells": T, "baselines_table_I": BASE}, ensure_ascii=False, indent=1))
    if not register: return
    f = lambda d: f"{d['mean']:.3f} ({d['min']:.3f} to {d['max']:.3f})"
    ca = {k: T[f"{k} no anchor"]["macro"]["mean"] - T[f"{k} anchor"]["macro"]["mean"] for k in ("CB", "CH")}
    basis = ("Macro MSE mean over three seeds (min to max):" + ";".join(f"{l} {f(T[l]['macro'])}" for l in T) + f"Anchor contribution (without anchor minus with anchor): λ 0 is {ca['CB']:+.3f}, λ 0.4 is {ca['CH']:+.3f}. Table I reference: LLM4Band {BASE['LLM4Band']}, Schaferct-R {BASE['Schaferct-R']}; the deployed recipe without anchor (λ 0.4) {'below' if T['CH no anchor']['macro']['mean'] < BASE['LLM4Band'] else 'not lower than'} LLM4Band. See summary.json for each scenario.")
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({l: T[l]["macro"] for l in T}, ensure_ascii=False), "--artifact", str(OUT / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", "holds", "--vs-criteria", "Measurement only, no verdict; \"holds\" here means only that all four cells have three seeds and the consistency check passes." + basis, "--basis", basis,
       "--limitations", "offline 870 calls; the anchored reference reuses the CB and CH cells of nl_2x2_v1 (same training and evaluation script); three seeds; only the anchor is varied.", "--next", "")


if __name__ == "__main__":
    fetch() if sys.argv[1] == "fetch" else summarize("--register" in sys.argv)
