# -*- coding: utf-8 -*-
"""Arm adapt_x: adapted expert plus probing envelope v4.
Collector v6, the four-expert bank and the envelope are shared with switch_nn_x and echo_x; the estimate handed to the envelope comes from an MLP trained on testbed closed-loop logs, with the shaped rate as label. The experts still run every step so all arms carry the same compute load; weights from BWE_ADAPT_MODEL.
"""
import json, os, time
import numpy as np
from estimator.switcher_x_v1 import SwitchXEstimator
from estimator.adapt_mlp_np_v1 import forward_np, load_weights


class AdaptXEstimator(SwitchXEstimator):
    def __init__(self):
        super().__init__()
        self.model_path = os.environ.get("BWE_ADAPT_MODEL", "/app/model/adapt_v1/adapt_mlp.npz")
        self.W = load_weights(self.model_path)
        assert self.W["w1"].shape == (150, 256) and self.W["scale"].shape == (150,), "adapted-expert weights have the wrong shape"

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        preds = self.bank.step(obs)
        model_bps = float(forward_np(self.W, np.asarray(obs, dtype=np.float32).reshape(1, 150))[0]) * 1e6
        model_bps = max(model_bps, 0.0)
        est_bps = self.envelope.apply(model_bps, raw, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"t_ms": self.collector.clock(), "arm": -2, "adapt": True, "preds_mbps": [float(v) for v in preds], "obs": raw,
                                         "audio_restored": self.collector_name == "v6", "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps,
                                         "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": est_bps, "model_bps": model_bps,
                                         "envelope": (self.envelope.last if self.envelope is not None else None), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
