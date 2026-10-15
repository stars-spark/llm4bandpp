# -*- coding: utf-8 -*-
"""Arm arm_default_repair: the challenge baseline with an observation fault layer and a repair layer.
Collector v6 output is first corrupted by BWE_OBS_FAULT (simulated unit errors: kbit/s rates, shifted delay origin, swapped windows and others) and then repaired by BWE_OBS_REPAIR (JSON ops, as obsrepair_v1.apply_ops); the repaired observation feeds both the challenge baseline and probing envelope v4.
Without either variable it matches arm_schaferct_public_x with envelope v4 step for step; the trace adds obs_fault.
"""
import json, os, time
from estimator.fixed_x_v1 import FixedXEstimator
ORIGIN = 1.79e12


def fault(v, name):
    v = list(v)
    if name == "F_kbps_real":
        for i in range(0, 10): v[i] *= 1e-3
    elif name == "F_origin_real":
        for f in (4, 5):
            for i in range(f * 10, f * 10 + 10): v[i] += ORIGIN
    elif name == "F_swap":
        for f in range(15): v[f * 10:f * 10 + 5], v[f * 10 + 5:f * 10 + 10] = v[f * 10 + 5:f * 10 + 10], v[f * 10:f * 10 + 5]
    elif name == "F_bits":
        for i in range(20, 30): v[i] *= 8
    elif name == "F_kB":
        for i in range(20, 30): v[i] *= 1e-3
    elif name == "F_mbps":
        for i in range(0, 10): v[i] *= 1e-6
    elif name in ("F_sec", "F_us"):
        for f in (3, 4, 5, 7):
            for i in range(f * 10, f * 10 + 10): v[i] *= (1e-3 if name == "F_sec" else 1e3)
    elif name == "F_pktps":
        for i in range(10, 15): v[i] /= 0.06
        for i in range(15, 20): v[i] /= 0.6
    elif name not in ("", "CLEAN"): raise ValueError("unknown error " + name)
    return v


def apply_ops(v, ops):
    v = list(v)
    for op in ops:
        if op.get("swap_windows"):
            for f in range(15): v[f * 10:f * 10 + 5], v[f * 10 + 5:f * 10 + 10] = v[f * 10 + 5:f * 10 + 10], v[f * 10:f * 10 + 5]
    for op in ops:
        if "feature" in op:
            k = int(op["feature"]); w = op.get("windows", "all"); lo, hi = (k * 10, k * 10 + 10) if w == "all" else ((k * 10, k * 10 + 5) if w == "short" else (k * 10 + 5, k * 10 + 10))
            for i in range(lo, hi): v[i] = v[i] * float(op.get("scale", 1.0)) + float(op.get("offset", 0.0))
    return v


class FixedRepairXEstimator(FixedXEstimator):
    def __init__(self):
        os.environ["BWE_ENVELOPE"] = "4"
        super().__init__("arm_schaferct_public_x")
        self.fault_name = (os.environ.get("BWE_OBS_FAULT", "") or "").strip()
        raw = (os.environ.get("BWE_OBS_REPAIR", "") or "").strip(); self.ops = json.loads(raw) if raw else []

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        obs_f = fault(obs, self.fault_name); obs_in = apply_ops(obs_f, self.ops); raw_in = apply_ops(fault(raw, self.fault_name), self.ops)
        preds = self.bank.step(obs_in); arm = self.fixed
        model_bps = max(float(preds[arm]), 0.0) * 1e6
        est_bps = self.envelope.apply(model_bps, raw_in, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"t_ms": self.collector.clock(), "arm": arm, "fixed": True, "preds_mbps": [float(x) for x in preds], "obs": raw, "obs_fault": obs_f,
                                         "fault": self.fault_name, "n_ops": len(self.ops), "collector": self.collector_name, "envelope_version": self.envelope_name,
                                         "est_bps": est_bps, "model_bps": model_bps, "envelope": (self.envelope.last if self.envelope is not None else None),
                                         "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
