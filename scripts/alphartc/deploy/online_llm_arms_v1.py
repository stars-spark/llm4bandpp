# -*- coding: utf-8 -*-
"""Two online estimators that keep the LLM in the closed loop. LLM4bandppV5Estimator (BWE_ESTIMATOR=arm_llm4bandpp): the LLM variant (the earlier LLM4band++ checkpoint with Qwen)
fed by collector v5 and loaded as in BandwidthEstimator_staleness._load_qwen_dual. LLMSwitchEstimator (switch_llm): four experts run every step and an LLM in a background
worker (llm_switcher_v1.py) picks the arm; trace fields match SwitchEstimator.
First file of the family (there is no v2), loaded by every estimator entry point version. arm_llm4bandpp served llm4bandpp-online-lock-diagnosis-v1, the diagnosis that led to
collector v6 and the arms of online_llm_arms_v3.py.
"""
import json, os, time
from pathlib import Path


def _collector(default):
    name = (os.environ.get("BWE_COLLECTOR", "") or default).strip().lower()
    if name == "v5":
        from estimator.spec_collector_v5 import SlidingCollectorV5
        return name, SlidingCollectorV5()
    if name == "v3":
        from estimator.spec_collector import SlidingCollector
        return name, SlidingCollector()
    raise ValueError("BWE_COLLECTOR only accepts v3 or v5, got %r" % name)


def _trace_handle():
    tp = (os.environ.get("BWE_SWITCH_TRACE", "") or os.environ.get("BWE_OBS_TRACE", "")).strip()
    return open(tp, "a") if tp else None


class LLM4bandppV5Estimator:
    def __init__(self):
        import torch
        from estimator.estimator_dual import bwe_agent_Qwen_dual
        self.torch = torch; threads = int(os.environ.get("BWE_TORCH_THREADS", "4")); torch.set_num_threads(threads)
        self.collector_name, self.collector = _collector("v5")
        dev = torch.device("cpu"); self.model = bwe_agent_Qwen_dual(device=dev)
        ck = os.environ.get("BWE_QWEN_CHECKPOINT", "/app/model/Qwen_dual_merged.pth")
        try: state = torch.load(ck, map_location=dev, weights_only=True)
        except TypeError: state = torch.load(ck, map_location=dev)
        for name in ("stateencoder", "llm", "bwe_head"): getattr(self.model, name).load_state_dict(state[name], strict=True)
        if "encoder0" in state: self.model.encoder0.data.copy_(state["encoder0"].to(dev))
        self.model.eval(); self.r = 0; self.trace = _trace_handle()

    def report_states(self, stats):
        self.collector.report_states(stats)

    def predict_bps(self, obs):
        with self.torch.inference_mode():
            return float(self.model.forward(self.torch.tensor(obs, dtype=self.torch.float32).reshape(1, 150)))

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); bps = max(self.predict_bps(obs), 0.0)
        if self.trace:
            self.trace.write(json.dumps({"r": self.r, "t_ms": self.collector.clock(), "arm": 0, "arm_name": "LLM4band++", "preds_mbps": [bps / 1e6], "obs": obs,
                                         "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps, "collector": self.collector_name,
                                         "est_bps": bps, "envelope": None, "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        self.r += 1
        return int(bps)


class LLMSwitchEstimator:
    def __init__(self):
        from estimator.switcher import ArmBank, block_features
        from estimator.llm_switcher_v1 import AsyncLLMSwitchCore
        d = os.environ.get("BWE_SWITCH_MODEL_DIR", "/app/model/switch_v1"); md = os.environ.get("BWE_LLM_SWITCH_DIR", "/app/model/switch_llm_v1")
        self.collector_name, self.collector = _collector("v5"); self.bank = ArmBank(d)
        self.core = AsyncLLMSwitchCore(block_features, str(Path(__file__).resolve().parent / "llm_switch_worker_v1.py"), md,
                                       threads=int(os.environ.get("BWE_LLM_SWITCH_THREADS", "4")))
        self.trace = _trace_handle()

    def report_states(self, stats):
        self.collector.report_states(stats)

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); preds = self.bank.step(obs)
        pred, arm = self.core.step(obs[0] / 1e6, obs[30], obs[60], obs[90], obs[100], preds); est_bps = max(pred, 0.0) * 1e6
        if self.trace:
            self.trace.write(json.dumps({"r": self.core.r - 1, "t_ms": self.collector.clock(), "arm": arm, "preds_mbps": [float(v) for v in preds], "obs": obs,
                                         "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps, "collector": self.collector_name,
                                         "est_bps": est_bps, "envelope": None, "llm": dict(self.core.last), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
