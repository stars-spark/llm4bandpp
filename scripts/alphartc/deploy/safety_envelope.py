#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probing envelope v2 (BWE_ENVELOPE=1 in switcher.py) around the switcher or fixed-arm estimate; constants come from the GCC specification, not fitted to closed-loop data.
From the 600 ms long window: loss rate and queuing-delay excess over the 10 s minimum. Clear (loss <= 0.02, excess <= 100 ms): floor F <- min(max(F, last output) x 1.08^dt,
1.5R + 10 kbps), output max(model, F); mild: F unchanged; congested (loss > 0.10 or excess > 300 ms): F <- 0.85R, output F. The receiving rate R only sets the cap.
Base of the envelope family; superseded by safety_envelope_v3.py.
Written for switch-envelope-lowbw-v2; no paper result uses it.
"""
from collections import deque

ETA, CAP_K, CAP_B, BETA = 1.08, 1.5, 10000.0, 0.85
LOSS_OK, LOSS_BAD, EXC_OK, EXC_BAD = 0.02, 0.10, 100.0, 300.0
MIN_WINDOW_S = 10.0


class SafetyEnvelope:
    def __init__(self):
        self.hist = deque(); self.F = 0.0; self.prev_out = 0.0; self.prev_t = None
        self.last = {"state": "init", "R": 0.0, "excess": 0.0, "loss": 0.0, "F": 0.0}

    def apply(self, pred_bps, obs, t_ms):
        pred = float(pred_bps); n_long, R, q, loss = obs[15], float(obs[5]), float(obs[35]), float(obs[105])
        dt = 0.0 if self.prev_t is None else min(max((t_ms - self.prev_t) / 1000.0, 0.0), 1.0); self.prev_t = t_ms
        if n_long <= 0 or R <= 0:
            self.last = {"state": "empty", "R": R, "excess": 0.0, "loss": loss, "F": self.F}; self.prev_out = pred; return pred
        self.hist.append((t_ms, q))
        while self.hist and t_ms - self.hist[0][0] > MIN_WINDOW_S * 1000.0: self.hist.popleft()
        excess = q - min(v for _, v in self.hist)
        if loss > LOSS_BAD or excess > EXC_BAD:
            state = "congested"; self.F = BETA * R; out = self.F
        elif loss <= LOSS_OK and excess <= EXC_OK:
            state = "clear"; self.F = min(max(self.F, self.prev_out) * (ETA ** dt), CAP_K * R + CAP_B); out = max(pred, self.F)
        else:
            state = "mild"; out = max(pred, self.F)
        self.prev_out = out; self.last = {"state": state, "R": R, "excess": excess, "loss": loss, "F": self.F}
        return out
