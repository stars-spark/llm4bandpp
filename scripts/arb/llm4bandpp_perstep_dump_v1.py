#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm4bandpp-perstep-dump-v1: export the per-step predictions of the one-token LLM variant (the checkpoint of our earlier
version, actor_1240000.pt) on the 870 validation calls, in the call order of arb_perstep_dump_v1. Ran on the GPU server
from a directory holding a copy of that variant's model code; reads the conference code tree without changing it and
writes to /path/to/server/outputs/llm4bandpp_perstep_dump_v1. Steps are processed in chunks and no state is carried
between time steps, as in our reproduction evaluator.
"""
import argparse, glob, json, os, sys, time
from pathlib import Path
import numpy as np, torch
BASE = "/path/to/llm4band_conference"; SCEN = f"{BASE}/validation/prepare_scenario"
CKPT = f"{BASE}/Qwen_for_bwe/Qwen_LoRa/checkpoints_iql/IQL-qwen1.5lora-dual-MRE4-f6a2d3ee/actor_1240000.pt"
OUT = Path("/path/to/server/outputs/llm4bandpp_perstep_dump_v1"); DIRS = ["high_bw_call", "low_bw_call", "high_fluctuating_bw", "low_fluctuating_bw"]
ap = argparse.ArgumentParser(); ap.add_argument("--ckpt", default=CKPT); ap.add_argument("--device", default="cuda:0"); ap.add_argument("--chunk", type=int, default=256); ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args(); sys.path.insert(0, os.getcwd())
from estimator import bwe_agent  # noqa: E402


def main():
    OUT.mkdir(parents=True, exist_ok=True); dev = torch.device(a.device); m = bwe_agent(20, 150, 1, dev)
    missing, unexpected = m.load_state_dict(torch.load(a.ckpt, map_location="cpu"), strict=False); print("missing", len(missing), "unexpected", len(unexpected), flush=True); m.eval()
    fl = [(d, p) for d in DIRS for p in sorted(glob.glob(f"{SCEN}/{d}/*.json"))]
    if a.limit: fl = fl[:a.limit]
    preds, lens, keys, mse_by = [], [], [], {}; t0 = time.time()
    for i, (d, p) in enumerate(fl):
        c = json.load(open(p)); obs = np.asarray(c["observations"], np.float32); tr = np.asarray(c["true_capacity"], np.float32) / 1e6; out = []
        with torch.inference_mode():
            for s in range(0, len(obs), a.chunk):
                y, _ = m(torch.from_numpy(obs[s:s + a.chunk]).to(dev)); out.append(y.reshape(-1).float().cpu().numpy())
        pr = np.concatenate(out).astype(np.float32) / 1e6; assert len(pr) == len(tr)
        preds.append(pr); lens.append(len(pr)); keys.append(f"{d}/{Path(p).name}"); mse_by.setdefault(d, []).append(float(np.nanmean((pr - tr) ** 2)))
        if (i + 1) % 50 == 0: print(f"  {i+1}/{len(fl)} {(time.time()-t0)/60:.1f} min", flush=True)
    sc = {"High BW": mse_by.get("high_bw_call", []), "Low BW": mse_by.get("low_bw_call", []), "Fluctuating": mse_by.get("high_fluctuating_bw", []) + mse_by.get("low_fluctuating_bw", [])}
    summ = {k: float(np.mean(v)) for k, v in sc.items() if v}; summ["macro"] = float(np.mean(list(summ.values())))
    np.savez_compressed(OUT / ("perstep_llm4bandpp.npz" if not a.limit else "smoke.npz"), pred=np.concatenate(preds), lens=np.asarray(lens), keys=np.asarray(keys))
    (OUT / ("summary.json" if not a.limit else "smoke.json")).write_text(json.dumps({"ckpt": a.ckpt, "files": len(fl), "steps": int(sum(lens)), "mse": summ, "minutes": (time.time() - t0) / 60}, ensure_ascii=False, indent=2))
    print(json.dumps(summ), flush=True)
    if not a.limit: (OUT / "DONE").write_text(time.strftime("%F %T"))


if __name__ == "__main__":
    main()
