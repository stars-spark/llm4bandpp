# -*- coding: utf-8 -*-
"""Arm arm_llm4band_conf: LLM4Band online, with collector v5.
Model class bwe_agent_Qwen_base from the original online code (single-scale state encoder, Qwen1.5-0.5B body, output head) with the conference weights qwen_merged_conference.pth, loaded as in the original entry point; trace fields match LLM4bandppV5Estimator.
"""
import json, os, time
from estimator.online_llm_arms_v1 import _collector, _trace_handle


class LLM4bandConfV5Estimator:
    ARM_NAME = "LLM4Band-conf"

    def __init__(self):
        import torch
        from estimator.estimator import bwe_agent_Qwen_base
        self.torch = torch; torch.set_num_threads(int(os.environ.get("BWE_TORCH_THREADS", "4")))
        self.collector_name, self.collector = _collector("v5")
        dev = torch.device("cpu"); self.model = bwe_agent_Qwen_base(device=dev)
        ck = os.environ.get("BWE_CONF_CHECKPOINT", "/app/model/qwen_merged_conference.pth")
        try: state = torch.load(ck, map_location=dev, weights_only=True)
        except TypeError: state = torch.load(ck, map_location=dev)
        for name in ("stateencoder", "llm", "bwe_head"): getattr(self.model, name).load_state_dict(state[name], strict=True)
        self.model.eval(); self.r = 0; self.trace = _trace_handle()

    def report_states(self, stats):
        self.collector.report_states(stats)

    def predict_bps(self, obs):
        with self.torch.inference_mode():
            return float(self.model.forward(self.torch.tensor(obs, dtype=self.torch.float32).reshape(1, 150)))

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); bps = max(self.predict_bps(obs), 0.0)
        if self.trace:
            self.trace.write(json.dumps({"r": self.r, "t_ms": self.collector.clock(), "arm": 0, "arm_name": self.ARM_NAME, "preds_mbps": [bps / 1e6], "obs": obs,
                                         "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps, "collector": self.collector_name,
                                         "est_bps": bps, "envelope": None, "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        self.r += 1
        return int(bps)
