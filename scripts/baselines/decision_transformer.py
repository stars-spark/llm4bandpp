#!/usr/bin/env python3
"""A compact causal Decision Transformer for bandwidth actions."""

from __future__ import annotations

import torch
from torch import nn


class BandwidthDecisionTransformer(nn.Module):
    """Predict action_t from RTG_t, action_{t-1}, state_t and past tokens."""

    def __init__(
        self,
        state_dim: int = 150,
        hidden_dim: int = 256,
        layers: int = 4,
        heads: int = 8,
        dropout: float = 0.1,
        max_timestep: int = 65_536,
    ) -> None:
        super().__init__()
        if hidden_dim % heads:
            raise ValueError("hidden_dim must be divisible by heads")
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.max_timestep = max_timestep
        self.state_embedding = nn.Linear(state_dim, hidden_dim)
        self.action_embedding = nn.Linear(1, hidden_dim)
        self.return_embedding = nn.Linear(1, hidden_dim)
        half = hidden_dim // 2
        frequencies = torch.exp(
            -torch.arange(half, dtype=torch.float32)
            * (torch.log(torch.tensor(10_000.0)) / max(1, half - 1))
        )
        self.register_buffer("time_frequencies", frequencies)
        self.input_norm = nn.LayerNorm(hidden_dim)
        layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=heads,
            dim_feedforward=4 * hidden_dim,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(
            layer,
            num_layers=layers,
            norm=nn.LayerNorm(hidden_dim),
            enable_nested_tensor=False,
        )
        self.action_head = nn.Sequential(nn.Linear(hidden_dim, 1), nn.Softplus())

    def forward(
        self,
        *,
        states: torch.Tensor,
        previous_actions: torch.Tensor,
        returns_to_go: torch.Tensor,
        timesteps: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        if states.ndim != 3 or states.shape[-1] != self.state_dim:
            raise ValueError(f"states must be [B,K,{self.state_dim}]")
        batch, length, _ = states.shape
        expected_scalar = (batch, length, 1)
        if tuple(previous_actions.shape) != expected_scalar or tuple(returns_to_go.shape) != expected_scalar:
            raise ValueError("previous_actions and returns_to_go must be [B,K,1]")
        if tuple(timesteps.shape) != (batch, length) or tuple(attention_mask.shape) != (batch, length):
            raise ValueError("timesteps and attention_mask must be [B,K]")
        if torch.any(timesteps < 0) or torch.any(timesteps >= self.max_timestep):
            raise ValueError("timestep is outside the embedding table")

        angles = timesteps.to(states.dtype).unsqueeze(-1) * self.time_frequencies.to(states.dtype)
        time = torch.cat((torch.sin(angles), torch.cos(angles)), dim=-1)
        if time.shape[-1] < self.hidden_dim:
            time = torch.nn.functional.pad(time, (0, self.hidden_dim - time.shape[-1]))
        returns = self.return_embedding(returns_to_go) + time
        previous = self.action_embedding(previous_actions) + time
        state = self.state_embedding(states) + time
        # Per step order: RTG_t, action_{t-1}, state_t. The prediction is read
        # from state_t, which sees only the past and these two current conditions.
        tokens = torch.stack((returns, previous, state), dim=2).reshape(batch, 3 * length, self.hidden_dim)
        tokens = self.input_norm(tokens)
        token_valid = attention_mask.bool().repeat_interleave(3, dim=1)
        token_count = tokens.shape[1]
        causal_mask = torch.triu(
            torch.ones((token_count, token_count), dtype=torch.bool, device=tokens.device),
            diagonal=1,
        )
        hidden = self.transformer(
            tokens,
            mask=causal_mask,
            src_key_padding_mask=~token_valid,
        )
        state_hidden = hidden[:, 2::3]
        return self.action_head(state_hidden)


def masked_action_mse(
    prediction: torch.Tensor, target: torch.Tensor, target_mask: torch.Tensor
) -> torch.Tensor:
    if prediction.shape != target.shape or target_mask.shape != prediction.shape[:2]:
        raise ValueError("prediction/target/mask shapes do not align")
    valid = target_mask.bool().unsqueeze(-1)
    count = valid.sum()
    if count == 0:
        raise ValueError("batch has no valid action targets")
    safe_target = torch.where(valid, target, prediction.detach())
    squared = (prediction - safe_target) ** 2
    return squared.sum() / count
