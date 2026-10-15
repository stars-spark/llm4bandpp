#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sampling variance of the open designer models (registered experiment open-sampling-variance-v1); a measurement with no pass criterion.
Each open R1-distilled model (14B, 32B, 70B) has three samples at temperature 0.6: the default seed and two extra seeds.
Reports mean, min and max of the correct share on the 42 end-to-end cells and of BA on the 12 client stacks; scoring functions come from realtel_open70b_v1.
Samples whose end-to-end share falls below the Similarity Flooding baseline (SF) are listed.
fetch copies finished remote outputs into the realtel_adapter_v1 and realtel_scale_v1 result folders and skips missing ones.
score runs the realtel_open70b_v1 self-test, scores every model and sample and writes summary.json; --register records only when all three models have three samples.
Usage: open_sampling_variance_v1.py fetch | score [--register]
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_open70b_v1 as R  # noqa: E402
W = "/path/to/server/work/openreason_v1"; HOST = {"r1_32b": "gpu-server-1", "r1_14b": "gpu-server-2", "r1_70b": "gpu-server-1"}; SEEDS = ("sd20261003", "sd20261004")
OUT = ROOT / "experiments/results/open_sampling_variance_v1"; ID = "open-sampling-variance-v1"; SF = 0.762


def fetch():
    for m, h in HOST.items():
        for sd in SEEDS:
            for kind, local in (("realtel", R.M.OUT), ("scale", R.RS.OUT)):
                src, dst = f"{h}:{W}/out_{kind}_{m}_{sd}.jsonl", local / f"out_open_{m}_{sd}.jsonl"
                ok = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", h, f"test -f {W}/out_{kind}_{m}_{sd}.jsonl.DONE"]).returncode == 0
                if ok: subprocess.run(["scp", "-q", "-o", "BatchMode=yes", src, str(dst)], check=True); print("Retrieve", dst.name, kind)
                else: print("remote run not finished; skipped", m, sd, kind)


def score(register):
    R.selftest(); S = R.RS.load_sources(); res = {}
    for m in HOST:
        rows = []
        for t in (m,) + tuple(f"{m}_{sd}" for sd in SEEDS):
            if not ((R.M.OUT / f"out_open_{t}.jsonl").is_file() and (R.RS.OUT / f"out_open_{t}.jsonl").is_file()): continue
            rows.append({"tag": t, "e2e_v3": R.rate(R.v3(R.units(R.open_adapter(t)))), "ba12": R.ba12(t),
                         "parse_realtel": R.parse_stats(R.M.OUT / f"out_open_{t}.jsonl", lambda n: len(R.M.TEST[n]["fields"])),
                         "parse_scale": R.parse_stats(R.RS.OUT / f"out_open_{t}.jsonl", lambda n: len(S[n]["fields"]))})
        agg = lambda k: {"mean": sum(r[k] for r in rows) / len(rows), "min": min(r[k] for r in rows), "max": max(r[k] for r in rows)} if rows else None
        res[m] = {"n_samples": len(rows), "e2e_v3": agg("e2e_v3"), "ba12": agg("ba12"), "runs": rows}
        print(m, len(rows), "times", {k: {kk: round(vv, 3) for kk, vv in res[m][k].items()} for k in ("e2e_v3", "ba12") if res[m][k]})
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if not register: return
    if any(res[m]["n_samples"] != 3 for m in HOST): print("fewer than three samples per model; not registered"); return
    f = lambda d: f"{d['mean']:.3f} ({d['min']:.3f} to {d['max']:.3f})"
    below = {m: [r["tag"] for r in res[m]["runs"] if r["e2e_v3"] < SF] for m in HOST}
    basis = ("Mean of three samples (min to max):" + ";".join(f"{m} end to end (third ground truth) {f(res[m]['e2e_v3'])}, 12-source balanced accuracy {f(res[m]['ba12'])}" for m in HOST) +
             f". Samples below SF {SF}: {json.dumps(below, ensure_ascii=False)}.")
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({m: {k: res[m][k] for k in ("e2e_v3", "ba12")} for m in HOST}, ensure_ascii=False), "--artifact", str(OUT / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", "holds", "--vs-criteria", "Measurement only, no verdict; \"holds\" here means only that all three models have three samples and the scoring self-check passes." + basis, "--basis", basis,
       "--limitations", "Three samples per model (temperature 0.6), four-bit quantization; end to end uses only the first field order; 24 runs on the local loopback interface with netem.", "--next", "")


if __name__ == "__main__":
    fetch() if sys.argv[1] == "fetch" else score("--register" in sys.argv)
