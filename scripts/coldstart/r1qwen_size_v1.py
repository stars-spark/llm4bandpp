#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch, scoring and registration of realtel-scale-r1qwen-size-v1 (criteria in its pre-registration).
fetch: copies out_scale_r1_{7b,1p5b}_sd{20261002,20261003,20261004}.jsonl from the GPU server and stores them in realtel_scale_v1 as out_open_r1_{7b,1p5b}_sd*.jsonl.
score [--register]: mean BA over three samples for four sizes (1.5B and 7B run here; 14B and 32B are the three samples of open-sampling-variance-v1), read as make_fig_designer_v2.open_ba reads them.
Holds: strictly increasing with size and 32B minus 1.5B at least 0.20; direction only: positive rank correlation without that; does not hold: rank correlation not positive.
Report only: parse rates and the BA over parsed answers. Writes experiments/results/realtel_scale_r1qwen_size_v1/summary.json.
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for p in ("scripts/coldstart", "scripts/paper"): sys.path.insert(0, str(ROOT / p))
import realtel_scale_v1 as RS  # noqa: E402
M = RS.M
W = "/path/to/server/work/openreason_v1"; SEEDS = ("20261002", "20261003", "20261004"); ID = "realtel-scale-r1qwen-size-v1"
OUT = ROOT / "experiments/results/realtel_scale_r1qwen_size_v1"
TAGS = {"1.5B": [f"r1_1p5b_sd{s}" for s in SEEDS], "7B": [f"r1_7b_sd{s}" for s in SEEDS],
        "14B": ["r1_14b", "r1_14b_sd20261003", "r1_14b_sd20261004"], "32B": ["r1_32b", "r1_32b_sd20261003", "r1_32b_sd20261004"]}


def fetch():
    for m in ("7b", "1p5b"):
        for s in SEEDS:
            src = f"out_scale_r1_{m}_sd{s}.jsonl"
            ok = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", "gpu-server-2", f"test -f {W}/{src}.DONE"]).returncode == 0
            if ok: subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"gpu-server-2:{W}/{src}", str(RS.OUT / f"out_open_r1_{m}_sd{s}.jsonl")], check=True); print("Retrieve", src)
            else: print("remote run not finished; skipped", src)


def parse_info(tag, S):
    L, n, ok, lim = {}, 0, 0, 0
    for j in map(json.loads, open(RS.OUT / f"out_open_{tag}.jsonl")):
        _, nm, k = j["id"].split("|"); n += 1; lim += j.get("finish_reason") == "length"
        try: L[(nm, int(k))] = M.parse(j["text"], len(S[nm]["fields"])); ok += 1
        except Exception: L[(nm, int(k))] = None
    for nm in S:
        for k in range(M.NPRES): L.setdefault((nm, k), None)
    rows = RS.rows(S, L); okrows = [r for r in rows if L[(r["source"], r["pres"])] is not None]
    return {"parsed": ok, "n": n, "hit_limit": lim, "ba": M.ba(rows), "ba_parsed_only": (M.ba(okrows) if okrows else None)}


def score(register):
    S = RS.load_sources(); res = {}
    for size, tags in TAGS.items():
        have = [t for t in tags if (RS.OUT / f"out_open_{t}.jsonl").is_file()]
        runs = {t: parse_info(t, S) for t in have}; bas = [r["ba"] for r in runs.values()]
        res[size] = {"n_samples": len(have), "mean": (sum(bas) / len(bas) if bas else None), "min": (min(bas) if bas else None), "max": (max(bas) if bas else None), "runs": runs}
        print(size, len(have), "times", None if not bas else round(sum(bas) / len(bas), 3), [round(b, 3) for b in bas], "Parse", [f"{r['parsed']}/{r['n']}" for r in runs.values()])
    assert round(res["14B"]["mean"], 3) == 0.695 and round(res["32B"]["mean"], 3) == 0.893, "14B, 32B did not reproduce the mean of open-sampling-variance-v1"
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if not register: return
    if any(res[s]["n_samples"] != 3 for s in TAGS): print("fewer than three samples per model; not registered"); return
    order = ["1.5B", "7B", "14B", "32B"]; mu = [res[s]["mean"] for s in order]
    # rho: Spearman correlation between size rank (0 to 3) and BA rank, without ties.
    ranks = sorted(range(4), key=lambda i: mu[i]); rk = [0] * 4
    for r, i in enumerate(ranks): rk[i] = r
    rho = 1 - 6 * sum((rk[i] - i) ** 2 for i in range(4)) / (4 * 15)
    mono = all(mu[i] < mu[i + 1] for i in range(3))
    v = "holds" if (mono and mu[3] - mu[0] >= 0.20) else ("direction only" if rho > 0 else "does not hold")
    f = lambda s: f"{res[s]['mean']:.3f} ({res[s]['min']:.3f} to {res[s]['max']:.3f})"
    po = lambda s: [None if r["ba_parsed_only"] is None else round(r["ba_parsed_only"], 3) for r in res[s]["runs"].values()]
    basis = ("Mean BA over three runs (min to max):" + ";".join(f"{s} {f(s)}" for s in order) + f". Strictly monotone {'yes' if mono else 'no'}, 32B minus 1.5B {mu[3] - mu[0]:+.3f}, rank correlation {rho:+.2f}. Report only: parse success " + ";".join(f"{s} " + ", ".join(f"{r['parsed']}/{r['n']}" for r in res[s]["runs"].values()) for s in order) +
             "; BA over parsed answers only " + ";".join(f"{s} {po(s)}" for s in order) + ".")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({s: {k: res[s][k] for k in ("mean", "min", "max")} for s in order} | {"rho": rho, "monotone": mono}, ensure_ascii=False), "--artifact", str(OUT / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered: holds if BA rises strictly with size and 32B minus 1.5B is at least 0.20; direction only if the rank correlation is positive." + basis, "--basis", basis,
       "--limitations", "Four sizes of the same family, three samples each (temperature 0.6); 32B is 4-bit GPTQ, the rest are float16; 12 client stacks, field descriptions only; prompts frozen per hosted model.", "--next", "")


if __name__ == "__main__":
    fetch() if sys.argv[1] == "fetch" else score("--register" in sys.argv)
