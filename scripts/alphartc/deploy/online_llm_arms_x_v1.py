# -*- coding: utf-8 -*-
"""Arm switch_llm_x: the LLM switcher with selectable collector (BWE_COLLECTOR v5 or v6) and probing envelope (BWE_ENVELOPE 0 or 4). It has the structure of switch_nn_x
(switcher_x_v1.py) with the decision core replaced by the background LLM of llm_switcher_v1.py; experts and switch features see the observation with audio restored,
the envelope the raw one. With collector v5 and envelope 0 it matches switch_llm.
New file next to online_llm_arms_v1.py, loaded by estimator entry point v2 and later; used only by switcher batches that the paper does not use.
"""
import json, os, time
from pathlib import Path


class LLMSwitchXEstimator:
    def __init__(self):
        from estimator.switcher import ArmBank, block_features
        from estimator.llm_switcher_v1 import AsyncLLMSwitchCore
        name = (os.environ.get("BWE_COLLECTOR", "") or "v5").strip().lower()
        if name == "v6":
            from estimator.spec_collector_v6 import SlidingCollectorV6
            self.collector = SlidingCollectorV6()
        elif name == "v5":
            from estimator.spec_collector_v5 import SlidingCollectorV5
            self.collector = SlidingCollectorV5()
        else:
            raise ValueError("BWE_COLLECTOR only accepts v5 or v6, got %r" % name)
        self.collector_name = name
        self.envelope_name = (os.environ.get("BWE_ENVELOPE", "") or "0").strip()
        if self.envelope_name == "4":
            from estimator.safety_envelope_v4 import SafetyEnvelope
            self.envelope = SafetyEnvelope()
        elif self.envelope_name == "0":
            self.envelope = None
        else:
            raise ValueError("switch_llm_x BWE_ENVELOPE only accepts 0 or 4, got %r" % self.envelope_name)
        d = os.environ.get("BWE_SWITCH_MODEL_DIR", "/app/model/switch_v1"); md = os.environ.get("BWE_LLM_SWITCH_DIR", "/app/model/switch_llm_v1")
        self.bank = ArmBank(d)
        self.core = AsyncLLMSwitchCore(block_features, str(Path(__file__).resolve().parent / "llm_switch_worker_v1.py"), md,
                                       threads=int(os.environ.get("BWE_LLM_SWITCH_THREADS", "4")))
        tp = (os.environ.get("BWE_SWITCH_TRACE", "") or os.environ.get("BWE_OBS_TRACE", "")).strip()
        self.trace = open(tp, "a") if tp else None

    def report_states(self, stats):
        self.collector.report_states(stats)

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        preds = self.bank.step(obs); pred, arm = self.core.step(obs[0] / 1e6, obs[30], obs[60], obs[90], obs[100], preds)
        model_bps = max(pred, 0.0) * 1e6
        est_bps = self.envelope.apply(model_bps, raw, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"r": self.core.r - 1, "t_ms": self.collector.clock(), "arm": arm, "preds_mbps": [float(v) for v in preds], "obs": raw,
                                         "audio_restored": self.collector_name == "v6", "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps,
                                         "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": est_bps, "model_bps": model_bps,
                                         "envelope": (self.envelope.last if self.envelope is not None else None), "llm": dict(self.core.last),
                                         "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
