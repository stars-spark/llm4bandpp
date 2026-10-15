#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge of schaferct-arch-recipe-v1: copies the three evaluation files SCHs0-2.json from the GPU server and summarizes them
as anchor_ablation_v1 does (macro MSE must equal the mean of the three scenario MSEs), next to the three C-H seeds (CHs0
to CHs2 of nl_2x2_v1) and Schaferct-R (7.074 in main-table-unified-v1), and registers data and conclusion (a
measurement, no pass or fail). finalize_scharch_v1_offline_v1.py repeats the summary from the released files.
Usage: fetch; summarize [--register].
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; OUT = ROOT / "experiments/results/schaferct_arch_recipe_v1"; ID = "schaferct-arch-recipe-v1"
SC = ("High BW", "Low BW", "Fluctuating"); SEEDS = (0, 1, 2); SCR = 7.074


def fetch():
    (OUT / "eval").mkdir(parents=True, exist_ok=True)
    for s in SEEDS:
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"gpu-server-2:/path/to/server/outputs/sch_arch_v1/eval/SCHs{s}.json", str(OUT / "eval" / f"SCHs{s}.json")], check=True)
    print("Retrieve 3 copies")


def stat(xs): return {"mean": sum(xs) / len(xs), "min": min(xs), "max": max(xs)}


def cell(files):
    D = [json.load(open(f)) for f in files]
    for d, f in zip(D, files):
        assert abs(d["macro_mse"] - sum(d["summaries"][s]["mse"] for s in SC) / 3) < 1e-9, f
        assert sum(d["summaries"][s]["n"] for s in SC) == 870, f
    return {"macro": stat([d["macro_mse"] for d in D]), **{f"{s}|{k}": stat([d["summaries"][s][k] for d in D]) for s in SC for k in ("mse", "over", "under")}}


def summarize(register):
    sch = cell([OUT / "eval" / f"SCHs{s}.json" for s in SEEDS]); ch = cell([ROOT / f"experiments/results/nl_2x2_v1/eval/CHs{s}.json" for s in SEEDS])
    res = {"SCH_arch_our_recipe": sch, "CH": ch, "Schaferct_R_own_recipe_macro": SCR}
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    f = lambda x: f"{x['mean']:.3f} ({x['min']:.3f} to {x['max']:.3f})"
    overlap = not (sch["macro"]["min"] > ch["macro"]["max"] or sch["macro"]["max"] < ch["macro"]["min"])
    basis = (f"Three-seed macro MSE: Schaferct's network with our recipe {f(sch['macro'])}; C-H (conference encoder with our recipe) {f(ch['macro'])}; Schaferct-R (its own recipe) {SCR}. The two seed ranges {'overlap' if overlap else 'non-overlapping'}; mean difference {sch['macro']['mean'] - ch['macro']['mean']:+.3f}, relative to C-H {100 * (sch['macro']['mean'] / ch['macro']['mean'] - 1):+.1f}%, relative to Schaferct-R {100 * (sch['macro']['mean'] / SCR - 1):+.1f}%. Per-scenario MSE (Schaferct structure versus C-H):" + ";".join(f"{s} {sch[s + '|mse']['mean']:.3f} versus {ch[s + '|mse']['mean']:.3f}" for s in SC) +
             f"; Low BW e+ {sch['Low BW|over']['mean']:.3f} versus {ch['Low BW|over']['mean']:.3f}, Fluctuating e+ {sch['Fluctuating|over']['mean']:.3f} versus {ch['Fluctuating|over']['mean']:.3f}.")
    print(basis)
    if not register: return
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"sch_macro": sch["macro"], "ch_macro": ch["macro"], "scr_macro": SCR}, ensure_ascii=False), "--artifact", str(OUT / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", "holds", "--vs-criteria", "Measurement only, no verdict; \"holds\" means only that all three seeds were evaluated and the calibration was checked." + basis, "--basis", basis,
       "--limitations", "The Schaferct structure follows its inference usage as a per-sample single-step GRU, and does not copy its training-time practice of treating the whole batch as a sequence; parameters 1 157 528, more than C-H's 683 160; three seeds; 870 offline calls; the Schaferct-R reading is one checkpoint trained with its own recipe.",
       "--next", "")


if __name__ == "__main__":
    {"fetch": fetch, "summarize": lambda: summarize("--register" in sys.argv)}[sys.argv[1]]()
