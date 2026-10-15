# -*- coding: utf-8 -*-
"""Arm arm_schaferct_public_x: one fixed expert (the challenge baseline, schaferct_public.onnx) behind the probing envelope, with no switching network. Collector (v5 or v6), four-expert bank
and envelope (0 or 4) are shared with switch_nn_x, so the closed-loop gap between the two comes from arm selection alone; the envelope sees the raw observation without audio,
since it adds its own audio constant.
First version, a subclass of switcher_x_v1.SwitchXEstimator written for closedloop-envelope-attribution-v1 and loaded by every estimator entry point version.
fixed_schema_x_v1.py builds on it arm_default_schema, the challenge baseline downstream in obsschema-closedloop-v2 (Table IV, Fig. 3(c)).
"""
import json, time
from estimator.switcher_x_v1 import SwitchXEstimator

ARM_INDEX = {"arm_pioneer_x": 0, "arm_schaferct_public_x": 1, "arm_schaferct_retrained_x": 2, "arm_mlp_x": 3}


class FixedXEstimator(SwitchXEstimator):
    def __init__(self, name):
        super().__init__()
        self.fixed = ARM_INDEX[name]

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        preds = self.bank.step(obs)
        arm = self.fixed
        model_bps = max(float(preds[arm]), 0.0) * 1e6
        est_bps = self.envelope.apply(model_bps, raw, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"t_ms": self.collector.clock(), "arm": arm, "fixed": True, "preds_mbps": [float(v) for v in preds], "obs": raw,
                                         "audio_restored": self.collector_name == "v6", "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps,
                                         "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": est_bps, "model_bps": model_bps,
                                         "envelope": (self.envelope.last if self.envelope is not None else None), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
