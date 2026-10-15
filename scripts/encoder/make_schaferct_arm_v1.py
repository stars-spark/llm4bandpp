#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schaferct-arch-recipe-v1, which tests whether the gap to Schaferct-R comes from the recipe or the network: write the estimator.py that trains Schaferct's policy network with our
recipe. Input: the estimator.py of the C cells (scripts/encoder/nl2x2_v1/estimator_conf.py); only bwe_agent changes.
The network copies the GaussianPolicy of Schaferct's v14_iql.py: Linear(150, 256) + ReLU, GRU(256, 256, 2 layers),
Linear(256, 256) + ReLU, two residual blocks of two Linear(256, 256) + LeakyReLU, Linear(256, 1) + Tanh; the output is
scaled by max_action * 1e6 (bit/s) and clipped to at least 10 bit/s; the input keeps the scale encoder0. The GRU is used
as at Schaferct's inference, one step per sample from a zero state; Schaferct's training, which feeds a batch to the GRU
as one sequence, is not copied.
Usage: python3 make_schaferct_arm_v1.py SOURCE_estimator.py OUTPUT_estimator.py
"""
import hashlib, re, sys
from pathlib import Path

WANT = "f78405de1d20dc68"
NEW_INIT = '''        # SCHAFERCT_ARCH_V1: structure of GaussianPolicy in Schaferct v14_iql.py, replacing the conference version encoder and BweHead
        self.sch_encoder1 = nn.Sequential(nn.Linear(150, 256), nn.ReLU()).to(self.device)
        self.sch_gru = nn.GRU(256, 256, 2).to(self.device)
        self.sch_fc_mid = nn.Sequential(nn.Linear(256, 256), nn.ReLU()).to(self.device)
        self.sch_rb1 = nn.Sequential(nn.Linear(256, 256), nn.LeakyReLU(), nn.Linear(256, 256), nn.LeakyReLU()).to(self.device)
        self.sch_rb2 = nn.Sequential(nn.Linear(256, 256), nn.LeakyReLU(), nn.Linear(256, 256), nn.LeakyReLU()).to(self.device)
        self.sch_final = nn.Sequential(nn.Linear(256, 1), nn.Tanh()).to(self.device)
'''
NEW_FWD = '''    def forward(self, x):
        x = x * self.encoder0
        m = self.sch_encoder1(x)                       # [batch, 256]
        m, _ = self.sch_gru(m.unsqueeze(0))            # one step per sample, zero initial state: [1, batch, 256]
        m = self.sch_fc_mid(m.squeeze(0))
        m = self.sch_rb1(m) + m
        m = self.sch_rb2(m) + m
        m = self.sch_final(m) * self.max_action * 1e6  # Mbps -> bps, same as Schaferct
        m = m.clamp(min=10)
        std = torch.exp(self.log_std.clamp(LOG_STD_MIN, LOG_STD_MAX))
        std = std.expand(x.shape[0], 1)
        return m, std
'''


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2]); s = src.read_text()
    assert hashlib.sha256(src.read_bytes()).hexdigest().startswith(WANT), "Source estimator.py hash mismatch"
    i = s.index("class bwe_agent(nn.Module):"); j = s.index("class bwe_agent_base(nn.Module):"); body = s[i:j]
    old_init = ("        self.stateencoder = StateEncoder(self.state_dim, 1024, self.device)\n"
                "        self.bwe_head = BweHead(1024, 512, self.action_dim, self.max_action, self.device)\n")
    assert body.count(old_init) == 1, "bwe_agent encoder and head are not where expected"
    body = body.replace(old_init, NEW_INIT)
    k = body.index("    def forward(self, x):"); body = body[:k] + NEW_FWD + "\n"
    t = s[:i] + body + s[j:]
    assert t.count("SCHAFERCT_ARCH_V1") == 1 and "self.stateencoder" not in t[t.index("class bwe_agent(nn.Module):"):t.index("class bwe_agent_base(nn.Module):")]
    out.write_text(t); print("Written", out, hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
