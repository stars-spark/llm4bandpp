# -*- coding: utf-8 -*-
"""The two fifteen-token encoders of ablation-enc-hcq-2x2-v1; both return [B, 15, 1024], fed to Qwen as inputs_embeds. estimator.py picks one by BWE_ENC.
  conf15  conference encoder split by feature: token i = LeakyReLU(LayerNorm(W_i x_i + b_i)), x_i the 10 scaled slots of feature i
          (index feature*10 + slot, as in encoder0), W_i 1024x10, one LayerNorm shared by the 15 tokens. With W_i the column blocks of the
          conference Linear(150,1024) and b_i = b/15, the 15 pre-activations sum to the conference linear output.
  ms15    multi-scale encoder without the cross-scale and bidirectional LSTMs and TemporalAttention (variants.DualScaleLSTMVariant, keep_cross=False),
          with the flattened Linear(120,1024) replaced by a per-position Linear(8,1024), LayerNorm, GELU and Dropout 0.1.
          The parent first builds a Linear(120,1024) that is then replaced: one extra draw of random numbers, no parameter left behind.
"""
from __future__ import annotations

import os
import sys

import torch
from torch import nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from variants import (FEATURE_EMBEDDING_DIM, MI_DIM, NUM_FEATURES,  # noqa: E402
                      DualScaleLSTMVariant)


class Conf15Encoder(nn.Module):
    """Conference encoder split into 15 per-feature tokens; 171,008 parameters."""

    def __init__(self, observation_shape, hidden_dim, device):
        super().__init__()
        assert observation_shape == NUM_FEATURES * MI_DIM, (
            f"observation_shape {observation_shape} should be {NUM_FEATURES * MI_DIM}")
        self.num_features = NUM_FEATURES
        self.mi_dim = MI_DIM
        self.hidden_dim = hidden_dim
        self.device = device
        self.proj = nn.ModuleList([nn.Linear(MI_DIM, hidden_dim) for _ in range(NUM_FEATURES)])
        self.layer_norm = nn.LayerNorm(hidden_dim)
        self.ac1 = nn.LeakyReLU()
        self.to(device)

    def pre_activation(self, x):
        """Map [B, 150] to [B, 15, H]: the 15 terms W_i x_i + b_i before LayerNorm and LeakyReLU."""
        v = x.view(x.shape[0], self.num_features, self.mi_dim)
        return torch.stack([self.proj[i](v[:, i, :]) for i in range(self.num_features)], dim=1)

    def forward(self, x):
        return self.ac1(self.layer_norm(self.pre_activation(x)))

    @torch.no_grad()
    def load_from_conference_linear(self, weight, bias):
        """Load a conference Linear(150,1024) as 15 column blocks with bias b/15; used only by the smoke equivalence check."""
        assert tuple(weight.shape) == (self.hidden_dim, self.num_features * self.mi_dim)
        for i in range(self.num_features):
            self.proj[i].weight.copy_(weight[:, i * self.mi_dim:(i + 1) * self.mi_dim])
            # Split the bias evenly so the 15 pre-activations sum to W x + b.
            self.proj[i].bias.copy_(bias / self.num_features)


class MS15Encoder(DualScaleLSTMVariant):
    """Multi-scale fifteen-token encoder: two LSTM branches with a two-way gate per feature, a two-layer cross-feature Transformer, a per-position projection."""

    def __init__(self, observation_shape, hidden_dim, device):
        super().__init__(observation_shape, hidden_dim, device, keep_cross=False)
        self.output_projection = nn.Sequential(
            nn.Linear(FEATURE_EMBEDDING_DIM, hidden_dim),
            nn.LayerNorm(hidden_dim), nn.GELU(), nn.Dropout(0.1))
        self.to(device)

    def forward(self, x):                                   # [B, 150]
        b = x.shape[0]
        v = x.view(b, self.num_features, self.mi_dim)
        embeds = torch.stack([self.feature_encoders[i](v[:, i, :])
                              for i in range(self.num_features)], dim=1)
        embeds = embeds + self.positional_encoding
        return self.output_projection(self.transformer_encoder(embeds))   # [B, 15, H]


ENCODERS = {"conf15": Conf15Encoder, "ms15": MS15Encoder}


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
