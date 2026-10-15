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

class StateEncoder(nn.Module):
    def __init__(self, observation_shape, hidden_dim, device):
        super(StateEncoder, self).__init__()
        self.hidden_dim = hidden_dim
        self.device = device
        self.fc_head = nn.Linear(observation_shape, self.hidden_dim).to(self.device)
        self.layer_norm = nn.LayerNorm(self.hidden_dim).to(self.device)
        self.ac1 = nn.LeakyReLU().to(self.device)
        # self.block = ResidualBlock(self.hidden_dim, self.hidden_dim)

    def forward(self, x):
        x = self.fc_head(x)
        x = self.layer_norm(x)
        x = self.ac1(x)
        # x = self.block(x)
        return x
    
class StateEncoderDualScaleLSTM(nn.Module):
    """Multi-scale encoder: a DualScaleLSTMEncoder per feature, a two-layer Transformer across the 15 features, and a per-position projection to [B, 15, hidden_dim]."""
    def __init__(self, observation_shape, hidden_dim, device):
        super(StateEncoderDualScaleLSTM, self).__init__()
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
            nn.Linear(self.feature_embedding_dim, hidden_dim),
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
        
        #    [batch, 15, 8] -> [batch, 15, 1024]
        output = self.output_projection(aggregated_features)
        
        return output
class DualScaleLSTMEncoder(nn.Module):
    """Encode one feature's 10 values (5 slots at 60 ms, then 5 at 600 ms) with short-term, long-term, cross-scale and bidirectional LSTMs, gated and fused to hidden_dim."""
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
        
        self.temporal_attention = TemporalAttention(
            short_dim=16, long_dim=16, cross_dim=12, bi_dim=16
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
        
        # Computed but unused: the gated fusion below ignores it. Kept so checkpoints load with strict=True.
        attended_features = self.temporal_attention(
            short_features, long_features, cross_features, bi_features, x
        )
        
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


class TemporalAttention(nn.Module):
    """Attention over the concatenated LSTM branch outputs; DualScaleLSTMEncoder computes it but does not use the result."""
    def __init__(self, short_dim=16, long_dim=16, cross_dim=12, bi_dim=16):
        super(TemporalAttention, self).__init__()
        
        total_dim = short_dim + long_dim + cross_dim + bi_dim
        
        self.query_proj = nn.Linear(total_dim, total_dim)
        self.key_proj = nn.Linear(total_dim, total_dim)
        self.value_proj = nn.Linear(total_dim, total_dim)
        
        self.time_scale_encoding = nn.Embedding(4, total_dim // 4)
        
        self.attention_dropout = nn.Dropout(0.1)
        self.output_proj = nn.Linear(total_dim, total_dim)
    
    def forward(self, short_feat, long_feat, cross_feat, bi_feat, original_input):
        batch_size = short_feat.size(0)
        
        all_features = torch.cat([short_feat, long_feat, cross_feat, bi_feat], dim=1)
        # [batch_size, 60]
        
        queries = self.query_proj(all_features)
        keys = self.key_proj(all_features)
        values = self.value_proj(all_features)
        
        scale_ids = torch.arange(4, device=all_features.device).unsqueeze(0).expand(batch_size, -1)
        scale_encoding = self.time_scale_encoding(scale_ids).flatten(1)
        
        attention_scores = torch.matmul(queries, keys.unsqueeze(-1)).squeeze(-1)
        attention_weights = torch.softmax(attention_scores, dim=-1)
        attention_weights = self.attention_dropout(attention_weights)
        
        attended = all_features * attention_weights.unsqueeze(-1)
        output = self.output_proj(attended)
        
        return output

class CNNEmbedding(nn.Module):
    def __init__(self, embedding_dim, device):
        super(CNNEmbedding, self).__init__()
        self.device = device
        self.embedding_dim = embedding_dim
        self.conv1d = nn.Conv1d(1, self.embedding_dim, 1).to(self.device)
        self.layer_norm = nn.LayerNorm(self.embedding_dim).to(self.device)
        self.ac1 = nn.ReLU().to(self.device)

    def forward(self, x):
        x = torch.unsqueeze(x, dim = 1)
        x = self.conv1d(x)
        x = x.transpose(1, 2)
        x = self.layer_norm(x)
        x = self.ac1(x)
        return x


class BweHead(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim, max_action, device):
        super(BweHead, self).__init__()
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.max_action = max_action
        self.device = device
        self.fc_head1 = nn.Linear(input_dim, self.hidden_dim).to(self.device)
        self.layer_norm = nn.LayerNorm(self.hidden_dim).to(self.device)
        self.ac1 = nn.LeakyReLU().to(self.device)

        self.fc_head2 = nn.Linear(self.hidden_dim, self.output_dim).to(self.device)
        self.ac2 = nn.LeakyReLU().to(self.device)
        self.tanh = nn.Tanh().to(self.device)

    def forward(self, x):
        x = self.fc_head1(x)
        x = self.layer_norm(x)
        x = self.ac1(x)
        x = self.fc_head2(x)
        x = self.ac2(x)
        return self.tanh(x) * self.max_action * 1e6

class BweHead2(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim, max_action, device):
        super(BweHead2, self).__init__()
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.max_action = max_action
        self.device = device
        self.fc_head1 = nn.Linear(input_dim, self.hidden_dim).to(self.device)
        self.layer_norm = nn.LayerNorm(self.hidden_dim).to(self.device)
        self.ac1 = nn.LeakyReLU().to(self.device)
        self.block = ResidualBlock(self.hidden_dim, self.hidden_dim, self.device)
        self.fc_head2 = nn.Linear(self.hidden_dim, self.output_dim).to(self.device)
        self.ac2 = nn.LeakyReLU().to(self.device)
        self.tanh = nn.Tanh().to(self.device)

    def forward(self, x):
        x = self.fc_head1(x)
        x = self.layer_norm(x)
        x = self.ac1(x)
        x = self.block(x)
        x = self.fc_head2(x)
        x = self.ac2(x)
        return self.tanh(x) * self.max_action * 1e6

class ResidualBlock(nn.Module):
    def __init__(self, input_size, output_size, device):
        super(ResidualBlock, self).__init__()
        self.output_size = output_size
        self.block = nn.Sequential(
            nn.Linear(input_size, self.output_size).to(device),
            nn.LayerNorm(self.output_size).to(device),
            nn.LeakyReLU().to(device),
        )

    def forward(self, x):
        residual = x
        out = self.block(x)
        out += residual
        return out

class CustomParallelEmbedding(nn.Module):
    def __init__(self, input_size, output_size, world_size):
        super(CustomParallelEmbedding, self).__init__()
        self.input_size = input_size
        self.output_size = output_size
        self.world_size = world_size

        self.embedding_size_per_rank = output_size // world_size
        self.local_rank = dist.get_rank()

        # Each rank holds a fraction of the embedding matrix
        self.embedding_matrix = nn.Parameter(torch.randn(input_size, self.embedding_size_per_rank))

    def forward(self, input_indices):
        dist.broadcast(self.embedding_matrix, src=0)

        all_input_indices = [torch.zeros(0, dtype=input_indices.dtype, device=input_indices.device) for _ in range(self.world_size)]

        gather_op = dist.all_gather(all_input_indices, input_indices)

        torch.distributed.barrier()

        local_input_indices = all_input_indices[self.local_rank]

        local_embeddings = torch.index_select(self.embedding_matrix, dim=0, index=local_input_indices)

        return local_embeddings

# https://github.com/facebookresearch/fairscale/blob/main/fairscale/nn/model_parallel/layers.py
