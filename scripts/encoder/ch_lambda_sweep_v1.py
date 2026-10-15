#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered experiment ch-lambda-sweep-v1: collect and summarize the HCQ weight sweep of the deployed recipe. Measurement only, no registered criterion.
λ 0.2, 0.6, 0.8 and 1.0, three seeds each, trained as cell CH with --reward_lambda set; evaluation JSONs CHl{02,06,08,10}s{0,1,2}.json copied from the training server.
λ 0 and 0.4 reuse cells CB and CH of ablation-nl-enc-hcq-2x2-v1, seeds 0 to 2 (same evaluation script and arguments).
Per λ: three-seed mean, min and max of macro MSE (mean of the three scenario MSEs, equal to macro_mse in the evaluation JSON) and of per-scenario MSE, e+ (over) and e− (under).
Writes summary.json, read by make_fig_lambda_supp_v2.py for Fig. S1; --register records it in the registry.
Usage: ch_lambda_sweep_v1.py fetch | summarize [--register]
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; OUT = ROOT / "experiments/results/ch_lambda_sweep_v1"; NL = ROOT / "experiments/results/nl_2x2_v1/eval"
ID = "ch-lambda-sweep-v1"; R = "/path/to/server/outputs/ch_lambda_v1"; SC = ("High BW", "Low BW", "Fluctuating")
SRC = {0.0: [NL / f"CBs{s}.json" for s in range(3)], 0.4: [NL / f"CHs{s}.json" for s in range(3)],
       **{l: [OUT / "eval" / f"CHl{int(round(l * 10)):02d}s{s}.json" for s in range(3)] for l in (0.2, 0.6, 0.8, 1.0)}}


def fetch():
    r = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", "gpu-server-2", f"test -f {R}/QUEUE_DONE && ls {R}/eval | wc -l"], capture_output=True, text=True)
    assert r.stdout.strip() == "12", f"gpu-server-2 not complete: {r.stdout!r}"
    (OUT / "eval").mkdir(parents=True, exist_ok=True)
    subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"gpu-server-2:{R}/eval/*.json", str(OUT / "eval")], check=True); print("Retrieved 12 evaluation files")


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
    # Two λ values with the same macro mean would mean one checkpoint was evaluated twice.
    assert len({round(T[l]["macro"]["mean"], 9) for l in T}) == len(T), "two cells have identical macro means; the same checkpoint may have been evaluated twice"
    for l in sorted(T):
        t = T[l]; print(f"λ {l:.1f} macro {t['macro']['mean']:.3f} ({t['macro']['min']:.3f} to {t['macro']['max']:.3f})",
                         " ".join(f"{s} {t[s + '|mse']['mean']:.3f}" for s in SC), f"low bandwidth e+ {t['Low BW|over']['mean']:.3f} e− {t['Low BW|under']['mean']:.3f}")
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "summary.json").write_text(json.dumps({str(k): v for k, v in T.items()}, ensure_ascii=False, indent=1))
    if not register: return
    # If the seed ranges at λ 0.6, 0.8 and 1.0 share a common overlap, those weights cannot be ranked within seed noise.
    hi = [T[l]["macro"] for l in (0.6, 0.8, 1.0)]; overlap = max(h["min"] for h in hi) <= min(h["max"] for h in hi)
    basis = ("Macro MSE mean over three seeds (min to max):" + ";".join(f"λ {l:.1f} {T[l]['macro']['mean']:.3f} ({T[l]['macro']['min']:.3f} to {T[l]['macro']['max']:.3f})" for l in sorted(T)) +
             f"Unfavorable prediction (λ 0.6 to 1.0 cannot be ranked within seed noise): the seed ranges of the three overlap in {'yes' if overlap else 'none'}. See summary.json for the MSE and e+ and e− of each scenario.")
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({str(l): T[l]["macro"] for l in sorted(T)}, ensure_ascii=False), "--artifact", str(OUT / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", "holds", "--vs-criteria", "Measurement only, no verdict; \"holds\" here means only that the three-seed measurements for each of the 6 λ values are complete and the definition check passes." + basis, "--basis", basis,
       "--limitations", "offline 870 calls; lambda 0 and 0.4 reuse the CB and CH cells of nl_2x2_v1 (same training and evaluation script); three seeds; closed-loop QoE registered separately.", "--next", "")


if __name__ == "__main__":
    fetch() if sys.argv[1] == "fetch" else summarize("--register" in sys.argv)
