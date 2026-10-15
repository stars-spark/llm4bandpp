# -*- coding: utf-8 -*-
"""Arms arm_llm4bandpp_x and arm_llm4band_conf_x: the LLM variant and LLM4Band with selectable collector (BWE_COLLECTOR v5 or v6; v6 restores the unreported audio stream)
and probing envelope (BWE_ENVELOPE 0 or 4); with v5 and 0 they match arm_llm4bandpp and arm_llm4band_conf step for step. The envelope sees the observation without audio,
since it adds its own audio constant.
New file, not a copy of online_llm_arms_v1.py, written for llm4bandpp-online-unlock-v1. Loaded by estimator entry points up to v9; v10 and later load online_llm_arms_v4.py.
"""
import json, os, time


def _collector():
    name = (os.environ.get("BWE_COLLECTOR", "") or "v5").strip().lower()
    if name == "v6":
        from estimator.spec_collector_v6 import SlidingCollectorV6
        return name, SlidingCollectorV6()
    if name == "v5":
        from estimator.spec_collector_v5 import SlidingCollectorV5
        return name, SlidingCollectorV5()
    raise ValueError("BWE_COLLECTOR only accepts v5 or v6, got %r" % name)


def _envelope():
    name = (os.environ.get("BWE_ENVELOPE", "") or "0").strip()
    if name == "4":
        from estimator.safety_envelope_v4 import SafetyEnvelope
        return name, SafetyEnvelope()
    if name == "0": return name, None
    raise ValueError("BWE_ENVELOPE only accepts 0 or 4, got %r" % name)


class _Base:
    ARM_NAME = None

    def _build(self, torch, dev): raise NotImplementedError

    def __init__(self):
        import torch
        self.torch = torch; torch.set_num_threads(int(os.environ.get("BWE_TORCH_THREADS", "4"))); self.collector_name, self.collector = _collector(); self.envelope_name, self.envelope = _envelope()
        self.model = self._build(torch, torch.device("cpu")); self.model.eval(); self.r = 0; tp = (os.environ.get("BWE_SWITCH_TRACE", "") or os.environ.get("BWE_OBS_TRACE", "")).strip(); self.trace = open(tp, "a") if tp else None

    def report_states(self, stats): self.collector.report_states(stats)

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        with self.torch.inference_mode(): model_bps = max(float(self.model.forward(self.torch.tensor(obs, dtype=self.torch.float32).reshape(1, 150))), 0.0)
        bps = self.envelope.apply(model_bps, raw, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"r": self.r, "t_ms": self.collector.clock(), "arm": 0, "arm_name": self.ARM_NAME, "preds_mbps": [model_bps / 1e6], "obs": raw, "audio_restored": self.collector_name == "v6",
                                         "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps, "collector": self.collector_name, "envelope_version": self.envelope_name,
                                         "est_bps": bps, "model_bps": model_bps, "envelope": (self.envelope.last if self.envelope is not None else None), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        self.r += 1; return int(bps)


def _load(torch, model, path, dev, with_scale):
    try: state = torch.load(path, map_location=dev, weights_only=True)
    except TypeError: state = torch.load(path, map_location=dev)
    for name in ("stateencoder", "llm", "bwe_head"): getattr(model, name).load_state_dict(state[name], strict=True)
    if with_scale and "encoder0" in state: model.encoder0.data.copy_(state["encoder0"].to(dev))
    return model


class LLM4bandppXEstimator(_Base):
    ARM_NAME = "LLM4band++"

    def _build(self, torch, dev):
        from estimator.estimator_dual import bwe_agent_Qwen_dual
        return _load(torch, bwe_agent_Qwen_dual(device=dev), os.environ.get("BWE_QWEN_CHECKPOINT", "/app/model/Qwen_dual_merged.pth"), dev, True)


class LLM4bandConfXEstimator(_Base):
    ARM_NAME = "LLM4Band-conf"

    def _build(self, torch, dev):
        from estimator.estimator import bwe_agent_Qwen_base
        return _load(torch, bwe_agent_Qwen_base(device=dev), os.environ.get("BWE_CONF_CHECKPOINT", "/app/model/qwen_merged_conference.pth"), dev, False)
