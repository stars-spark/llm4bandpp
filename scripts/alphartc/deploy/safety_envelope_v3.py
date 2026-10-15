# -*- coding: utf-8 -*-
"""Probing envelope v3 (BWE_ENVELOPE=3): the v2 state machine on the total receiving rate Rt, main video plus a 41 kbps audio constant (testbed-sender-floor-audio-audit-v1),
since AlphaRTC does not report audio to the estimator. Capacity memory: at congestion onset C_hat <- Rt and during a hold period the floor stays below 0.9 C_hat; a probe above C_hat
clear for 5 s clears the memory, otherwise the hold doubles (10 s up to 80 s). Backoff happens at most once per second. 1.08, 1.5R + 10 kbps and 0.85 are GCC values;
0.9, 5 s and 10 to 80 s are engineering choices; none is fitted to closed-loop results.
New file next to safety_envelope.py (v2), written for switch-envelope-lowbw-v3; superseded by v4 and not used by any paper result.
"""
from collections import deque

ETA, CAP_K, CAP_B, BETA = 1.08, 1.5, 10000.0, 0.85
LOSS_OK, LOSS_BAD, EXC_OK, EXC_BAD = 0.02, 0.10, 100.0, 300.0
MIN_WINDOW_S = 10.0
AUDIO_BPS = 41000.0
HOLD_FRAC, HOLD_S0, HOLD_MAX, PROBE_OK_S, DEC_GAP_S = 0.90, 10.0, 80.0, 5.0, 1.0


class SafetyEnvelope:
    def __init__(self):
        self.hist = deque(); self.F = 0.0; self.prev_out = 0.0; self.prev_t = None; self.prev_state = "init"
        self.C_hat = None; self.hold_s = HOLD_S0; self.hold_until = 0.0; self.above_since = None; self.last_dec = -1e18
        self.last = {"state": "init", "R": 0.0, "Rt": 0.0, "excess": 0.0, "loss": 0.0, "F": 0.0, "C_hat": None, "hold": False}

    def apply(self, pred_bps, obs, t_ms):
        pred = float(pred_bps); n_long, R, q, loss = obs[15], float(obs[5]), float(obs[35]), float(obs[105])
        dt = 0.0 if self.prev_t is None else min(max((t_ms - self.prev_t) / 1000.0, 0.0), 1.0)
        self.prev_t = t_ms; t = t_ms / 1000.0
        if n_long <= 0 or R <= 0:
            self.last = dict(self.last, state="empty"); self.prev_out = pred; self.prev_state = "empty"; return pred
        Rt = R + AUDIO_BPS
        self.hist.append((t_ms, q))
        while self.hist and t_ms - self.hist[0][0] > MIN_WINDOW_S * 1000.0:
            self.hist.popleft()
        excess = q - min(v for _, v in self.hist)
        holding = self.C_hat is not None and t < self.hold_until
        if loss > LOSS_BAD or excess > EXC_BAD:
            state = "congested"
            if self.prev_state != "congested":
                failed_probe = self.C_hat is not None and not holding
                self.hold_s = min(self.hold_s * 2.0, HOLD_MAX) if failed_probe else (self.hold_s if self.C_hat is not None else HOLD_S0)
                self.C_hat = Rt; self.hold_until = t + self.hold_s; self.above_since = None
            if t - self.last_dec >= DEC_GAP_S:
                self.F = BETA * Rt; self.last_dec = t
            out = self.F
        elif loss <= LOSS_OK and excess <= EXC_OK:
            state = "clear"
            F = min(max(self.F, self.prev_out) * (ETA ** dt), CAP_K * Rt + CAP_B)
            if holding:
                F = min(F, HOLD_FRAC * self.C_hat)
            self.F = F; out = max(pred, F)
            if self.C_hat is not None and not holding:
                if out > self.C_hat:
                    self.above_since = t if self.above_since is None else self.above_since
                    if t - self.above_since >= PROBE_OK_S:
                        self.C_hat = None; self.hold_s = HOLD_S0; self.above_since = None
                else:
                    self.above_since = None
        else:
            state = "mild"; out = max(pred, self.F)
        self.prev_out = out; self.prev_state = state
        self.last = {"state": state, "R": R, "Rt": Rt, "excess": excess, "loss": loss, "F": self.F,
                     "C_hat": self.C_hat, "hold": bool(self.C_hat is not None and t < self.hold_until)}
        return out
