# -*- coding: utf-8 -*-
"""Probing envelope v6 (BWE_ENVELOPE=6), the envelope of the deployed system (Fig. 2): the v4 rules plus two rules driven by a shadow GCC, the Python GCC called every 200 ms
that the GCC reference runs (gcc_pt125_c200_v1), fed the same packet reports. Rule 1: shadow GCC overuse also counts as congestion, besides loss above 0.10 and delay excess
above 300 ms. Rule 2: from congestion onset the output equals the shadow GCC rate (the model is not used) until the output stays clear above the onset total rate Cc for 5 s;
the actual output is written back to the shadow GCC each step. Periods without congestion match v4 step for step; a shadow GCC error skips the cap and the overuse test (gcc_err).
New file built from v4 (v4 and v5 unchanged) after compete-flow-v1 crossed its safety line on a shared bottleneck. Loaded through online_llm_arms_v4 to _v8 and echo_x_v2
(estimator entry point v10 and later, run scripts v15 and later).
"""
import threading
from collections import deque

ETA, CAP_K, CAP_B, BETA = 1.08, 1.5, 10000.0, 0.85
LOSS_OK, LOSS_BAD, EXC_OK, EXC_BAD = 0.02, 0.10, 100.0, 300.0
MIN_WINDOW_S = 30.0
STARTUP_SKIP_S, STARTUP_NEED_S = 6.0, 10.0
AUDIO_BPS = 41000.0
HOLD_FRAC, HOLD_S0, HOLD_MAX, PROBE_OK_S, DEC_GAP_S = 0.90, 10.0, 80.0, 5.0, 1.0
DELTA_TAU_S = 3.0


def _shadow_gcc():
    from estimator.gcc_pt125_c200_v1 import GCCEstimatorPT125C200
    return GCCEstimatorPT125C200()


class SafetyEnvelope:
    def __init__(self, gcc=None):
        self.hist = deque(); self.t_first = None; self.F = 0.0; self.prev_out = 0.0; self.prev_t = None; self.prev_state = "init"
        self.delta = 0.0; self.C_hat = None; self.hold_s = HOLD_S0; self.hold_until = 0.0; self.above_since = None; self.last_dec = -1e18
        self.gcc = gcc if gcc is not None else _shadow_gcc(); self._mu = threading.Lock(); self.gcc_err = 0; self.n_pkts = 0
        self.Cc = None; self.cc_since = None
        self.last = {"state": "init", "R": 0.0, "Rt": 0.0, "excess": 0.0, "loss": 0.0, "F": 0.0, "C_hat": None, "hold": False,
                     "gcc_bps": None, "gcc_flag": None, "gcc_state": None, "ceiling": False, "capped": False, "gcc_err": 0}

    def report_states(self, stats):
        with self._mu:
            try:
                self.gcc.report_states(stats); self.n_pkts += 1
            except Exception:
                self.gcc_err += 1

    def _gcc_read(self):
        with self._mu:
            try:
                g = float(self.gcc.get_estimated_bandwidth()); return (g if g > 0 else None), getattr(self.gcc, "overuse_flag", None), getattr(self.gcc, "state", None)
            except Exception:                      # noqa: BLE001
                self.gcc_err += 1; return None, None, None

    def _gcc_follow(self, out):
        with self._mu:
            try:
                self.gcc.change_bandwidth_estimation(int(out))
            except Exception:                      # noqa: BLE001
                self.gcc_err += 1

    def apply(self, pred_bps, obs, t_ms):
        g, flag, gstate = self._gcc_read()
        pred = float(pred_bps); n_long, R, q, loss = obs[15], float(obs[5]), float(obs[35]), float(obs[105])
        dt = 0.0 if self.prev_t is None else min(max((t_ms - self.prev_t) / 1000.0, 0.0), 1.0)
        self.prev_t = t_ms; t = t_ms / 1000.0
        if n_long <= 0 or R <= 0:
            out = pred; capped = False
            if self.Cc is not None and g is not None:
                capped = g < out; out = g; self.F = g
            self.last = dict(self.last, state="empty", gcc_bps=g, gcc_flag=flag, gcc_state=gstate, ceiling=self.Cc is not None, Cc=self.Cc, capped=capped, gcc_err=self.gcc_err)
            self.prev_out = out; self.prev_state = "empty"; self._gcc_follow(out); return out
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
        overuse = flag == "OVERUSE"
        bad = loss > LOSS_BAD or excess > EXC_BAD or overuse
        holding = self.C_hat is not None and t < self.hold_until
        calm = not bad
        if holding and calm and self.prev_out > 0 and dt > 0:
            a = 1.0 - 2.718281828459045 ** (-dt / DELTA_TAU_S)
            self.delta += a * ((Rt - self.prev_out) - self.delta)
        d = max(self.delta, 0.0)
        probe_check = False
        if bad:
            state = "congested"
            if self.prev_state != "congested":
                failed_probe = self.C_hat is not None and not holding
                self.hold_s = min(self.hold_s * 2.0, HOLD_MAX) if failed_probe else (self.hold_s if self.C_hat is not None else HOLD_S0)
                self.C_hat = Rt; self.hold_until = t + self.hold_s; self.above_since = None
                self.Cc = Rt; self.cc_since = None
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
            self.F = F; out = max(pred, F); probe_check = self.C_hat is not None and not holding
        else:
            state = "mild"; out = max(pred, self.F)
        capped = False
        if self.Cc is not None and g is not None:
            capped = g < out; out = g; self.F = g
        if self.Cc is not None:
            if state != "congested" and out > self.Cc:
                self.cc_since = t if self.cc_since is None else self.cc_since
                if t - self.cc_since >= PROBE_OK_S:
                    self.Cc = None; self.cc_since = None
            else:
                self.cc_since = None
        if probe_check:
            if out > self.C_hat:
                self.above_since = t if self.above_since is None else self.above_since
                if t - self.above_since >= PROBE_OK_S:
                    self.delta = 0.0; self.C_hat = None; self.hold_s = HOLD_S0; self.above_since = None
            else:
                self.above_since = None
        self.prev_out = out; self.prev_state = state
        self.last = {"state": state, "R": R, "Rt": Rt, "excess": excess, "loss": loss, "F": self.F,
                     "C_hat": self.C_hat, "delta": self.delta, "hold": bool(self.C_hat is not None and t < self.hold_until),
                     "gcc_bps": g, "gcc_flag": flag, "gcc_state": gstate, "ceiling": self.Cc is not None, "Cc": self.Cc, "capped": capped, "gcc_err": self.gcc_err}
        self._gcc_follow(out)
        return out
