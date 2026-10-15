#!/usr/bin/env python3
"""Build a capacity-balanced training pickle in the format of our MRE_4.pickle from the public emulated calls.

Recipe (the conference script dataset_analysis/range_average.py, with the reward of Eq. (1) of the paper):
  every step of every training call is one transition (observation, logged bandwidth prediction as the action, next
  observation, reward, terminal flag, true capacity); the last step of a call has terminal True and a next observation
  of 150 values -1;
  missing video or audio quality scores of a step are replaced by the call's mean (nanmean);
  reward = lambda * (-|action - capacity| / (capacity + 1e-6)) + (1 - lambda) * (0.8 * r_v + 0.2 * r_a), with lambda 0.4;
  a reward that is not a number (missing capacity) is set to 1;
  transitions are grouped by true capacity into the bins [0,1), [1,2), ..., [6,7) and >= 7 Mb/s (a missing capacity
  falls into the last bin, as in the conference script), and at most --per-bin transitions are drawn from each bin
  without replacement.
Our MRE_4.pickle has 3,500,000 transitions: 500,000 in each bin except 3 to 4 Mb/s, which is empty, and >= 7 Mb/s,
which holds 498,556 transitions plus the 1,444 with a missing capacity. We do not know why the 3 to 4 Mb/s bin is
empty; --skip-bins 3-4 reproduces that composition. MRE_4 was drawn without a fixed seed, so a rebuild with --seed
draws a different sample; this script writes the drawn (call, step) index next to the pickle. To rebuild MRE_4 itself,
pass --from-index with experiments/results/training_split_v1/mre4_index_v1.npz, the (call, step) of each of its
transitions in pickle order, recovered by export_split_mre4_index_v1.py; the bins and the draw are then not used.

Usage: python3 scripts/encoder/make_balanced_pickle_v1.py --train-dir DIR --out FILE.pickle [--per-bin 500000]
       [--reward-lambda 0.4] [--seed 0] [--skip-bins 3-4] [--names FILE] [--from-index INDEX.npz]
  --train-dir  directory with the training calls (public emulated files, NNNNN.json)
  --names      optional text file with one training file name per line (default: every *.json in --train-dir)
Memory: the output arrays need about 8.4 GB for 3.5 million transitions; the calls are read twice, one at a time.
"""
import argparse
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np

BINS = ["0-1", "1-2", "2-3", "3-4", "4-5", "5-6", "6-7", ">=7"]


def capacity_bin(c):
    """Bin label of one true capacity in bit/s; a missing value (NaN) falls into the last bin."""
    for k, edge in enumerate((1e6, 2e6, 3e6, 4e6, 5e6, 6e6, 7e6)):
        if c < edge:
            return k
    return 7


def call_rows(c, lam):
    """Transitions of one call: observations, actions, next observations, rewards, terminals, capacities."""
    obs = c["observations"]
    act = c["bandwidth_predictions"]
    qv, qa, cap = c["video_quality"], c["audio_quality"], c["true_capacity"]
    avg_v = np.nanmean(np.asarray(qv, dtype=np.float32))
    avg_a = np.nanmean(np.asarray(qa, dtype=np.float32))
    n = len(obs)
    rewards = []
    for i in range(n):
        r_v = avg_v if math.isnan(qv[i]) else qv[i]
        r_a = avg_a if math.isnan(qa[i]) else qa[i]
        acc = -abs(act[i] - cap[i]) / (cap[i] + 1e-6)
        r = lam * acc + (1 - lam) * (0.8 * r_v + 0.2 * r_a)
        rewards.append(1.0 if math.isnan(r) else r)
    nxt = [obs[i + 1] if i + 1 < n else [-1] * len(obs[0]) for i in range(n)]
    return obs, [[a] for a in act], nxt, rewards, [i == n - 1 for i in range(n)], cap


def build(d, names, rows, lam):
    """Arrays of the transitions rows = [(call index, step), ...], in that order."""
    n = len(rows)
    out = {"observations": np.zeros((n, 150)), "actions": np.zeros((n, 1)), "next_observations": np.zeros((n, 150)),
           "rewards": np.zeros(n), "terminals": np.zeros(n, dtype=bool), "true_capacitys": np.zeros(n)}
    by_call = {}
    for j, (ci, si) in enumerate(rows):
        by_call.setdefault(ci, []).append((j, si))
    for ci in sorted(by_call):
        o, act, nx, r, t, cap = call_rows(json.loads((d / names[ci]).read_text(encoding="utf-8")), lam)
        for j, si in by_call[ci]:
            out["observations"][j] = o[si]; out["actions"][j] = act[si]; out["next_observations"][j] = nx[si]
            out["rewards"][j] = r[si]; out["terminals"][j] = t[si]; out["true_capacitys"][j] = cap[si]
    return out, len(by_call)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--names")
    ap.add_argument("--per-bin", type=int, default=500000)
    ap.add_argument("--reward-lambda", type=float, default=0.4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--skip-bins", default="", help="comma-separated bin labels to leave empty, e.g. 3-4")
    ap.add_argument("--from-index", help="npz with calls, call and step: rebuild exactly these transitions in this order")
    a = ap.parse_args()
    d = Path(a.train_dir)
    if a.from_index:
        z = np.load(a.from_index, allow_pickle=False)
        names = [str(x) for x in z["calls"]]
        out, used = build(d, names, list(zip(z["call"].tolist(), z["step"].tolist())), a.reward_lambda)
        with open(a.out, "wb") as f:
            pickle.dump(out, f)
        print(f"{len(z['call'])} transitions from {used} calls rebuilt from {a.from_index} -> {a.out}")
        return 0
    names = [l.strip() for l in open(a.names)] if a.names else sorted(p.name for p in d.glob("*.json"))
    names = [n for n in names if n]
    skip = {BINS.index(s.strip()) for s in a.skip_bins.split(",") if s.strip()}
    # pass 1: the bin of every step
    per_bin = [[] for _ in BINS]
    for ci, name in enumerate(names):
        cap = json.loads((d / name).read_text(encoding="utf-8"))["true_capacity"]
        for si, c in enumerate(cap):
            per_bin[capacity_bin(c)].append((ci, si))
    rng = np.random.default_rng(a.seed)
    chosen = []
    for k, rows in enumerate(per_bin):
        if k in skip or not rows:
            continue
        idx = rng.choice(len(rows), size=min(a.per_bin, len(rows)), replace=False)
        chosen += [rows[i] for i in sorted(idx)]
    chosen.sort()
    n = len(chosen)
    out, _ = build(d, names, chosen, a.reward_lambda)   # pass 2: fill the drawn transitions call by call
    by_call = {ci for ci, _ in chosen}
    with open(a.out, "wb") as f:
        pickle.dump(out, f)
    index = Path(a.out).with_suffix(".index.json")
    index.write_text(json.dumps({"seed": a.seed, "per_bin": a.per_bin, "reward_lambda": a.reward_lambda,
                                 "skip_bins": sorted(BINS[k] for k in skip), "calls": names,
                                 "rows": [[names[ci], si] for ci, si in chosen],
                                 "bin_counts": {BINS[k]: (0 if k in skip else min(a.per_bin, len(v))) for k, v in enumerate(per_bin)}}),
                     encoding="utf-8")
    print(f"{n} transitions from {len(by_call)} of {len(names)} calls -> {a.out}; index -> {index}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
