#!/usr/bin/env python3
"""Train the compact Decision Transformer from a frozen manifest of call files."""

from __future__ import annotations

import argparse
import json
import os
import time
import resource
from pathlib import Path

import numpy as np
import torch

from decision_transformer import BandwidthDecisionTransformer, masked_action_mse
from decision_transformer_data import SessionWindowDataset, collate_dt_batch


def shuffled_epoch_indices(
    dataset: SessionWindowDataset, rng: np.random.Generator
):
    """Visit every window once while keeping each call's reads contiguous."""
    for session in rng.permutation(len(dataset.entries)):
        count = dataset.window_counts[session]
        if count <= 0:
            continue
        lower = int(dataset.cumulative[session - 1]) if session else 0
        for start in rng.permutation(count):
            yield lower + int(start)


def streaming_batches(
    dataset: SessionWindowDataset,
    batch_size: int,
    rng: np.random.Generator,
):
    """Yield fixed-size batches; raw call files are parsed once per epoch."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    pending = []
    while True:
        for index in shuffled_epoch_indices(dataset, rng):
            pending.append(dataset[index])
            if len(pending) == batch_size:
                yield collate_dt_batch(pending)
                pending.clear()


def move_inputs(batch: dict, device: torch.device) -> tuple[dict, dict]:
    inputs = {key: value.to(device) for key, value in batch["model_inputs"].items()}
    labels = {key: value.to(device) for key, value in batch["labels"].items()}
    return inputs, labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=50_000)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--log-every", type=int, default=20)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = torch.device(args.device)
    dataset = SessionWindowDataset(args.manifest, context_len=20, cache_sessions=2)
    batches = streaming_batches(dataset, args.batch_size, rng)
    model = BandwidthDecisionTransformer().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    metrics = args.output / "train_metrics.jsonl"
    started = time.time()
    first_loss = None
    final_loss = None
    try:
        with metrics.open("w") as stream:
            for step in range(1, args.steps + 1):
                batch = next(batches)
                inputs, labels = move_inputs(batch, device)
                prediction = model(**inputs)
                loss = masked_action_mse(
                    prediction, labels["action_targets"], labels["target_mask"]
                )
                if not torch.isfinite(loss):
                    raise FloatingPointError(f"non-finite loss at step {step}")
                if first_loss is None:
                    first_loss = float(loss.detach())
                final_loss = float(loss.detach())
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                if step == 1 or step % args.log_every == 0 or step == args.steps:
                    row = {
                        "step": step,
                        "loss_mbps2": float(loss.detach()),
                        "elapsed_s": time.time() - started,
                        "max_cuda_bytes": torch.cuda.max_memory_allocated(device) if device.type == "cuda" else 0,
                        "equivalent_epochs": step * args.batch_size / len(dataset),
                    }
                    stream.write(json.dumps(row) + "\n")
                    stream.flush()
        checkpoint = args.output / "checkpoint_final.pt"
        tmp = checkpoint.with_suffix(".pt.tmp")
        torch.save({"state_dict": model.state_dict(), "step": args.steps, "seed": args.seed}, tmp)
        os.replace(tmp, checkpoint)
        complete = {
            "status": "complete",
            "elapsed_s": time.time() - started,
            "checkpoint": str(checkpoint),
            "checkpoint_bytes": checkpoint.stat().st_size,
            "first_loss_mbps2": first_loss,
            "final_loss_mbps2": final_loss,
            "max_cuda_bytes": torch.cuda.max_memory_allocated(device) if device.type == "cuda" else 0,
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "equivalent_epochs": args.steps * args.batch_size / len(dataset),
        }
        marker_tmp = args.output / "TRAIN_COMPLETE.json.tmp"
        marker_tmp.write_text(json.dumps(complete, indent=2) + "\n")
        os.replace(marker_tmp, args.output / "TRAIN_COMPLETE.json")
    except Exception as exc:
        (args.output / "TRAIN_FAILED.json").write_text(
            json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, indent=2) + "\n"
        )
        raise


if __name__ == "__main__":
    main()
