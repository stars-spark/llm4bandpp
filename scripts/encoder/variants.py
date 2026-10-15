# -*- coding: utf-8 -*-
"""Control encoders E1 and E2 of encoder-tsc-upgrade (E0 is module.StateEncoder, E3 is tsc_encoder.TSCEncoder; neither is here).
E1: the multi-scale DualScaleLSTM without TemporalAttention, whose 220,500 parameters are computed but never read. Removing it changes the
    order of random draws at initialization, so E1 does not reproduce the original encoder bit for bit; everything else is line for line the same.
E2: E1 without the cross-scale and bidirectional LSTMs. Both run over five 60 ms slots followed by five 600 ms slots, a time axis that is
    discontinuous between steps 5 and 6. E2 against E0 measures the value of removing that bias; E3 against E1 the value of the new encoder.
"""
from __future__ import annotations

import math

import torch
from torch import nn

NUM_FEATURES = 15
MI_DIM = 10
FEATURE_EMBEDDING_DIM = 8


class _DualScaleBranches(nn.Module):
    """Encode one feature's 10 values; keep_cross=False gives the two-branch E2 version."""

    def __init__(self, hidden_dim: int = FEATURE_EMBEDDING_DIM, keep_cross: bool = True):
        super().__init__()
        self.keep_cross = keep_cross
        self.short_term_lstm = nn.LSTM(input_size=1, hidden_size=16, num_layers=2,
                                       batch_first=True, dropout=0.1)
        self.long_term_lstm = nn.LSTM(input_size=1, hidden_size=16, num_layers=2,
                                      batch_first=True, dropout=0.1)
        if keep_cross:
            self.cross_scale_lstm = nn.LSTM(input_size=1, hidden_size=12, num_layers=1,
                                            batch_first=True)
            self.bidirectional_lstm = nn.LSTM(input_size=1, hidden_size=8, num_layers=1,
                                              batch_first=True, bidirectional=True)
        fused_in = 16 + 16 + (12 + 16 if keep_cross else 0)
        self.n_branches = 4 if keep_cross else 2
        self.fusion_network = nn.Sequential(
            nn.Linear(fused_in, 32), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(32, 16), nn.ReLU(),
            nn.Linear(16, hidden_dim))
        self.gating_network = nn.Sequential(
            nn.Linear(MI_DIM, 16), nn.ReLU(),
            nn.Linear(16, self.n_branches), nn.Sigmoid())

    def forward(self, x):                                  # [B, 10]
        short = x[:, :5].unsqueeze(-1)
        long = x[:, 5:].unsqueeze(-1)
        _, (sh, _) = self.short_term_lstm(short)
        _, (lh, _) = self.long_term_lstm(long)
        parts = [sh[-1], lh[-1]]
        if self.keep_cross:
            whole = x.unsqueeze(-1)
            _, (ch, _) = self.cross_scale_lstm(whole)
            _, (bh, _) = self.bidirectional_lstm(whole)
            parts += [ch[-1], torch.cat([bh[0], bh[1]], dim=1)]
        gate = self.gating_network(x)                      # [B, n_branches]
        gated = [p * gate[:, i:i + 1] for i, p in enumerate(parts)]
        return self.fusion_network(torch.cat(gated, dim=1))


class DualScaleLSTMVariant(nn.Module):
    """Drop-in replacement for module.StateEncoderDualScaleLSTM: keep_cross=True is E1 (four branches, no TemporalAttention), keep_cross=False is E2."""

    def __init__(self, observation_shape, hidden_dim, device, keep_cross: bool = True):
        super().__init__()
        assert observation_shape == NUM_FEATURES * MI_DIM, (
            f"observation_shape {observation_shape} should be {NUM_FEATURES * MI_DIM}")
        self.observation_shape = observation_shape
        self.num_features = NUM_FEATURES
        self.mi_dim = MI_DIM
        self.feature_embedding_dim = FEATURE_EMBEDDING_DIM
        self.hidden_dim = hidden_dim
        self.device = device
        self.keep_cross = keep_cross

        self.feature_encoders = nn.ModuleList([
            _DualScaleBranches(FEATURE_EMBEDDING_DIM, keep_cross) for _ in range(NUM_FEATURES)])

        layer = nn.TransformerEncoderLayer(
            d_model=FEATURE_EMBEDDING_DIM, nhead=4, dim_feedforward=32,
            dropout=0.1, activation="gelu", batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(layer, num_layers=2)

        self.output_projection = nn.Sequential(
            nn.Linear(NUM_FEATURES * FEATURE_EMBEDDING_DIM, hidden_dim),
            nn.LayerNorm(hidden_dim), nn.GELU(), nn.Dropout(0.1))

        self.register_buffer(
            "positional_encoding",
            self._positional_encoding(NUM_FEATURES, FEATURE_EMBEDDING_DIM))

        # Move the whole module once: bwe_agent never moves the encoder, and the submodules are not moved one by one here.
        self.to(device)

    @staticmethod
    def _positional_encoding(seq_len, d_model):
        pe = torch.zeros(seq_len, d_model)
        pos = torch.arange(0, seq_len, dtype=torch.float).unsqueeze(1)
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        return pe.unsqueeze(0)

    def forward(self, x):                                   # [B, 150]
        b = x.shape[0]
        v = x.view(b, self.num_features, self.mi_dim)
        embeds = torch.stack([self.feature_encoders[i](v[:, i, :])
                              for i in range(self.num_features)], dim=1)
        embeds = embeds + self.positional_encoding
        return self.output_projection(self.transformer_encoder(embeds).reshape(b, -1))
