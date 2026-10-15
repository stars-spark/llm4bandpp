# -*- coding: utf-8 -*-
"""Arm arm_llm4bandpp_schema: the one-token LLM variant (Qwen_dual_merged.pth on CPU, collector v6, probing envelope v4) behind a client interface layer and adapter.
BWE_OBS_SCHEMA rewrites the collector output into a synthetic schema (the ten of fixed_schema_x_v1 plus rt_getstats, named and scaled after WebRTC getStats) and BWE_OBS_MAP maps it back to the 15 interface features; the adapted observation feeds the model (with audio) and the envelope (raw).
Without BWE_OBS_SCHEMA it matches arm_llm4bandpp_x (collector v6, envelope v4) step for step.
"""
import json, os, time
from estimator.online_llm_arms_v3 import LLM4bandppXEstimator
from estimator.fixed_schema_x_v1 import PERM as _PERM0, FACT as _FACT0, IDENTITY, from_mapping

PERM = dict(_PERM0); FACT = dict(_FACT0)
PERM["rt_getstats"] = [11, 14, 0, 8, 9, 13, 7, 4, 5, 10, 6, 3, 12, 2, 1]
FACT["rt_getstats"] = [1, 1, 1, 1e-3, 1e-3, 1e-3, 1, 1e-3, 1e-3, 1e-3, 1, 1, 1, 1, 1]


def to_foreign(v, schema):
    """Rewrite a 150-dim interface observation (feature k, window b at k*10+b) into 15 foreign fields of 10 windows each."""
    fac = FACT[schema]
    return [[v[k * 10 + b] * fac[k] for b in range(10)] for k in PERM[schema]]


def adapt(v, schema, mp):
    return list(v) if not schema else from_mapping(to_foreign(v, schema), mp)


class SchemaLLM4bandppEstimator(LLM4bandppXEstimator):
    ARM_NAME = "LLM4band++ schema"

    def __init__(self):
        os.environ["BWE_ENVELOPE"] = "4"; os.environ["BWE_COLLECTOR"] = "v6"
        super().__init__()
        self.schema = (os.environ.get("BWE_OBS_SCHEMA", "") or "").strip()
        if self.schema and self.schema not in PERM: raise ValueError("unknown foreign schema " + self.schema)
        raw = (os.environ.get("BWE_OBS_MAP", "") or "").strip()
        self.map_tag = "IDENTITY" if raw == "IDENTITY" else ("JSON" if raw else "")
        self.mapping = IDENTITY if raw == "IDENTITY" else (json.loads(raw) if raw else IDENTITY)
        if self.schema and not raw: raise ValueError("BWE_OBS_SCHEMA is set but BWE_OBS_MAP is empty; pass IDENTITY for no adapter")

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        obs_in = adapt(obs, self.schema, self.mapping); raw_in = adapt(raw, self.schema, self.mapping)
        with self.torch.inference_mode(): model_bps = max(float(self.model.forward(self.torch.tensor(obs_in, dtype=self.torch.float32).reshape(1, 150))), 0.0)
        bps = self.envelope.apply(model_bps, raw_in, self.collector.clock())
        if self.trace:
            self.trace.write(json.dumps({"r": self.r, "t_ms": self.collector.clock(), "arm": 0, "arm_name": self.ARM_NAME, "preds_mbps": [model_bps / 1e6], "obs": raw, "obs_est": obs,
                                         "schema": self.schema, "map": self.map_tag, "collector": self.collector_name, "envelope_version": self.envelope_name,
                                         "est_bps": bps, "model_bps": model_bps, "envelope": self.envelope.last, "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        self.r += 1; return int(bps)
