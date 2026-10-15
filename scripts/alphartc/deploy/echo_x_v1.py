# -*- coding: utf-8 -*-
"""Arm echo_x: a non-learning estimator behind the probing envelope. The estimate handed to the envelope is the collector's receiving rate (obs[0], bit/s), a zero-parameter echo;
collector (v5 or v6), four-expert bank and envelope (0 or 4) are shared with switch_nn_x and arm_*_x, and the experts still run every step for equal compute load,
so the closed-loop gap between echo_x and switch_nn_x is due to the learned experts and selection alone.
First version, a subclass of switcher_x_v1.SwitchXEstimator written for closedloop-envelope-echo-v1; loaded by estimator entry points v3 to v9, while v10 and later load echo_x_v2.py.
"""
import json, time
from estimator.switcher_x_v1 import SwitchXEstimator


class EchoXEstimator(SwitchXEstimator):
    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        preds = self.bank.step(obs)
        model_bps = max(float(obs[0]), 0.0)
        est_bps = self.envelope.apply(model_bps, raw, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"t_ms": self.collector.clock(), "arm": -1, "echo": True, "preds_mbps": [float(v) for v in preds], "obs": raw,
                                         "audio_restored": self.collector_name == "v6", "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps,
                                         "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": est_bps, "model_bps": model_bps,
                                         "envelope": (self.envelope.last if self.envelope is not None else None), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
