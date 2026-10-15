# -*- coding: utf-8 -*-
"""Arm switch_nn_x: the lightweight switcher with selectable collector (v5, v6; v6 restores the unreported audio stream) and probing envelope (0, 4).
With v5 and envelope 0 it matches switch_nn step for step; the envelope always sees the observation without audio. The trace adds model_bps and audio_restored.
"""
import json, os, time
from estimator.switcher import SwitchEstimator


class SwitchXEstimator(SwitchEstimator):
    def __init__(self):
        name = (os.environ.get("BWE_COLLECTOR", "") or "v5").strip().lower()
        os.environ["BWE_COLLECTOR"] = "v5" if name == "v6" else name
        super().__init__(fixed_arm=None)
        os.environ["BWE_COLLECTOR"] = name
        if name == "v6":
            from estimator.spec_collector_v6 import SlidingCollectorV6
            self.collector = SlidingCollectorV6(); self.collector_name = "v6"

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        preds = self.bank.step(obs); pred, arm = self.core.step(obs[0] / 1e6, obs[30], obs[60], obs[90], obs[100], preds)
        model_bps = max(pred, 0.0) * 1e6
        est_bps = self.envelope.apply(model_bps, raw, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"r": self.core.r - 1, "t_ms": self.collector.clock(), "arm": arm, "preds_mbps": [float(v) for v in preds], "obs": raw,
                                         "audio_restored": self.collector_name == "v6", "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps,
                                         "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": est_bps, "model_bps": model_bps,
                                         "envelope": (self.envelope.last if self.envelope is not None else None), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
