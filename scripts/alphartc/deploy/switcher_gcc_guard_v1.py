# -*- coding: utf-8 -*-
"""Arm switch_gccguard: switch_nn with a loss-yield guard driven by a shadow GCC that is reset to the actual output every step.
The guard engages only on congestion loss: long-window (3 s) loss at least 2% and short-window queuing delay at least 12.5 ms above the 30 s minimum (first 6 s excluded), both GCC thresholds. While engaged the output is min(expert, shadow GCC), held for 6 s after the condition clears.
The guard never raises the estimate; with no loss the arm matches switch_nn step for step, and the trace adds a guard field.
"""
import json, os, time
from estimator.switcher import SwitchEstimator

LOSS_ON, DELAY_ON_MS, HOLD_MS, BASE_WIN_MS, STARTUP_SKIP_MS = 0.02, 12.5, 6000.0, 30000.0, 6000.0


class LossGuard:
    def __init__(self, loss_on=LOSS_ON, delay_on_ms=DELAY_ON_MS, hold_ms=HOLD_MS):
        from collections import deque
        self.loss_on, self.delay_on, self.hold_ms, self.until, self.t0, self.win = loss_on, delay_on_ms, hold_ms, -1.0, None, deque()
        self.last = {"active": False, "loss": 0.0, "delay_rise_ms": None, "gcc_bps": None, "lowered": False}

    def apply(self, est_bps, gcc_bps, loss, now_ms, qdelay_ms=None):
        if self.t0 is None: self.t0 = now_ms
        rise = None
        if qdelay_ms is not None:
            if now_ms - self.t0 >= STARTUP_SKIP_MS: self.win.append((now_ms, qdelay_ms))
            while self.win and self.win[0][0] < now_ms - BASE_WIN_MS: self.win.popleft()
            if self.win: rise = qdelay_ms - min(v for _, v in self.win)
        if loss >= self.loss_on and rise is not None and rise >= self.delay_on: self.until = now_ms + self.hold_ms
        active = now_ms < self.until; out = est_bps
        if active and gcc_bps is not None and gcc_bps > 0: out = min(est_bps, float(gcc_bps))
        self.last = {"active": bool(active), "loss": float(loss), "delay_rise_ms": (float(rise) if rise is not None else None), "gcc_bps": (float(gcc_bps) if gcc_bps is not None else None), "lowered": bool(out < est_bps)}
        return out


class GccGuardSwitchEstimator(SwitchEstimator):
    def __init__(self):
        super().__init__(fixed_arm=None)
        from estimator.gcc import GCCEstimator
        self.gcc = GCCEstimator(); self.guard = LossGuard()

    def report_states(self, stats):
        self.collector.report_states(stats); self.gcc.report_states(stats)

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); preds = self.bank.step(obs)
        pred, arm = self.core.step(obs[0] / 1e6, obs[30], obs[60], obs[90], obs[100], preds); est_bps = max(pred, 0.0) * 1e6
        try: gcc_bps = float(self.gcc.get_estimated_bandwidth())
        except Exception: gcc_bps = None
        loss = sum(float(v) for v in obs[105:110]) / 5.0; qd = sum(float(v) for v in obs[30:35]) / 5.0; out = self.guard.apply(est_bps, gcc_bps, loss, self.collector.clock(), qd)
        try: self.gcc.change_bandwidth_estimation(int(out))
        except Exception: pass
        if self.trace:
            self.trace.write(json.dumps({"r": self.core.r - 1, "t_ms": self.collector.clock(), "arm": arm, "preds_mbps": [float(v) for v in preds], "obs": obs,
                                         "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps, "collector": self.collector_name, "envelope_version": "0",
                                         "est_bps": out, "envelope": None, "guard": dict(self.guard.last, expert_bps=est_bps), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(out)
