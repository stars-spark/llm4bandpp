#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered experiment decision-transformer-eval-v1: per-step predictions of the Decision Transformer baseline (three seeds) on the 870 validation calls.
Inference: 20-step context; states multiplied by the input scaling vector; the previous action is the model's own previous output (0 at the first step);
return-to-go RTG_t = r* x max(H - t, 1), H the median length of a training call, r* the 90th (also 50th) percentile of the per-step mean HCQ reward of training calls.
Rewards are not observable at deployment, so RTG is not reduced by realized reward. Runs on CPU (about 3.2 M parameters); file order matches arb_perstep_dump_v1.
Writes DT_s{seed}_{p90,p50}.npz (per-step predictions in Mbit/s), summary.json (per-scenario MSE) and train_reward_stats.json to --out.
Usage: python3 scripts/baselines/dt_perstep_dump_v1.py --val DIR --train DIR --ckpt-root DIR --out DIR [--limit N for a smoke run]
"""
import argparse, glob, json, sys, time
from pathlib import Path
import numpy as np, torch
sys.path.insert(0, ".")
from scripts.baselines.decision_transformer import BandwidthDecisionTransformer  # noqa: E402
from scripts.baselines.decision_transformer_data import hcq_reward  # noqa: E402
from scripts.lib.encoder0 import ENCODER0  # noqa: E402
ap = argparse.ArgumentParser(); ap.add_argument("--val", default="/path/to/llm4band_conference/validation/prepare_scenario"); ap.add_argument("--train", default="/path/to/server/datasets/dt_stage_v1/training_dataset")
ap.add_argument("--ckpt-root", default="/path/to/server/outputs/dt_baseline_3seed_gpu_server_1_v1"); ap.add_argument("--out", default="/path/to/server/outputs/dt_perstep_dump_v1"); ap.add_argument("--threads", type=int, default=16)
ap.add_argument("--limit", type=int, default=0); ap.add_argument("--stats-sessions", type=int, default=1000); a = ap.parse_args()
torch.set_num_threads(a.threads); OUT = Path(a.out); OUT.mkdir(parents=True, exist_ok=True); K = 20; DIRS = ["high_bw_call", "low_bw_call", "high_fluctuating_bw", "low_fluctuating_bw"]; SCALE = np.asarray(ENCODER0, np.float32); assert SCALE.shape == (150,)


def train_stats():
    p = OUT / "train_reward_stats.json"
    if p.exists(): return json.loads(p.read_text())
    fl = sorted(glob.glob(f"{a.train}/*.json")); rng = np.random.default_rng(20260919); pick = [fl[i] for i in sorted(rng.choice(len(fl), size=min(a.stats_sessions, len(fl)), replace=False))]; means, lens = [], []
    for f in pick:
        d = json.load(open(f)); r, v = hcq_reward(np.asarray(d["bandwidth_predictions"], float), np.asarray(d["true_capacity"], float), np.asarray(d["video_quality"], float), np.asarray(d["audio_quality"], float), lambda_mre=0.4)
        if v.any(): means.append(float(r[v].mean())); lens.append(len(r))
    s = {"n_sessions": len(means), "n_train_files": len(fl), "H_median_len": int(np.median(lens)), "r_p90": float(np.percentile(means, 90)), "r_p50": float(np.percentile(means, 50)), "r_min": float(np.min(means)), "r_max": float(np.max(means))}
    p.write_text(json.dumps(s, indent=2)); return s


def rollout(model, S_list, r_star, H):
    n = len(S_list); lens = np.array([len(s) for s in S_list]); T = int(lens.max()); acts = [np.zeros(L, np.float32) for L in lens]; prev = [np.zeros(L, np.float32) for L in lens]
    with torch.inference_mode():
        for t in range(T):
            idx = np.where(lens > t)[0]; s0 = max(0, t - K + 1); k = t - s0 + 1
            st = torch.from_numpy(np.stack([S_list[i][s0:t + 1] for i in idx])); pa = torch.from_numpy(np.stack([prev[i][s0:t + 1] for i in idx]))[..., None]
            # RTG is r* times the remaining horizon, floored at one step; it never depends on observed reward.
            ts = torch.arange(s0, t + 1).unsqueeze(0).expand(len(idx), -1); rtg = (r_star * torch.clamp(H - ts.float(), min=1.0))[..., None]
            y = model(states=st, previous_actions=pa, returns_to_go=rtg, timesteps=ts, attention_mask=torch.ones(len(idx), k, dtype=torch.bool))[:, -1, 0].numpy()
            for j, i in enumerate(idx):
                acts[i][t] = y[j]
                # The model's own output becomes the previous action of the next step.
                if t + 1 < lens[i]: prev[i][t + 1] = y[j]
            if t % 500 == 0: print(f"    step {t}/{T} present file {len(idx)}", flush=True)
    return acts


def main():
    st = train_stats(); print("training set reward statistics", st, flush=True); fl = [(d, p) for d in DIRS for p in sorted(glob.glob(f"{a.val}/{d}/*.json"))]
    if a.limit: fl = fl[:: max(1, len(fl) // a.limit)][:a.limit]
    S_list, TR, keys = [], [], []
    for d, p in fl:
        c = json.load(open(p)); S_list.append(np.nan_to_num(np.asarray(c["observations"], np.float32), nan=0.0, posinf=0.0, neginf=0.0) * SCALE); TR.append(np.asarray(c["true_capacity"], np.float32) / 1e6); keys.append(f"{d}/{Path(p).name}")
    summ = {"stats": st, "files": len(fl), "runs": {}}; t0 = time.time()
    for seed in (0, 1, 2):
        m = BandwidthDecisionTransformer(); ck = torch.load(f"{a.ckpt_root}/seed{seed}/checkpoint_final.pt", map_location="cpu"); m.load_state_dict(ck["state_dict"], strict=True); m.eval()
        for tag, r in (("p90", st["r_p90"]), ("p50", st["r_p50"])):
            print(f"  seed {seed} target {tag} r*={r:.4f}", flush=True); acts = rollout(m, S_list, r, st["H_median_len"]); pred = np.concatenate(acts); assert np.isfinite(pred).all()
            mse = {}
            for (d, _), a_, tr in zip(fl, acts, TR): mse.setdefault(d, []).append(float(np.nanmean((a_ - tr) ** 2)))
            sc = {"High BW": mse.get("high_bw_call", []), "Low BW": mse.get("low_bw_call", []), "Fluctuating": mse.get("high_fluctuating_bw", []) + mse.get("low_fluctuating_bw", [])}
            name = f"DT_s{seed}_{tag}"; summ["runs"][name] = {k: float(np.mean(v)) for k, v in sc.items() if v}
            np.savez_compressed(OUT / (f"{name}.npz" if not a.limit else f"smoke_{name}.npz"), pred=pred, lens=np.asarray([len(x) for x in acts]), keys=np.asarray(keys)); print("   ", summ["runs"][name], f"{(time.time()-t0)/60:.1f} min", flush=True)
    (OUT / ("summary.json" if not a.limit else "smoke.json")).write_text(json.dumps(summ, ensure_ascii=False, indent=2))
    if not a.limit: (OUT / "DONE").write_text(time.strftime("%F %T"))


if __name__ == "__main__":
    main()
