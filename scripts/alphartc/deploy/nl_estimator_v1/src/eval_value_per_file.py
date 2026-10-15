"""Evaluate one controlled actor checkpoint and retain file-level paired metrics."""

import argparse
import datetime as dt
import glob
import importlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch


ap = argparse.ArgumentParser()
ap.add_argument("--code-dir", required=True)
ap.add_argument("--scen", required=True)
ap.add_argument("--ckpt", required=True)
ap.add_argument("--device", default="cuda:1")
ap.add_argument("--chunk", type=int, default=256)
ap.add_argument("--tag", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument(
    "--scenario-dir",
    action="append",
    default=[],
    metavar="LABEL=RELATIVE_DIR",
    help="override the default three-scenario layout; may be repeated",
)
args = ap.parse_args()


def mse(x, y):
    return np.nanmean(np.asarray([(a - b) ** 2 for a, b in zip(x, y)], dtype=np.float32))


def over(x, y):
    return np.nanmean(
        np.asarray([max((a - b) / b, np.float32(0)) for a, b in zip(x.flat, y.flat)], dtype=np.float32)
    )


def under(x, y):
    return np.nanmean(
        np.asarray([max(np.float32(0), (b - a) / b) for a, b in zip(x.flat, y.flat)], dtype=np.float32)
    )


def clipped_relative_error(x, y):
    return np.nanmean(
        np.asarray([min(1, np.float32(abs(a - b) / b)) for a, b in zip(x.flat, y.flat)], dtype=np.float32)
    )


def main():
    code_dir = str(Path(args.code_dir).resolve())
    sys.path.insert(0, code_dir)
    estimator = importlib.import_module("estimator")
    actor_class = estimator.bwe_agent
    device = torch.device(args.device)

    model = actor_class(20, 150, 1, device)
    state = torch.load(args.ckpt, map_location="cpu")
    model.load_state_dict(state, strict=True)
    model.eval()

    if args.scenario_dir:
        scenarios = {}
        for spec in args.scenario_dir:
            label, relative_dir = spec.split("=", 1)
            scenarios[label] = sorted(glob.glob(f"{args.scen}/{relative_dir}/*.json"))
    else:
        scenarios = {
            "High BW": sorted(glob.glob(f"{args.scen}/high_bw_call/*.json")),
            "Low BW": sorted(glob.glob(f"{args.scen}/low_bw_call/*.json")),
            "Fluctuating": sorted(glob.glob(f"{args.scen}/high_fluctuating_bw/*.json"))
            + sorted(glob.glob(f"{args.scen}/low_fluctuating_bw/*.json")),
        }
    if not scenarios or any(not paths for paths in scenarios.values()):
        raise RuntimeError(f"one or more scenario groups are empty: {[(k, len(v)) for k, v in scenarios.items()]}")

    rows = []
    started = time.time()
    for scenario, paths in scenarios.items():
        if args.limit:
            paths = paths[: args.limit]
        for index, path in enumerate(paths):
            with open(path, encoding="utf-8") as handle:
                call = json.load(handle)
            obs = np.asarray(call["observations"], dtype=np.float32)
            truth = np.asarray(call["true_capacity"], dtype=np.float32) / 1e6
            predictions = []
            with torch.inference_mode():
                for start in range(0, len(obs), args.chunk):
                    x = torch.from_numpy(obs[start : start + args.chunk]).to(device)
                    pred, _ = model(x)
                    predictions.append(pred.reshape(-1).float().cpu().numpy())
            pred = np.concatenate(predictions).astype(np.float32) / 1e6
            if len(pred) != len(truth):
                raise RuntimeError(f"prediction length mismatch for {path}: {len(pred)} != {len(truth)}")
            relative = os.path.relpath(path, args.scen)
            rows.append(
                {
                    "file": relative,
                    "scenario": scenario,
                    "n_steps": int(len(truth)),
                    "mse": float(mse(pred, truth)),
                    "over": float(over(pred, truth)),
                    "under": float(under(pred, truth)),
                    "err": float(clipped_relative_error(pred, truth)),
                }
            )
            if (index + 1) % 25 == 0 or index + 1 == len(paths):
                print(
                    f"[{dt.datetime.now():%H:%M:%S}] {scenario} {index + 1}/{len(paths)} "
                    f"elapsed={(time.time() - started) / 60:.1f} min",
                    flush=True,
                )

    summaries = {}
    for scenario in scenarios:
        subset = [row for row in rows if row["scenario"] == scenario]
        summaries[scenario] = {
            "n": len(subset),
            **{
                metric: float(np.mean([row[metric] for row in subset]))
                for metric in ["mse", "over", "under", "err"]
            },
        }
    macro_mse = float(np.mean([value["mse"] for value in summaries.values()]))
    micro_mse = float(np.mean([row["mse"] for row in rows]))
    output = {
        "tag": args.tag,
        "created_at": dt.datetime.now().astimezone().isoformat(),
        "code_dir": code_dir,
        "checkpoint": str(Path(args.ckpt).resolve()),
        "checkpoint_size": os.path.getsize(args.ckpt),
        "scenario_root": str(Path(args.scen).resolve()),
        "chunk": args.chunk,
        "limit": args.limit,
        "summaries": summaries,
        "macro_mse": macro_mse,
        "micro_mse": micro_mse,
        "files": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"tag": args.tag, "macro_mse": macro_mse, "micro_mse": micro_mse}, ensure_ascii=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
