#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-step export for ablation-enc-hcq-2x2-v1, written like scripts/arb/llm4bandpp_perstep_dump_v1.py: the 870 calls in the
order of arb_perstep_dump_v1, processed in chunks with no state carried between steps; output pred (Mb/s), lens and keys,
scored by the judge with the fm function of main_table_unified_v1. The four cells and the checkpoint of our earlier
version use the same script with different code directories: make_actor if the directory defines it (the four cells,
encoder chosen by BWE_ENC), otherwise that version's bwe_agent. Weights load strictly unless --nonstrict (meant only for
that checkpoint; missing and unexpected keys are counted). The per-scenario MSE printed here is for the log only.
"""
import argparse
import datetime as dt
import glob
import hashlib
import importlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

DIRS = ["high_bw_call", "low_bw_call", "high_fluctuating_bw", "low_fluctuating_bw"]
SCEN = {"high_bw_call": "High BW", "low_bw_call": "Low BW",
        "high_fluctuating_bw": "Fluctuating", "low_fluctuating_bw": "Fluctuating"}

ap = argparse.ArgumentParser()
ap.add_argument("--code-dir", required=True)
ap.add_argument("--ckpt", required=True)
ap.add_argument("--scen", required=True)
ap.add_argument("--device", required=True)
ap.add_argument("--chunk", type=int, default=512)
ap.add_argument("--limit", type=int, default=0, help="Only export the first N calls, for smoke test")
ap.add_argument("--out", required=True, help="Output .npz; the .json with the same name is the summary")
ap.add_argument("--nonstrict", action="store_true")
a = ap.parse_args()


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} already exists, refusing to overwrite")
    code_dir = str(Path(a.code_dir).resolve())
    sys.path.insert(0, code_dir)
    os.chdir(code_dir)
    est = importlib.import_module("estimator")
    dev = torch.device(a.device)
    if hasattr(est, "make_actor"):
        m = est.make_actor(20, 150, 1, dev)
        factory = f"make_actor:{os.environ.get('BWE_ENC')}"
    else:
        m = est.bwe_agent(20, 150, 1, dev)
        factory = "bwe_agent"
    sd = torch.load(a.ckpt, map_location="cpu")
    missing, unexpected = m.load_state_dict(sd, strict=not a.nonstrict)
    del sd
    m.eval()
    print(f"factory {factory} missing {len(missing)} unexpected {len(unexpected)}", flush=True)

    fl = [(d, p) for d in DIRS for p in sorted(glob.glob(f"{a.scen}/{d}/*.json"))]
    if not a.limit and len(fl) != 870:
        raise SystemExit(f"The scenario directory should have 870 calls, got {len(fl)}")
    if a.limit:
        fl = fl[:a.limit]
    preds, lens, keys, by = [], [], [], {}
    t0 = time.time()
    if dev.type == "cuda":
        torch.cuda.reset_peak_memory_stats(dev)
    for i, (d, p) in enumerate(fl):
        c = json.load(open(p))
        obs = np.asarray(c["observations"], np.float32)
        tr = np.asarray(c["true_capacity"], np.float32) / 1e6
        o = []
        with torch.inference_mode():
            for s in range(0, len(obs), a.chunk):
                y, _ = m(torch.from_numpy(obs[s:s + a.chunk]).to(dev))
                o.append(y.reshape(-1).float().cpu().numpy())
        pr = np.concatenate(o).astype(np.float32) / 1e6
        if len(pr) != len(tr):
            raise SystemExit(f"{p} predicted length {len(pr)} does not match ground truth {len(tr)}")
        preds.append(pr)
        lens.append(len(pr))
        keys.append(f"{d}/{Path(p).name}")
        by.setdefault(SCEN[d], []).append(float(np.nanmean((pr - tr) ** 2)))
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(fl)} {(time.time() - t0) / 60:.1f} min", flush=True)
    summ = {k: float(np.mean(v)) for k, v in by.items()}
    if len(summ) == 3:
        summ["macro"] = float(np.mean([summ[k] for k in ("High BW", "Low BW", "Fluctuating")]))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".partial.npz")
    np.savez_compressed(tmp, pred=np.concatenate(preds), lens=np.asarray(lens), keys=np.asarray(keys))
    os.replace(tmp, out)
    info = {"created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "host": os.uname().nodename, "code_dir": code_dir, "factory": factory,
            "BWE_ENC": os.environ.get("BWE_ENC"), "ckpt": str(Path(a.ckpt).resolve()),
            "ckpt_sha256": sha256_file(a.ckpt), "ckpt_bytes": os.path.getsize(a.ckpt),
            "strict": not a.nonstrict, "missing_keys": len(missing), "unexpected_keys": len(unexpected),
            "scen": a.scen, "chunk": a.chunk, "limit": a.limit, "files": len(fl),
            "steps": int(sum(lens)), "mse_nanmean_by_scenario": summ,
            "minutes": round((time.time() - t0) / 60, 2),
            "peak_allocated_mib": (round(torch.cuda.max_memory_allocated(dev) / 2**20, 1)
                                   if dev.type == "cuda" else None),
            "npz": str(out), "npz_sha256": sha256_file(out)}
    out.with_suffix(".json").write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    print(json.dumps({"mse": summ, "minutes": info["minutes"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
