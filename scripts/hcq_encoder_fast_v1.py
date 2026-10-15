# -*- coding: utf-8 -*-
"""Vectorized multi-scale encoder: the same computation as module.StateEncoderDualScaleLSTM, used for the latency rows of Table III."""
from __future__ import annotations

import torch
import torch.nn as nn


class FastStateEncoderDualScale(nn.Module):
    """Evaluate the fifteen feature encoders as one batched recurrent system."""

    NUM_FEATURES = 15
    MI_DIM = 10
    EMBEDDING_DIM = 8

    def __init__(self, observation_shape: int, hidden_dim: int, device):
        super().__init__()
        if observation_shape != self.NUM_FEATURES * self.MI_DIM:
            raise ValueError("observation_shape must be 150")
        self.observation_shape = observation_shape
        self.num_features = self.NUM_FEATURES
        self.mi_dim = self.MI_DIM
        self.feature_embedding_dim = self.EMBEDDING_DIM
        self.hidden_dim = hidden_dim
        self.device = device

        self._make_lstm_parameters("short", 2, 1, 16, device)
        self._make_lstm_parameters("long", 2, 1, 16, device)
        self._make_lstm_parameters("cross", 1, 1, 12, device)
        self._make_lstm_parameters("bi_forward", 1, 1, 8, device)
        self._make_lstm_parameters("bi_reverse", 1, 1, 8, device)

        self.gate_w1 = nn.Parameter(torch.empty(self.NUM_FEATURES, 16, 10, device=device))
        self.gate_b1 = nn.Parameter(torch.empty(self.NUM_FEATURES, 16, device=device))
        self.gate_w2 = nn.Parameter(torch.empty(self.NUM_FEATURES, 4, 16, device=device))
        self.gate_b2 = nn.Parameter(torch.empty(self.NUM_FEATURES, 4, device=device))

        self.fusion_w1 = nn.Parameter(torch.empty(self.NUM_FEATURES, 32, 60, device=device))
        self.fusion_b1 = nn.Parameter(torch.empty(self.NUM_FEATURES, 32, device=device))
        self.fusion_w2 = nn.Parameter(torch.empty(self.NUM_FEATURES, 16, 32, device=device))
        self.fusion_b2 = nn.Parameter(torch.empty(self.NUM_FEATURES, 16, device=device))
        self.fusion_w3 = nn.Parameter(torch.empty(self.NUM_FEATURES, 8, 16, device=device))
        self.fusion_b3 = nn.Parameter(torch.empty(self.NUM_FEATURES, 8, device=device))
        self._reset_parameters()

        layer = nn.TransformerEncoderLayer(
            d_model=self.EMBEDDING_DIM,
            nhead=4,
            dim_feedforward=32,
            dropout=0.1,
            activation="gelu",
            batch_first=True,
        ).to(device)
        self.transformer_layer = layer
        self.transformer_encoder = nn.TransformerEncoder(layer, num_layers=2).to(device)
        self.output_projection = nn.Sequential(
            nn.Linear(self.NUM_FEATURES * self.EMBEDDING_DIM, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
        ).to(device)
        self.register_buffer("positional_encoding", self._create_positional_encoding(), persistent=True)

    def _make_lstm_parameters(self, name, layers, input_size, hidden_size, device):
        for layer in range(layers):
            size = input_size if layer == 0 else hidden_size
            for suffix, shape in (
                ("w_ih", (self.NUM_FEATURES, 4 * hidden_size, size)),
                ("w_hh", (self.NUM_FEATURES, 4 * hidden_size, hidden_size)),
                ("b_ih", (self.NUM_FEATURES, 4 * hidden_size)),
                ("b_hh", (self.NUM_FEATURES, 4 * hidden_size)),
            ):
                setattr(self, f"{name}_{layer}_{suffix}", nn.Parameter(torch.empty(*shape, device=device)))

    def _reset_parameters(self):
        for p in self.parameters():
            if p.dim() >= 2:
                nn.init.uniform_(p, -0.1, 0.1)
            else:
                nn.init.zeros_(p)

    def _create_positional_encoding(self):
        pe = torch.zeros(self.NUM_FEATURES, self.EMBEDDING_DIM, device=self.device)
        position = torch.arange(self.NUM_FEATURES, dtype=torch.float32, device=self.device).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, self.EMBEDDING_DIM, 2, device=self.device).float()
                             * (-torch.log(torch.tensor(10000.0, device=self.device)) / self.EMBEDDING_DIM))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        return pe.unsqueeze(0)

    def _lstm(self, sequence, name, layers, hidden_size):
        # sequence has shape batch, feature, time.
        current = sequence
        for layer in range(layers):
            w_ih = getattr(self, f"{name}_{layer}_w_ih")
            w_hh = getattr(self, f"{name}_{layer}_w_hh")
            b_ih = getattr(self, f"{name}_{layer}_b_ih")
            b_hh = getattr(self, f"{name}_{layer}_b_hh")
            batch = current.shape[0]
            h = current.new_zeros(batch, self.NUM_FEATURES, hidden_size)
            c = current.new_zeros(batch, self.NUM_FEATURES, hidden_size)
            outputs = []
            for t in range(current.shape[2]):
                x_t = current[:, :, t, :]
                gates = (torch.einsum("bfi,foi->bfo", x_t, w_ih)
                         + torch.einsum("bfh,foh->bfo", h, w_hh)
                         + b_ih.unsqueeze(0) + b_hh.unsqueeze(0))
                i, f, g, o = gates.chunk(4, dim=-1)
                c = torch.sigmoid(f) * c + torch.sigmoid(i) * torch.tanh(g)
                h = torch.sigmoid(o) * torch.tanh(c)
                outputs.append(h)
            current = torch.stack(outputs, dim=2)
        return h

    @staticmethod
    def _feature_linear(x, weight, bias):
        return torch.einsum("bfi,foi->bfo", x, weight) + bias.unsqueeze(0)

    @classmethod
    def from_reference(cls, ref):
        fast = cls(ref.observation_shape, ref.hidden_dim, ref.device)
        with torch.no_grad():
            for branch, source_name, layers, hidden in (
                ("short", "short_term_lstm", 2, 16),
                ("long", "long_term_lstm", 2, 16),
                ("cross", "cross_scale_lstm", 1, 12),
            ):
                for layer in range(layers):
                    src = getattr(ref.feature_encoders[0], source_name)
                    for suffix in ("w_ih", "w_hh", "b_ih", "b_hh"):
                        target = getattr(fast, f"{branch}_{layer}_{suffix}")
                        attr = suffix.replace("w_", "weight_").replace("b_", "bias_") + f"_l{layer}"
                        values = torch.stack([getattr(getattr(fe, source_name), attr)
                                              for fe in ref.feature_encoders])
                        target.copy_(values)
            for direction, suffix in (("bi_forward", ""), ("bi_reverse", "_reverse")):
                for layer in range(1):
                    for part, ref_part in (("w_ih", "weight_ih_l0" + suffix),
                                           ("w_hh", "weight_hh_l0" + suffix),
                                           ("b_ih", "bias_ih_l0" + suffix),
                                           ("b_hh", "bias_hh_l0" + suffix)):
                        getattr(fast, f"{direction}_{layer}_{part}").copy_(
                            torch.stack([getattr(fe.bidirectional_lstm, ref_part) for fe in ref.feature_encoders]))
            for target_name, source_name in (
                ("gate_w1", "0.weight"), ("gate_b1", "0.bias"),
                ("gate_w2", "2.weight"), ("gate_b2", "2.bias"),
            ):
                values = torch.stack([getattr(fe.gating_network[int(source_name[0])], source_name.split(".")[1])
                                      for fe in ref.feature_encoders])
                getattr(fast, target_name).copy_(values)
            for target_name, source_name in (
                ("fusion_w1", "0.weight"), ("fusion_b1", "0.bias"),
                ("fusion_w2", "3.weight"), ("fusion_b2", "3.bias"),
                ("fusion_w3", "5.weight"), ("fusion_b3", "5.bias"),
            ):
                values = torch.stack([getattr(fe.fusion_network[int(source_name[0])], source_name.split(".")[1])
                                      for fe in ref.feature_encoders])
                getattr(fast, target_name).copy_(values)
            fast.transformer_encoder.load_state_dict(ref.transformer_encoder.state_dict())
            fast.output_projection.load_state_dict(ref.output_projection.state_dict())
            fast.positional_encoding.copy_(ref.positional_encoding)
        return fast

    def forward(self, x):
        x = x.view(x.shape[0], self.NUM_FEATURES, self.MI_DIM)
        short = self._lstm(x[:, :, :5].unsqueeze(-1), "short", 2, 16)
        long = self._lstm(x[:, :, 5:].unsqueeze(-1), "long", 2, 16)
        cross = self._lstm(x.unsqueeze(-1), "cross", 1, 12)
        bi_forward = self._lstm(x.unsqueeze(-1), "bi_forward", 1, 8)
        bi_reverse = self._lstm(x.flip(-1).unsqueeze(-1), "bi_reverse", 1, 8)
        bi = torch.cat([bi_forward, bi_reverse], dim=-1)

        gate_hidden = torch.relu(self._feature_linear(x, self.gate_w1, self.gate_b1))
        gate = torch.sigmoid(self._feature_linear(gate_hidden, self.gate_w2, self.gate_b2))
        combined = torch.cat([short * gate[:, :, 0:1], long * gate[:, :, 1:2],
                              cross * gate[:, :, 2:3], bi * gate[:, :, 3:4]], dim=-1)
        fused = torch.relu(self._feature_linear(combined, self.fusion_w1, self.fusion_b1))
        fused = torch.relu(self._feature_linear(fused, self.fusion_w2, self.fusion_b2))
        embeddings = self._feature_linear(fused, self.fusion_w3, self.fusion_b3)
        embeddings = embeddings + self.positional_encoding
        aggregated = self.transformer_encoder(embeddings)
        return self.output_projection(aggregated.reshape(x.shape[0], -1))
