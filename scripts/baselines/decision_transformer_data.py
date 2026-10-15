#!/usr/bin/env python3
"""Data loading for the Decision Transformer baseline: one call file at a time; no context window crosses two calls."""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch
from torch.utils.data import Dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lib.encoder0 import as_numpy as encoder0_numpy  # noqa: E402


REQUIRED_FIELDS = (
    "observations",
    "bandwidth_predictions",
    "true_capacity",
    "video_quality",
    "audio_quality",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _one_dimensional(data: Any, name: str) -> np.ndarray:
    array = np.asarray(data, dtype=np.float64).reshape(-1)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def validate_session(data: dict[str, Any], source: str = "session") -> int:
    missing = [name for name in REQUIRED_FIELDS if name not in data]
    if missing:
        raise ValueError(f"{source}: missing fields {missing}")
    observations = np.asarray(data["observations"])
    if observations.ndim != 2 or observations.shape[1] != 150:
        raise ValueError(f"{source}: observations shape {observations.shape}, expected [T, 150]")
    length = len(observations)
    if length == 0:
        raise ValueError(f"{source}: empty session")
    for field in REQUIRED_FIELDS[1:]:
        if len(_one_dimensional(data[field], field)) != length:
            raise ValueError(f"{source}: {field} length differs from observations")
    return length


def build_manifest(
    source_dir: Path,
    manifest_path: Path,
    *,
    context_len: int = 20,
    limit: int = 0,
) -> dict[str, Any]:
    """Index the raw JSON call files without materializing a second trajectory dataset."""
    if context_len <= 0:
        raise ValueError("context_len must be positive")
    paths = sorted(source_dir.glob("*.json"))
    if limit > 0:
        paths = paths[:limit]
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            raw = path.read_bytes()
            data = json.loads(raw)
            length = validate_session(data, str(path))
            entries.append(
                {
                    "session_id": path.name,
                    "path": str(path.resolve()),
                    "n_steps": length,
                    "n_windows": max(0, length - context_len + 1),
                    "sha256": _sha256(raw),
                }
            )
        except Exception as exc:  # a corrupt file is listed in errors and indexing continues
            errors.append({"path": str(path.resolve()), "error": f"{type(exc).__name__}: {exc}"})

    manifest_text = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries)
    _atomic_write(manifest_path, manifest_text)
    meta = {
        "schema_version": 1,
        "source_dir": str(source_dir.resolve()),
        "context_len": context_len,
        "sessions_seen": len(paths),
        "sessions_valid": len(entries),
        "sessions_invalid": len(errors),
        "total_steps": sum(int(entry["n_steps"]) for entry in entries),
        "total_windows": sum(int(entry["n_windows"]) for entry in entries),
        "manifest_sha256": _sha256(manifest_text.encode()),
        "reward": "lambda*(-abs(action-capacity)/capacity)+(1-lambda)*(0.8*video+0.2*audio); no clipping",
        "capacity_policy": "true_capacity is used only to derive reward and evaluation labels",
        "errors": errors,
    }
    _atomic_write(manifest_path.with_suffix(manifest_path.suffix + ".meta.json"), json.dumps(meta, indent=2) + "\n")
    return meta


def _fill_quality(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array, dtype=np.float64).copy()
    finite = np.isfinite(array)
    fill = float(np.mean(array[finite])) if finite.any() else 0.0
    array[~finite] = fill
    return array


def hcq_reward(
    actions_bps: np.ndarray,
    capacities_bps: np.ndarray,
    video_quality: np.ndarray,
    audio_quality: np.ndarray,
    *,
    lambda_mre: float = 0.4,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the HCQ reward of Eq. (1) with weight lambda_mre; the relative-error term is not capped."""
    if not 0.0 <= lambda_mre <= 1.0:
        raise ValueError("lambda_mre must be in [0, 1]")
    action = np.asarray(actions_bps, dtype=np.float64).reshape(-1)
    capacity = np.asarray(capacities_bps, dtype=np.float64).reshape(-1)
    video = _fill_quality(np.asarray(video_quality, dtype=np.float64).reshape(-1))
    audio = _fill_quality(np.asarray(audio_quality, dtype=np.float64).reshape(-1))
    if not (len(action) == len(capacity) == len(video) == len(audio)):
        raise ValueError("reward arrays have different lengths")
    valid = np.isfinite(action) & np.isfinite(capacity) & (capacity > 0)
    reward = np.zeros(len(action), dtype=np.float64)
    relative_error = np.zeros(len(action), dtype=np.float64)
    relative_error[valid] = np.abs(action[valid] - capacity[valid]) / capacity[valid]
    quality = 0.8 * video + 0.2 * audio
    reward[valid] = lambda_mre * (-relative_error[valid]) + (1.0 - lambda_mre) * quality[valid]
    return reward.astype(np.float32), valid


def discounted_return_to_go(rewards: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    if not 0.0 < gamma <= 1.0:
        raise ValueError("gamma must be in (0, 1]")
    rewards = np.asarray(rewards, dtype=np.float32).reshape(-1)
    result = np.empty_like(rewards)
    running = 0.0
    for index in range(len(rewards) - 1, -1, -1):
        running = float(rewards[index]) + gamma * running
        result[index] = running
    return result


@dataclass
class SessionArrays:
    states: np.ndarray
    actions_mbps: np.ndarray
    capacities_mbps: np.ndarray
    rewards: np.ndarray
    returns_to_go: np.ndarray
    valid: np.ndarray


class SessionWindowDataset(Dataset):
    """Map-style full-context windows that never cross a call boundary."""

    def __init__(
        self,
        manifest_path: Path,
        *,
        context_len: int | None = None,
        lambda_mre: float = 0.4,
        gamma: float = 1.0,
        cache_sessions: int = 2,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.entries = [json.loads(line) for line in self.manifest_path.read_text().splitlines() if line.strip()]
        meta_path = self.manifest_path.with_suffix(self.manifest_path.suffix + ".meta.json")
        meta = json.loads(meta_path.read_text())
        self.context_len = int(context_len or meta["context_len"])
        if self.context_len <= 0:
            raise ValueError("context_len must be positive")
        if context_len is not None and context_len != int(meta["context_len"]):
            raise ValueError("context_len differs from the frozen manifest")
        self.lambda_mre = lambda_mre
        self.gamma = gamma
        self.cache_sessions = max(1, int(cache_sessions))
        self._cache: OrderedDict[int, SessionArrays] = OrderedDict()
        self.window_counts = [max(0, int(entry["n_steps"]) - self.context_len + 1) for entry in self.entries]
        self.cumulative = np.cumsum(self.window_counts, dtype=np.int64)
        self.scale = encoder0_numpy(dtype=np.float32).reshape(1, 150)

    def __len__(self) -> int:
        return int(self.cumulative[-1]) if len(self.cumulative) else 0

    def locate(self, index: int) -> tuple[int, int]:
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError(index)
        session_index = bisect.bisect_right(self.cumulative.tolist(), index)
        previous = int(self.cumulative[session_index - 1]) if session_index else 0
        start = index - previous
        if start + self.context_len > int(self.entries[session_index]["n_steps"]):
            raise AssertionError("window crosses a session boundary")
        return session_index, start

    def _load(self, session_index: int) -> SessionArrays:
        if session_index in self._cache:
            arrays = self._cache.pop(session_index)
            self._cache[session_index] = arrays
            return arrays
        entry = self.entries[session_index]
        path = Path(entry["path"])
        raw = path.read_bytes()
        if _sha256(raw) != entry["sha256"]:
            raise RuntimeError(f"source session changed after manifest creation: {path}")
        data = json.loads(raw)
        validate_session(data, str(path))
        states_raw = np.asarray(data["observations"], dtype=np.float32)
        actions_bps = _one_dimensional(data["bandwidth_predictions"], "bandwidth_predictions")
        capacities_bps = _one_dimensional(data["true_capacity"], "true_capacity")
        rewards, valid = hcq_reward(
            actions_bps,
            capacities_bps,
            _one_dimensional(data["video_quality"], "video_quality"),
            _one_dimensional(data["audio_quality"], "audio_quality"),
            lambda_mre=self.lambda_mre,
        )
        finite_states = np.isfinite(states_raw).all(axis=1)
        finite_actions = np.isfinite(actions_bps)
        valid &= finite_states & finite_actions
        # NaN * 0 is still NaN, so invalid inputs and labels are set to 0; only steps with
        # valid=True enter the loss and the metrics.
        states = np.nan_to_num(states_raw, nan=0.0, posinf=0.0, neginf=0.0)
        safe_actions_bps = np.where(finite_actions, actions_bps, 0.0)
        safe_capacities_bps = np.where(
            np.isfinite(capacities_bps) & (capacities_bps > 0), capacities_bps, 0.0
        )
        arrays = SessionArrays(
            states=states,
            actions_mbps=(safe_actions_bps / 1_000_000.0).astype(np.float32),
            capacities_mbps=(safe_capacities_bps / 1_000_000.0).astype(np.float32),
            rewards=rewards,
            returns_to_go=discounted_return_to_go(rewards, self.gamma),
            valid=valid,
        )
        self._cache[session_index] = arrays
        while len(self._cache) > self.cache_sessions:
            self._cache.popitem(last=False)
        return arrays

    def __getitem__(self, index: int) -> dict[str, Any]:
        session_index, start = self.locate(index)
        stop = start + self.context_len
        arrays = self._load(session_index)
        states = np.ascontiguousarray(arrays.states[start:stop] * self.scale)
        action_targets = np.ascontiguousarray(arrays.actions_mbps[start:stop, None])
        previous_actions = np.zeros((self.context_len, 1), dtype=np.float32)
        if start == 0:
            previous_actions[1:, 0] = arrays.actions_mbps[start : stop - 1]
        else:
            previous_actions[:, 0] = arrays.actions_mbps[start - 1 : stop - 1]
        model_inputs = {
            "states": torch.from_numpy(states),
            # Only action_{t-1} is aligned with state_t, so no input carries the current action.
            "previous_actions": torch.from_numpy(previous_actions),
            "returns_to_go": torch.from_numpy(
                np.ascontiguousarray(arrays.returns_to_go[start:stop, None])
            ),
            "timesteps": torch.arange(start, stop, dtype=torch.long),
            "attention_mask": torch.ones(self.context_len, dtype=torch.bool),
        }
        labels = {
            "action_targets": torch.from_numpy(action_targets),
            "target_mask": torch.from_numpy(np.ascontiguousarray(arrays.valid[start:stop])),
            "true_capacity_mbps": torch.from_numpy(
                np.ascontiguousarray(arrays.capacities_mbps[start:stop, None])
            ),
            "rewards": torch.from_numpy(np.ascontiguousarray(arrays.rewards[start:stop, None])),
        }
        return {
            "model_inputs": model_inputs,
            "labels": labels,
            "meta": {
                "session_id": self.entries[session_index]["session_id"],
                "start": start,
                "stop": stop,
            },
        }


def collate_dt_batch(samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    samples = list(samples)
    if not samples:
        raise ValueError("cannot collate an empty batch")
    return {
        "model_inputs": {
            key: torch.stack([sample["model_inputs"][key] for sample in samples])
            for key in samples[0]["model_inputs"]
        },
        "labels": {
            key: torch.stack([sample["labels"][key] for sample in samples])
            for key in samples[0]["labels"]
        },
        "meta": [sample["meta"] for sample in samples],
    }


def assert_disjoint_manifests(first: Path, second: Path) -> None:
    def hashes(path: Path) -> set[str]:
        return {json.loads(line)["sha256"] for line in path.read_text().splitlines() if line.strip()}

    overlap = hashes(first) & hashes(second)
    if overlap:
        raise ValueError(f"train/evaluation manifests overlap by {len(overlap)} content hashes")
