#!/usr/bin/env python3
"""Supervised MLP baseline with the fixed input scale vector (scripts/lib/encoder0.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from torch import nn

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lib.encoder0 import as_tensor as encoder0_tensor  # noqa: E402


class SupervisedBandwidthMLP(nn.Module):
    """Predict the capacity label associated with a 150-value observation.

    Inputs are raw observations. encoder0 is applied inside the module and stored
    as a buffer, so a checkpoint carries its own input scaling. Outputs are Mbps and constrained to be non-negative.
    """

    input_dim = 150

    def __init__(self) -> None:
        super().__init__()
        scale = encoder0_tensor(dtype=torch.float32).reshape(-1)
        if scale.numel() != self.input_dim:
            raise ValueError(f"encoder0 has {scale.numel()} values, expected 150")
        self.register_buffer("encoder0", scale)
        self.network = nn.Sequential(
            nn.Linear(150, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Linear(256, 1),
            nn.Softplus(),
        )

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        if observations.ndim < 2 or observations.shape[-1] != self.input_dim:
            raise ValueError(
                f"observations must end in dimension 150, got {tuple(observations.shape)}"
            )
        if not torch.is_floating_point(observations):
            observations = observations.float()
        scaled = observations * self.encoder0.to(dtype=observations.dtype)
        return self.network(scaled)

    @torch.inference_mode()
    def predict_bps(self, observations: torch.Tensor) -> torch.Tensor:
        return self(observations) * 1_000_000.0


def trainable_parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)

