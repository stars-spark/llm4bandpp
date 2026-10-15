#!/usr/bin/env python3
"""Per-call macro/micro evaluation for the supervised MLP baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from supervised_mlp import SupervisedBandwidthMLP


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--scenario-dir",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Evaluate an explicit scenario directory; repeat for scenario-equal macro MSE.",
    )
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--batch-size", type=int, default=4096)
    return parser.parse_args()


def scenario_for(name: str) -> str:
    lowered = name.lower()
    for scenario in ("periodic", "random", "subway", "taxi", "low", "high"):
        if scenario in lowered:
            return scenario
    return "other"


def evaluation_files(args: argparse.Namespace) -> list[tuple[str, Path]]:
    if not args.scenario_dir:
        return [(scenario_for(path.name), path) for path in sorted(args.dataset.glob("*.json"))]
    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for spec in args.scenario_dir:
        if "=" not in spec:
            raise ValueError(f"--scenario-dir must be NAME=PATH, got {spec!r}")
        name, raw = spec.split("=", 1)
        paths = sorted(Path(raw).glob("*.json"))
        if not name or not paths:
            raise ValueError(f"empty scenario or no JSON files for {spec!r}")
        for path in paths:
            if path.name in seen:
                raise ValueError(f"duplicate evaluation basename: {path.name}")
            seen.add(path.name)
            result.append((name, path))
    return result


def main() -> None:
    args = parse_args()
    device = torch.device(args.device)
    payload = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state_dict = payload["state_dict"] if "state_dict" in payload else payload
    model = SupervisedBandwidthMLP().to(device)
    model.load_state_dict(state_dict, strict=True)
    model.eval()

    rows: list[dict[str, object]] = []
    all_squared_error: list[np.ndarray] = []
    for scenario, path in evaluation_files(args):
        data = json.loads(path.read_text())
        observations = np.asarray(data["observations"], dtype=np.float32)
        truth = np.asarray(data["true_capacity"], dtype=np.float64).reshape(-1) / 1_000_000.0
        if observations.ndim != 2 or observations.shape[1] != 150 or len(observations) != len(truth):
            raise ValueError(f"invalid aligned arrays in {path}")
        predictions = []
        with torch.inference_mode():
            for start in range(0, len(observations), args.batch_size):
                batch = torch.from_numpy(observations[start : start + args.batch_size]).to(device)
                predictions.append(model(batch).squeeze(-1).cpu().numpy())
        prediction = np.concatenate(predictions).astype(np.float64)
        valid = np.isfinite(prediction) & np.isfinite(truth) & (truth > 0)
        prediction, truth = prediction[valid], truth[valid]
        error = prediction - truth
        squared = error**2
        all_squared_error.append(squared)
        row = {
            "file": path.name,
            "scenario": scenario,
            "n": int(len(truth)),
            "mse": float(np.mean(squared)),
            "mae": float(np.mean(np.abs(error))),
            "over_ratio": float(np.mean(error > 0)),
            "under_ratio": float(np.mean(error < 0)),
            "mean_relative_error": float(np.mean(np.abs(error) / truth)),
        }
        rows.append(row)

    if not rows:
        raise ValueError(f"no JSON sessions found under {args.dataset}")
    file_macro_mse = float(np.mean([float(row["mse"]) for row in rows]))
    micro_mse = float(np.mean(np.concatenate(all_squared_error)))
    scenarios: dict[str, dict[str, float | int]] = {}
    for name in sorted({str(row["scenario"]) for row in rows}):
        selected = [row for row in rows if row["scenario"] == name]
        scenarios[name] = {
            "files": len(selected),
            "macro_mse": float(np.mean([float(row["mse"]) for row in selected])),
            "macro_mre": float(
                np.mean([float(row["mean_relative_error"]) for row in selected])
            ),
        }
    # The paper's macro MSE weights the three scenarios equally. File weighting
    # would let the 469-file low-BW group dominate the 77-file high-BW group.
    macro_mse = float(np.mean([float(value["macro_mse"]) for value in scenarios.values()]))
    report = {
        "checkpoint": str(args.checkpoint.resolve()),
        "dataset": str(args.dataset.resolve()),
        "files": len(rows),
        "macro_mse": macro_mse,
        "file_macro_mse": file_macro_mse,
        "micro_mse": micro_mse,
        "scenarios": scenarios,
        "per_file": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("files", "macro_mse", "micro_mse")}, indent=2))


if __name__ == "__main__":
    main()
