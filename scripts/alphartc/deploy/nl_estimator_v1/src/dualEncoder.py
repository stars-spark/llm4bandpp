# Copyright 2024 ByteDance and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import torch
import torch.nn as nn
import math
    
class StateEncoderDualScaleLSTMpro(nn.Module):
    """Multi-scale encoder with one output vector: a DualScaleLSTMEncoder per feature, a two-layer Transformer across features, and the flattened [B, 120] projected to [B, hidden_dim]."""
    def __init__(self, observation_shape, hidden_dim, device):
        super(StateEncoderDualScaleLSTMpro, self).__init__()
        self.observation_shape = observation_shape  # 150
        self.num_features = 15
        self.mi_dim = 10
        self.feature_embedding_dim = 8
        self.hidden_dim = hidden_dim  # 1024
        self.device = device
        
        assert observation_shape == self.num_features * self.mi_dim, \
            f"observation_shape {observation_shape} != num_features * mi_dim {self.num_features * self.mi_dim}"
        
        self.feature_encoders = nn.ModuleList([
            DualScaleLSTMEncoder(device=device)
            for _ in range(self.num_features)
        ])
        
        self.transformer_layer = nn.TransformerEncoderLayer(
            d_model=self.feature_embedding_dim,
            nhead=4,
            dim_feedforward=32,
            dropout=0.1,
            activation='gelu',
            batch_first=True
        ).to(device)
        
        self.transformer_encoder = nn.TransformerEncoder(
            self.transformer_layer, 
            num_layers=2
        ).to(device)
        
        self.output_projection = nn.Sequential(
            nn.Linear(self.num_features * self.feature_embedding_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1)
        ).to(device)
        
        self.positional_encoding = self._create_positional_encoding(
            self.num_features, self.feature_embedding_dim
        ).to(device)

    def _create_positional_encoding(self, seq_len, d_model):
        """Sinusoidal positional encoding of shape [1, seq_len, d_model]."""
        pe = torch.zeros(seq_len, d_model)
        position = torch.arange(0, seq_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * 
                           (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        return pe.unsqueeze(0)  # [1, seq_len, d_model]
    
    def forward(self, x):
        batch_size = x.shape[0]
        
        # 1. Reshape: [batch_size, 150] → [batch_size, 15, 10]
        x = x.view(batch_size, self.num_features, self.mi_dim)
        
        feature_embeddings = []
        for i in range(self.num_features):
            feature_mi = x[:, i, :]  # [batch_size, 10]
            
            feature_embed = self.feature_encoders[i](feature_mi)  # [batch_size, 8]
            feature_embeddings.append(feature_embed)
        
        feature_embeddings = torch.stack(feature_embeddings, dim=1)
        
        feature_embeddings = feature_embeddings + self.positional_encoding
        
        aggregated_features = self.transformer_encoder(feature_embeddings)
        
        flattened = aggregated_features.view(batch_size, -1)
        output = self.output_projection(flattened)
        
        return output
class DualScaleLSTMEncoder(nn.Module):
    """Encode one feature's 10 values (5 slots at 60 ms, then 5 at 600 ms) with four gated LSTM branches fused to hidden_dim; no attention module."""
    def __init__(self, hidden_dim=8, device='cpu'):
        super(DualScaleLSTMEncoder, self).__init__()
        self.hidden_dim = hidden_dim
        self.device = device
        
        self.short_term_lstm = nn.LSTM(
            input_size=1, 
            hidden_size=16,
            num_layers=2,
            batch_first=True,
            dropout=0.1
        ).to(device)
        
        self.long_term_lstm = nn.LSTM(
            input_size=1,
            hidden_size=16,
            num_layers=2,
            batch_first=True,
            dropout=0.1
        ).to(device)
        
        self.cross_scale_lstm = nn.LSTM(
            input_size=1,
            hidden_size=12,
            num_layers=1,
            batch_first=True
        ).to(device)
        
        self.bidirectional_lstm = nn.LSTM(
            input_size=1,
            hidden_size=8,
            num_layers=1,
            batch_first=True,
            bidirectional=True
        ).to(device)
        
        self.fusion_network = nn.Sequential(
            nn.Linear(16 + 16 + 12 + 16, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, hidden_dim)
        ).to(device)
        
        self.gating_network = nn.Sequential(
            nn.Linear(10, 16),
            nn.ReLU(),
            nn.Linear(16, 4),
            nn.Sigmoid()
        ).to(device)
    
    def forward(self, x):  # [batch_size, 10]
        batch_size = x.size(0)
        
        short_term_mi = x[:, :5]
        long_term_mi = x[:, 5:]
        
        
        short_input = short_term_mi.unsqueeze(-1)  # [batch_size, 5, 1]
        short_output, (short_h, short_c) = self.short_term_lstm(short_input)
        short_features = short_h[-1]
        
        long_input = long_term_mi.unsqueeze(-1)   # [batch_size, 5, 1]
        long_output, (long_h, long_c) = self.long_term_lstm(long_input)
        long_features = long_h[-1]  # [batch_size, 16]
        
        cross_input = x.unsqueeze(-1)  # [batch_size, 10, 1]
        cross_output, (cross_h, cross_c) = self.cross_scale_lstm(cross_input)
        cross_features = cross_h[-1]  # [batch_size, 12]
        
        bi_output, (bi_h, bi_c) = self.bidirectional_lstm(cross_input)
        bi_features = torch.cat([bi_h[0], bi_h[1]], dim=1)  # [batch_size, 16]
        
        gate_weights = self.gating_network(x)  # [batch_size, 4]
        
        gated_short = short_features * gate_weights[:, 0:1]      # [batch_size, 16]
        gated_long = long_features * gate_weights[:, 1:2]        # [batch_size, 16]
        gated_cross = cross_features * gate_weights[:, 2:3]      # [batch_size, 12]
        gated_bi = bi_features * gate_weights[:, 3:4]            # [batch_size, 16]
        
        combined_features = torch.cat([
            gated_short,
            gated_long, 
            gated_cross,
            gated_bi
        ], dim=1)  # [batch_size, 60]
        
        output = self.fusion_network(combined_features)  # [batch_size, 8]
        
        return output