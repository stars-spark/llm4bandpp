#!/usr/bin/env python3
"""Export the training split of the challenge calls and the (call, step) of every transition of MRE_4.pickle.

The conference split (dataset/split_emulated_dataset&make_pickle.py) copied 8464 of the 9405 public emulated calls into
solution/training_dataset and the other 941 into solution/evaluate_dataset. Both directories are kept on our GPU server,
so the split is listed as it stands, with the SHA-256 of each file. MRE_4.pickle, the balanced pickle our runs trained
on, was drawn without a recorded index. Each of its transitions is matched back to the call and step it came from by the
exact bytes of its observation, action and next observation; both split directories are searched, so a transition of a
held-out call would be found too. The recovered index is checked by rebuilding every transition with
make_balanced_pickle_v1.build and comparing the result with the pickle field by field. Some transitions occur more than
once with identical observation, action and next observation; such a transition is assigned to the source whose true
capacity and reward (recomputed as make_balanced_pickle_v1.call_rows does) equal the pickle's, preferring training calls.

Outputs in OUT: split_v1.json (file names and SHA-256 of both parts), mre4_index_v1.npz (calls: the file names of both
parts, training first; call, step: one entry per transition, in pickle order), summary_v1.json (counts, the assignment of
repeated transitions and the comparison).
Usage: export_split_mre4_index_v1.py SOLUTION_DIR PICKLE OUT [--workers 12] [--reward-lambda 0.4]
"""
import argparse
import hashlib
import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_balanced_pickle_v1 as MB   # noqa: E402

DT = np.float64


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def key(o, a, n):
    return hashlib.blake2b(o.tobytes() + a.tobytes() + n.tobytes(), digest_size=16).digest()


LAM = 0.4


def init(lam):
    global LAM
    LAM = lam


def call_keys(job):
    """Every step of one call: (part, call index, keys, true capacities, rewards, video and audio quality)."""
    part, ci, path = job
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    o = np.asarray(c["observations"], dtype=DT)
    a = np.asarray(c["bandwidth_predictions"], dtype=DT).reshape(-1, 1)
    nx = np.vstack([o[1:], np.full((1, o.shape[1]), -1, dtype=DT)])
    _, _, _, rew, _, cap = MB.call_rows(c, LAM)
    return part, ci, [key(o[i], a[i], nx[i]) for i in range(len(o))], cap, rew, c["video_quality"], c["audio_quality"]


def agrees(x, y):
    return (x != x and y != y) or x == y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("solution"); ap.add_argument("pickle"); ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--reward-lambda", type=float, default=0.4)
    a = ap.parse_args()
    sol, out = Path(a.solution), Path(a.out); out.mkdir(parents=True, exist_ok=True)
    parts = {"training": sorted(p.name for p in (sol / "training_dataset").glob("*.json")),
             "evaluate": sorted(p.name for p in (sol / "evaluate_dataset").glob("*.json"))}
    dirs = {"training": sol / "training_dataset", "evaluate": sol / "evaluate_dataset"}
    assert not set(parts["training"]) & set(parts["evaluate"]), "a call is in both parts"
    with Pool(a.workers) as pool:
        split = {k: dict(zip(v, pool.map(sha256, [str(dirs[k] / n) for n in v], chunksize=16))) for k, v in parts.items()}
    (out / "split_v1.json").write_text(json.dumps({"source": "conference split, solution/training_dataset and solution/evaluate_dataset",
                                                   "counts": {k: len(v) for k, v in split.items()}, "sha256": split}, indent=0), encoding="utf-8")
    print("split", {k: len(v) for k, v in split.items()}, flush=True)

    P = pickle.load(open(a.pickle, "rb"))
    fields = {k: (str(np.asarray(v).dtype), list(np.asarray(v).shape)) for k, v in P.items()}
    print("pickle fields", fields, flush=True)
    obs = np.ascontiguousarray(P["observations"], dtype=DT); act = np.ascontiguousarray(P["actions"], dtype=DT).reshape(len(obs), -1)
    nxt = np.ascontiguousarray(P["next_observations"], dtype=DT)
    N = len(obs); rows_of = {}
    for i in range(N):
        rows_of.setdefault(key(obs[i], act[i], nxt[i]), []).append(i)
    print("pickle transitions", N, "distinct", len(rows_of), flush=True)

    pcap = np.asarray(P["true_capacitys"], dtype=DT).ravel().tolist(); prew = np.asarray(P["rewards"], dtype=DT).ravel().tolist()
    names = parts["training"] + parts["evaluate"]; off = {"training": 0, "evaluate": len(parts["training"])}
    call = np.full(N, -1, dtype=np.int32); step = np.full(N, -1, dtype=np.int32); cands = np.zeros(N, dtype=np.int32)
    held_out = np.zeros(N, dtype=bool); score = np.full(N, -1, dtype=np.int8); diag = {}
    jobs = [(k, ci, str(dirs[k] / n)) for k in ("training", "evaluate") for ci, n in enumerate(parts[k])]
    with Pool(a.workers, initializer=init, initargs=(a.reward_lambda,)) as pool:
        for part, ci, keys, cap, rew, qv, qa in pool.imap_unordered(call_keys, jobs, chunksize=4):
            for si, k in enumerate(keys):
                for i in rows_of.get(k, ()):
                    cands[i] += 1
                    if part == "evaluate": held_out[i] = True
                    s = 2 * agrees(cap[si], pcap[i]) + agrees(rew[si], prew[i])   # 3: capacity and reward agree
                    s = s * 2 + (part == "training")
                    if s > score[i]:
                        score[i], call[i], step[i] = s, off[part] + ci, si
                        diag[i] = (names[off[part] + ci], si, cap[si], rew[si], qv[si], qa[si])
    unmatched = int((call < 0).sum())
    agree = score >> 1
    bad = np.where(agree < 3)[0]
    summary_diag = {"capacity_and_reward_agree": int((agree == 3).sum()), "capacity_only": int((agree == 2).sum()),
                    "reward_only": int((agree == 1).sum()), "neither": int((agree == 0).sum()),
                    "source_in_held_out_calls": int((call >= len(parts["training"])).sum()),
                    "examples": [{"row": int(i), "call": diag[i][0], "step": diag[i][1], "pickle_capacity": pcap[i], "capacity": diag[i][2],
                                  "pickle_reward": prew[i], "reward": diag[i][3], "video_quality": diag[i][4], "audio_quality": diag[i][5],
                                  "action": float(act[i, 0])} for i in bad[:40].tolist()]}
    if len(bad):
        caps = np.array([diag[i][2] for i in bad.tolist()], dtype=DT); qvs = np.array([diag[i][4] for i in bad.tolist()], dtype=DT)
        qas = np.array([diag[i][5] for i in bad.tolist()], dtype=DT); dr = np.abs(np.array([prew[i] - diag[i][3] for i in bad.tolist()], dtype=DT))
        summary_diag.update(video_quality_missing=int(np.isnan(qvs).sum()), audio_quality_missing=int(np.isnan(qas).sum()),
                            capacity_missing=int(np.isnan(caps).sum()), capacity_below_100kbps=int((caps < 1e5).sum()),
                            reward_diff_quantiles=[float(np.nanquantile(dr, q)) for q in (0.5, 0.9, 0.99, 1.0)] if np.isfinite(dr).any() else None)
    summary = {"pickle": a.pickle, "pickle_fields": fields, "transitions": N, "distinct_transitions": len(rows_of),
               "matched": N - unmatched, "unmatched": unmatched, "matched_in_held_out_calls": int(held_out.sum()),
               "transitions_with_several_sources": int((cands > 1).sum()), "calls_used": int(len(set(call[call >= 0].tolist()))),
               "training_calls": len(parts["training"]), "assignment": summary_diag}
    np.savez_compressed(out / "mre4_index_v1.npz", calls=np.array(names), call=call.astype(np.int16), step=step)
    print(json.dumps(summary), flush=True)

    if unmatched == 0 and summary_diag["source_in_held_out_calls"] == 0:   # rebuild every transition from the public calls
        R, _ = MB.build(dirs["training"], parts["training"], list(zip(call.tolist(), step.tolist())), a.reward_lambda)
        cmp = {}
        for k in R:
            if k not in P: continue
            x, y = np.asarray(P[k]).reshape(R[k].shape), R[k]
            same = np.array_equal(x, y, equal_nan=True)
            entry = {"identical": bool(same)}
            if not same and np.issubdtype(y.dtype, np.floating):
                d = np.abs(x.astype(DT) - y); d[np.isnan(x.astype(DT)) & np.isnan(y)] = 0
                entry.update(max_abs_diff=float(np.nanmax(d)), rows_differing=int((d > 0).reshape(len(d), -1).any(1).sum()))
            cmp[k] = entry
        summary["rebuild_comparison"] = cmp
        caps = np.asarray(R["true_capacitys"])
        summary["bin_counts"] = {MB.BINS[b]: int(n) for b, n in zip(*np.unique([MB.capacity_bin(c) for c in caps], return_counts=True))}
        summary["missing_capacity"] = int(np.isnan(caps).sum())
    (out / "summary_v1.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary.get("rebuild_comparison", {})), "\nEXPORT_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
