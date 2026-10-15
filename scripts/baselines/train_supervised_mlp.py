#!/usr/bin/env python3
"""Train the supervised MLP baseline on a training pickle in the format of MRE_4.pickle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import random
import time
import resource
from pathlib import Path

import numpy as np
import torch

from supervised_mlp import SupervisedBandwidthMLP, trainable_parameter_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pickle", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=50_000)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--save-every", type=int, default=0)
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_arrays(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    observations = np.asarray(payload["observations"])
    target_key = "true_capacitys" if "true_capacitys" in payload else "true_capacity"
    targets_bps = np.asarray(payload[target_key]).reshape(-1)
    if observations.ndim != 2 or observations.shape[1] != 150:
        raise ValueError(f"observations shape is {observations.shape}, expected [N, 150]")
    if len(observations) != len(targets_bps):
        raise ValueError("observation and capacity lengths differ")
    valid = np.flatnonzero(
        np.isfinite(observations).all(axis=1)
        & np.isfinite(targets_bps)
        & (targets_bps > 0)
    )
    if len(valid) == 0:
        raise ValueError("no finite positive training labels")
    return observations, targets_bps, valid, target_key


def atomic_torch_save(payload: object, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, tmp)
    os.replace(tmp, path)


def main() -> None:
    args = parse_args()
    process_started = time.time()
    args.out.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    observations, targets_bps, valid, target_key = load_arrays(args.pickle)
    data_load_s = time.time() - process_started
    rng = np.random.default_rng(args.seed)
    device = torch.device(args.device)
    model = SupervisedBandwidthMLP().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = torch.nn.MSELoss()
    metrics_path = args.out / "train_metrics.jsonl"
    started = time.time()

    config = {
        "architecture": "150-512-512-256-1",
        "activation": "ReLU hidden; Softplus output",
        "input": "raw 150-value observation; exact scripts/lib/encoder0.py scaling inside model",
        "target": "capacity label aligned with the same decision tuple, converted from bps to Mbps",
        "target_key": target_key,
        "seed": args.seed,
        "steps": args.steps,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "device": str(device),
        "valid_samples": int(len(valid)),
        "parameter_count": trainable_parameter_count(model),
        "source_pickle": str(args.pickle.resolve()),
        "source_sha256": file_sha256(args.pickle),
        "data_load_s": data_load_s,
    }
    (args.out / "config.json").write_text(json.dumps(config, indent=2) + "\n")

    first_loss = None
    final_loss = None
    with metrics_path.open("w") as metrics:
        for step in range(1, args.steps + 1):
            selected = valid[rng.integers(0, len(valid), size=args.batch_size)]
            batch_x = torch.from_numpy(np.asarray(observations[selected], dtype=np.float32)).to(device)
            batch_y = torch.from_numpy(
                np.asarray(targets_bps[selected] / 1_000_000.0, dtype=np.float32)
            ).reshape(-1, 1).to(device)
            prediction = model(batch_x)
            loss = loss_fn(prediction, batch_y)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"non-finite loss at step {step}")
            if first_loss is None:
                first_loss = float(loss.detach())
            final_loss = float(loss.detach())
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

            if step == 1 or step % args.log_every == 0 or step == args.steps:
                row = {
                    "step": step,
                    "loss_mbps2": float(loss.detach()),
                    "elapsed_s": time.time() - started,
                }
                metrics.write(json.dumps(row) + "\n")
                metrics.flush()
            if args.save_every and step % args.save_every == 0:
                atomic_torch_save(
                    {"state_dict": model.state_dict(), "config": config, "step": step},
                    args.out / f"checkpoint_step_{step}.pt",
                )

    checkpoint = args.out / "checkpoint_final.pt"
    atomic_torch_save(
        {"state_dict": model.state_dict(), "config": config, "step": args.steps}, checkpoint
    )
    marker = {
        "status": "complete",
        "checkpoint": str(checkpoint.resolve()),
        "checkpoint_sha256": file_sha256(checkpoint),
        "elapsed_s": time.time() - started,
        "total_elapsed_s": time.time() - process_started,
        "data_load_s": data_load_s,
        "first_loss_mbps2": first_loss,
        "final_loss_mbps2": final_loss,
        "checkpoint_bytes": checkpoint.stat().st_size,
        "max_cuda_bytes": torch.cuda.max_memory_allocated(device) if device.type == "cuda" else 0,
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    tmp_marker = args.out / "train_complete.json.tmp"
    tmp_marker.write_text(json.dumps(marker, indent=2) + "\n")
    os.replace(tmp_marker, args.out / "train_complete.json")


if __name__ == "__main__":
    main()
