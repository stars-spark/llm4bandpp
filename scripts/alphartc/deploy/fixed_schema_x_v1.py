# -*- coding: utf-8 -*-
"""Arm arm_default_schema: the challenge baseline (schaferct_public.onnx) and probing envelope v4 behind a client interface layer and adapter.
BWE_OBS_SCHEMA rewrites collector v6 output into a synthetic schema (field order and units from obsschema_v1) and BWE_OBS_MAP (15 entries {source, scale}; IDENTITY feeds fields in order) maps it back to the 15 interface features; the adapted observation feeds expert and envelope.
The schema tables are copied from obsschema_v1 and checked against it by test_fixed_schema_x_v1.py.
"""
import json, os, time
from estimator.fixed_x_v1 import FixedXEstimator

PERM = {"dev_a": [12, 9, 7, 10, 14, 11, 8, 2, 1, 6, 5, 3, 13, 4, 0], "dev_b": [5, 1, 3, 14, 2, 11, 7, 10, 13, 9, 12, 6, 8, 4, 0],
        "test_c": [6, 13, 2, 11, 5, 8, 9, 12, 14, 7, 0, 10, 4, 1, 3], "test_d": [7, 14, 12, 1, 9, 13, 11, 0, 3, 6, 10, 5, 4, 8, 2],
        "test_e": [3, 10, 13, 6, 12, 9, 11, 14, 1, 5, 4, 2, 8, 7, 0], "test_f": [10, 8, 1, 6, 11, 9, 5, 3, 13, 2, 4, 12, 7, 14, 0],
        "test_g": [7, 13, 14, 9, 4, 5, 12, 2, 1, 0, 10, 3, 6, 11, 8], "test_h": [14, 12, 1, 2, 4, 0, 11, 8, 9, 6, 5, 7, 3, 13, 10],
        "test_i": [10, 5, 3, 12, 13, 1, 8, 9, 6, 2, 14, 11, 4, 0, 7], "test_j": [11, 5, 12, 9, 3, 1, 7, 13, 10, 14, 6, 2, 8, 4, 0]}
FACT = {"dev_a": [1e-3, 1, 1, 1e-3, 1e-3, 1e-3, 1, 1e-3, 1, 1, 100, 1, 100, 100, 100], "dev_b": [1, 1, 8, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "test_c": [1e-6, 1, 1, 1e3, 1, 1, 1, 1e3, 1e3, 1e3, 100, 1, 100, 100, 100], "test_d": [1 / 1024, 1, 1e-3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "test_e": [1, 1, 1, 1e-3, 1e-3, 1e-3, 1, 1e-3, 1e-3, 1e-3, 1, 1, 1, 1, 1], "test_f": [1e-3, 1, 8, 1, 1, 1, 1, 1, 1, 1, 1000, 1, 100, 100, 100],
        "test_g": [1e-3, 1, 1 / 1024, 1e3, 1, 1, 1, 1e3, 1e3, 1e3, 100, 1, 1, 1, 1], "test_h": [1, 1, 1, 1e-3, 1, 1, 1, 1e-3, 1e-3, 1e-3, 1, 1, 1, 1, 1],
        "test_i": [1e-3, 1, 8, 1, 1, 1, 1, 1, 1, 1, 1000, 1, 100, 100, 100], "test_j": [1e-6, 1, 1e-3, 1e-3, 1, 1, 1, 1, 1, 1, 100, 1, 100, 100, 100]}
IDENTITY = [{"source": k, "scale": 1.0} for k in range(15)]


def to_foreign(v, schema):
    """Rewrite a 150-dim interface observation (feature k, window b at k*10+b) into 15 foreign fields of 10 windows each."""
    fac = FACT[schema]
    return [[v[k * 10 + b] * fac[k] for b in range(10)] for k in PERM[schema]]


def from_mapping(F, mp):
    out = [0.0] * 150
    for k, m in enumerate(mp[:15]):
        if m is None or m.get("source") is None: continue
        j = int(m["source"])
        if not 0 <= j < len(F): continue
        a = float(m.get("scale", 1.0))
        for b in range(10): out[k * 10 + b] = F[j][b] * a
    return out


def adapt(v, schema, mp):
    return list(v) if not schema else from_mapping(to_foreign(v, schema), mp)


class FixedSchemaXEstimator(FixedXEstimator):
    def __init__(self):
        os.environ["BWE_ENVELOPE"] = "4"
        super().__init__("arm_schaferct_public_x")
        self.schema = (os.environ.get("BWE_OBS_SCHEMA", "") or "").strip()
        if self.schema and self.schema not in PERM: raise ValueError("unknown foreign schema " + self.schema)
        raw = (os.environ.get("BWE_OBS_MAP", "") or "").strip()
        self.map_tag = "IDENTITY" if raw == "IDENTITY" else ("JSON" if raw else "")
        self.mapping = IDENTITY if raw == "IDENTITY" else (json.loads(raw) if raw else IDENTITY)
        if self.schema and not raw: raise ValueError("BWE_OBS_SCHEMA is set but BWE_OBS_MAP is empty; pass IDENTITY for no adapter")

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        obs_in = adapt(obs, self.schema, self.mapping); raw_in = adapt(raw, self.schema, self.mapping)
        preds = self.bank.step(obs_in); arm = self.fixed
        model_bps = max(float(preds[arm]), 0.0) * 1e6
        est_bps = self.envelope.apply(model_bps, raw_in, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"t_ms": self.collector.clock(), "arm": arm, "fixed": True, "preds_mbps": [float(x) for x in preds], "obs": raw, "obs_est": obs,
                                         "schema": self.schema, "map": self.map_tag, "collector": self.collector_name, "envelope_version": self.envelope_name,
                                         "est_bps": est_bps, "model_bps": model_bps, "envelope": (self.envelope.last if self.envelope is not None else None),
                                         "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        return int(est_bps)
