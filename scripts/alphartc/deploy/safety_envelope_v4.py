# -*- coding: utf-8 -*-
"""Probing envelope v4 (BWE_ENVELOPE=4): the v3 rules with the sender's rate offset corrected. delta = Rt - last output is tracked online (3 s exponential average, only in the hold
period and when not congested) and subtracted from the hold floor and the congestion backoff, so the actual rate lands on target. The delay baseline is the 30 s minimum,
dropping the first 6 s once 10 s of history exist; sustained congestion backs off by another 0.85 each second. No constant is fitted to testbed results.
Copy of v3 with these changes. In the paper it is the envelope of the challenge baseline downstream in obsschema-closedloop-v2 and of the telemetry-only configuration
(fixed_schema_ch_v2.py, hd720-designer-tel-v2 and -fid-v1; Table IV). safety_envelope_v6.py adds the shadow GCC to these rules.
"""
from collections import deque

ETA, CAP_K, CAP_B, BETA = 1.08, 1.5, 10000.0, 0.85
LOSS_OK, LOSS_BAD, EXC_OK, EXC_BAD = 0.02, 0.10, 100.0, 300.0
MIN_WINDOW_S = 30.0
STARTUP_SKIP_S, STARTUP_NEED_S = 6.0, 10.0
AUDIO_BPS = 41000.0
HOLD_FRAC, HOLD_S0, HOLD_MAX, PROBE_OK_S, DEC_GAP_S = 0.90, 10.0, 80.0, 5.0, 1.0
DELTA_TAU_S = 3.0


class SafetyEnvelope:
    def __init__(self):
        self.hist = deque(); self.t_first = None; self.F = 0.0; self.prev_out = 0.0; self.prev_t = None; self.prev_state = "init"
        self.delta = 0.0; self.C_hat = None; self.hold_s = HOLD_S0; self.hold_until = 0.0; self.above_since = None; self.last_dec = -1e18
        self.last = {"state": "init", "R": 0.0, "Rt": 0.0, "excess": 0.0, "loss": 0.0, "F": 0.0, "C_hat": None, "hold": False}

    def apply(self, pred_bps, obs, t_ms):
        pred = float(pred_bps); n_long, R, q, loss = obs[15], float(obs[5]), float(obs[35]), float(obs[105])
        dt = 0.0 if self.prev_t is None else min(max((t_ms - self.prev_t) / 1000.0, 0.0), 1.0)
        self.prev_t = t_ms; t = t_ms / 1000.0
        if n_long <= 0 or R <= 0:
            self.last = dict(self.last, state="empty"); self.prev_out = pred; self.prev_state = "empty"; return pred
        Rt = R + AUDIO_BPS
        if self.t_first is None:
            self.t_first = t_ms
        self.hist.append((t_ms, q))
        while self.hist and t_ms - self.hist[0][0] > MIN_WINDOW_S * 1000.0:
            self.hist.popleft()
        age = (t_ms - self.t_first) / 1000.0
        if age >= STARTUP_SKIP_S + STARTUP_NEED_S:
            elig = [v for ts, v in self.hist if (ts - self.t_first) / 1000.0 >= STARTUP_SKIP_S]
            base = min(elig) if elig else min(v for _, v in self.hist)
        else:
            base = min(v for _, v in self.hist)
        excess = q - base
        holding = self.C_hat is not None and t < self.hold_until
        calm = not (loss > LOSS_BAD or excess > EXC_BAD)
        if holding and calm and self.prev_out > 0 and dt > 0:
            a = 1.0 - 2.718281828459045 ** (-dt / DELTA_TAU_S)
            self.delta += a * ((Rt - self.prev_out) - self.delta)
        d = max(self.delta, 0.0)
        if loss > LOSS_BAD or excess > EXC_BAD:
            state = "congested"
            if self.prev_state != "congested":
                failed_probe = self.C_hat is not None and not holding
                self.hold_s = min(self.hold_s * 2.0, HOLD_MAX) if failed_probe else (self.hold_s if self.C_hat is not None else HOLD_S0)
                self.C_hat = Rt; self.hold_until = t + self.hold_s; self.above_since = None
            if t - self.last_dec >= DEC_GAP_S:
                target = max(BETA * Rt - d, 0.0)
                if self.prev_state == "congested":
                    target = min(target, BETA * self.F)
                self.F = target; self.last_dec = t
            out = self.F
        elif loss <= LOSS_OK and excess <= EXC_OK:
            state = "clear"
            F = min(max(self.F, self.prev_out) * (ETA ** dt), CAP_K * Rt + CAP_B)
            if holding:
                F = min(F, max(HOLD_FRAC * self.C_hat - d, 0.0))
            self.F = F; out = max(pred, F)
            if self.C_hat is not None and not holding:
                if out > self.C_hat:
                    self.above_since = t if self.above_since is None else self.above_since
                    if t - self.above_since >= PROBE_OK_S:
                        self.delta = 0.0; self.C_hat = None; self.hold_s = HOLD_S0; self.above_since = None
                else:
                    self.above_since = None
        else:
            state = "mild"; out = max(pred, self.F)
        self.prev_out = out; self.prev_state = state
        self.last = {"state": state, "R": R, "Rt": Rt, "excess": excess, "loss": loss, "F": self.F,
                     "C_hat": self.C_hat, "delta": self.delta, "hold": bool(self.C_hat is not None and t < self.hold_until)}
        return out
