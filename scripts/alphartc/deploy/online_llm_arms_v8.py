# -*- coding: utf-8 -*-
"""The arms of online_llm_arms_v7.py with an estimate floor: BWE_MIN_BPS_FLOOR=1 keeps the model estimate at or above 5 kbps (AlphaRTC congestion_controller::GetMinBitrateBps),
applied before the guard and the envelope, so an estimate of 0 never pauses the sender; the trace adds model_raw_bps and floor_hit.
Copy of v7; unset, it matches v7 step for step. The deployed system is arm_ch_x of this file with collector v6, the floor and envelope v6. Loaded by estimator entry point v15
and later (run scripts v20 to v29); fixed_x_v2.py, fixed_schema_ch_v1.py and fixed_schema_ch_v2.py build on its classes.
"""
import json, os, time


def _collector():
    name = (os.environ.get("BWE_COLLECTOR", "") or "v5").strip().lower()
    if name == "v7":
        from estimator.spec_collector_v7 import SlidingCollectorV7
        return name, SlidingCollectorV7()
    if name == "v6":
        from estimator.spec_collector_v6 import SlidingCollectorV6
        return name, SlidingCollectorV6()
    if name == "v5":
        from estimator.spec_collector_v5 import SlidingCollectorV5
        return name, SlidingCollectorV5()
    raise ValueError("BWE_COLLECTOR only accepts v5, v6, or v7, got %r" % name)


def _envelope():
    name = (os.environ.get("BWE_ENVELOPE", "") or "0").strip()
    if name == "4":
        from estimator.safety_envelope_v4 import SafetyEnvelope
        return name, SafetyEnvelope()
    if name == "6":
        from estimator.safety_envelope_v6 import SafetyEnvelope
        return name, SafetyEnvelope()
    if name == "0": return name, None
    raise ValueError("BWE_ENVELOPE only accepts 0, 4, or 6, got %r" % name)


class _Base:
    ARM_NAME = None

    def _build(self, torch, dev): raise NotImplementedError

    GUARD_BPS = 300000.0
    FLOOR_BPS = 5000.0

    def __init__(self):
        import torch
        self.guard_on = (os.environ.get("BWE_STARTUP_GUARD", "") or "0").strip() == "1"
        self.floor_on = (os.environ.get("BWE_MIN_BPS_FLOOR", "") or "0").strip() == "1"
        self.torch = torch; torch.set_num_threads(int(os.environ.get("BWE_TORCH_THREADS", "4"))); self.collector_name, self.collector = _collector(); self.envelope_name, self.envelope = _envelope()
        self.model = self._build(torch, torch.device("cpu")); self.model.eval(); self.r = 0; tp = (os.environ.get("BWE_SWITCH_TRACE", "") or os.environ.get("BWE_OBS_TRACE", "")).strip(); self.trace = open(tp, "a") if tp else None

    def report_states(self, stats):
        self.collector.report_states(stats)
        rs = getattr(self.envelope, "report_states", None)
        if rs is not None: rs(stats)

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        with self.torch.inference_mode(): model_raw = float(self.model.forward(self.torch.tensor(obs, dtype=self.torch.float32).reshape(1, 150)))
        model_bps = max(model_raw, 0.0); floor_hit = self.floor_on and model_bps < self.FLOOR_BPS
        if floor_hit: model_bps = self.FLOOR_BPS
        if self.guard_on and all(raw[15 + s] > 0 for s in range(5)): self.guard_on = False
        x = min(model_bps, self.GUARD_BPS) if self.guard_on else model_bps
        bps = self.envelope.apply(x, raw, self.collector.clock()) if self.envelope is not None else x
        if self.trace:
            self.trace.write(json.dumps({"r": self.r, "t_ms": self.collector.clock(), "arm": 0, "arm_name": self.ARM_NAME, "preds_mbps": [model_bps / 1e6], "obs": raw, "audio_restored": self.collector_name in ("v6", "v7"),
                                         "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps, "collector": self.collector_name, "envelope_version": self.envelope_name,
                                         "est_bps": bps, "model_bps": model_bps, "guard_on": self.guard_on, "model_raw_bps": model_raw, "floor_hit": floor_hit, "envelope": (self.envelope.last if self.envelope is not None else None), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
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


class _MeanOnly:
    """Wrap a bwe_agent so that forward returns only the mean of its (mean, std) output, as _Base expects."""
    def __init__(self, agent): self.agent = agent
    def eval(self): self.agent.eval(); return self
    def forward(self, x): return self.agent(x)[0]


class NLXEstimator(_Base):
    ARM_NAME = "LLM4band++ (no LLM)"

    def _build(self, torch, dev):
        from estimator.nl_estimator_v1 import load_agent
        return _MeanOnly(load_agent(os.environ.get("BWE_NL_CHECKPOINT", "/app/model/nl_v1/nl_s1.pt"), str(dev)))


class CHXEstimator(_Base):
    """Deployed estimator arm arm_ch_x: conference encoder with the HCQ reward, no LLM; collector and envelope as for NLXEstimator."""
    ARM_NAME = "C-H (conference encoder + HCQ, no LLM)"

    def _build(self, torch, dev):
        from estimator.ch_estimator_v1 import load_agent
        return _MeanOnly(load_agent(os.environ.get("BWE_CH_CHECKPOINT", "/app/model/ch_v1/ch.pt"), str(dev)))

