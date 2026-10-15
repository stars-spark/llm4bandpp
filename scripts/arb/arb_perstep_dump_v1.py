#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arb-perstep-dump-v1: export, on the 870 validation calls, the per-step predictions of six estimators (supervised MLP
seeds 0 to 2, the challenge baseline (schaferct_public.onnx), Schaferct-R, Pioneer), the per-step ground-truth
capacity and the short-window value of the 15 features. The evaluation is that of our per-call evaluator; the per-step
predictions are kept instead of being summarized. The ONNX models run step by step on CPU with their LSTM state carried
over; the MLP runs on GPU. perstep.npz feeds main_table_unified_v1.py, offline_echo_row_v1.py and table1_ch_rows_v1.py.
Ran on the GPU server; reads the conference code tree without changing it and writes only to /path/to/server/outputs.
"""
from __future__ import annotations

import glob, json, os, sys, time
from pathlib import Path

import numpy as np

BASE = "/path/to/llm4band_conference"
SCEN_ROOT = f"{BASE}/validation/prepare_scenario"
OUT = Path("/path/to/server/outputs/arb_perstep_dump_v1")
MLP_ROOT = Path("/path/to/server/work/supervised_mlp_eval_3seed_v4_gpu_server_1")
ONNX = {
    "Schaferct(public)":    f"{BASE}/Schaferct/onnx_model_for_evaluation/baseline.onnx",
    "Schaferct(retrained)": f"{BASE}/Schaferct/checkpoints_iql/IQL-range_averge/checkpoint_1000000.onnx",
    "Pioneer":              f"{BASE}/Pioneer/onnx_model/SJTU_Medialab_final.onnx",
}
DIRS = ["high_bw_call", "low_bw_call", "high_fluctuating_bw", "low_fluctuating_bw"]
ARMS = ["MLP_seed0", "MLP_seed1", "MLP_seed2",
        "Schaferct(public)", "Schaferct(retrained)", "Pioneer"]
SHORT_SLOT = np.arange(15) * 10


def files():
    out = []
    for d in DIRS:
        for p in sorted(glob.glob(f"{SCEN_ROOT}/{d}/*.json")):
            out.append((d, p))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fl = files()
    assert len(fl) == 870, len(fl)
    print(f"File count {len(fl)}", flush=True)

    keys = [f"{d}/{os.path.basename(p)}" for d, p in fl]
    nsteps = np.zeros(len(fl), dtype=np.int32)
    feats, truths = [], []
    for i, (d, p) in enumerate(fl):
        call = json.load(open(p))
        obs = np.asarray(call["observations"], dtype=np.float32)
        nsteps[i] = obs.shape[0]
        feats.append(obs[:, SHORT_SLOT].astype(np.float32))
        truths.append((np.asarray(call["true_capacity"], dtype=np.float32) / 1e6))
    print(f"Steps total {int(nsteps.sum())} min {int(nsteps.min())} max {int(nsteps.max())}", flush=True)

    preds = {a: [None] * len(fl) for a in ARMS}

    import torch
    sys.path.insert(0, "/path/to/server/work/a1b_eval/scripts/baselines")
    from supervised_mlp import SupervisedBandwidthMLP
    dev = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    for sd in (0, 1, 2):
        ck = MLP_ROOT / f"seed{sd}" / "checkpoint_final.pt"
        pay = torch.load(ck, map_location="cpu", weights_only=False)
        m = SupervisedBandwidthMLP().to(dev)
        m.load_state_dict(pay["state_dict"] if "state_dict" in pay else pay, strict=True)
        m.eval()
        t0 = time.time()
        for i, (d, p) in enumerate(fl):
            obs = np.asarray(json.load(open(p))["observations"], dtype=np.float32)
            with torch.inference_mode():
                pr = m(torch.from_numpy(obs).to(dev)).squeeze(-1).cpu().numpy()
            preds[f"MLP_seed{sd}"][i] = pr.astype(np.float32)
        print(f"  mlp seed{sd} done {(time.time()-t0)/60:.1f} min", flush=True)

    import onnxruntime as ort
    sess, shape = {}, {}
    for n, path in ONNX.items():
        s = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        sess[n], shape[n] = s, tuple(s.get_inputs()[1].shape)
    t0 = time.time()
    for i, (d, p) in enumerate(fl):
        obs = np.asarray(json.load(open(p))["observations"], dtype=np.float32)
        for n, s in sess.items():
            h = np.zeros(shape[n], dtype=np.float32); c = np.zeros(shape[n], dtype=np.float32)
            pr = np.empty(obs.shape[0], dtype=np.float32)
            for t in range(obs.shape[0]):
                o, h, c = s.run(None, {"obs": obs[t:t + 1].reshape(1, 1, -1),
                                       "hidden_states": h, "cell_states": c})
                pr[t] = o[0, 0, 0]
            preds[n][i] = pr
        if (i + 1) % 100 == 0:
            print(f"  onnx {i+1}/{len(fl)}  {(time.time()-t0)/60:.1f} min", flush=True)

    off = np.zeros(len(fl) + 1, dtype=np.int64)
    off[1:] = np.cumsum(nsteps)
    save = {"keys": np.array(keys), "dirs": np.array([d for d, _ in fl]),
            "offsets": off, "nsteps": nsteps,
            "feat_short": np.concatenate(feats, axis=0),
            "truth_mbps": np.concatenate(truths, axis=0),
            "arms": np.array(ARMS)}
    for a in ARMS:
        arr = np.concatenate(preds[a], axis=0)
        if a in ONNX:
            arr = arr / 1e6
        save[f"pred__{a}"] = arr.astype(np.float32)
    np.savez_compressed(OUT / "perstep.npz", **save)

    sys.path.insert(0, "/path/to/server/work/a1b_eval")
    from eval_metrics import mse as _mse, over as _over, under as _under, clipped_relative_error as _err
    check = []
    for i in range(len(fl)):
        s, e = off[i], off[i + 1]
        tr = save["truth_mbps"][s:e].astype(np.float64)
        for a in ARMS:
            pr = save[f"pred__{a}"][s:e].astype(np.float64)
            check.append({"arm": a, "dir": save["dirs"][i], "file": os.path.basename(keys[i]),
                          "mse": float(_mse(pr, tr)), "over": float(_over(pr, tr)),
                          "under": float(_under(pr, tr)), "err": float(_err(pr, tr))})
    (OUT / "recheck_per_file.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in check), encoding="utf-8")

    (OUT / "DONE.json").write_text(json.dumps(
        {"n_files": len(fl), "total_steps": int(nsteps.sum()), "arms": ARMS,
         "npz_bytes": (OUT / "perstep.npz").stat().st_size}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print("complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
