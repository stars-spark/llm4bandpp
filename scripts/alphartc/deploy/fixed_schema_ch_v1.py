# -*- coding: utf-8 -*-
"""Arm arm_ch_schema: the deployed system (C-H with ch.pt, collector v6, 5 kbps floor, probing envelope v6) behind a client interface layer and adapter. BWE_OBS_SCHEMA rewrites
the collector output into a foreign schema and BWE_OBS_MAP maps it back to the 15 interface features; the adapted observation feeds both model and envelope, while the envelope's
shadow GCC reads native packet reports. Without BWE_OBS_SCHEMA it matches arm_ch_x (collector v6, envelope v6, floor on, guard off) step for step.
New file: a subclass of online_llm_arms_v8.CHXEstimator that imports the interface layer (PERM, adapt, IDENTITY) from fixed_schema_nl_v1.py and fixed_schema_x_v1.py.
Loaded by estimator entry point v17 and later (run script v25) for hd720-designer-ch-v1, the 720p deployed-system row of Table IV.
"""
import json, os, time
from estimator.online_llm_arms_v8 import CHXEstimator
from estimator.fixed_schema_nl_v1 import PERM, adapt
from estimator.fixed_schema_x_v1 import IDENTITY


class SchemaCHEstimator(CHXEstimator):
    ARM_NAME = "C-H schema"

    def __init__(self):
        os.environ["BWE_ENVELOPE"] = "6"; os.environ["BWE_COLLECTOR"] = "v6"; os.environ["BWE_MIN_BPS_FLOOR"] = "1"
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
        with self.torch.inference_mode(): model_raw = float(self.model.forward(self.torch.tensor(obs_in, dtype=self.torch.float32).reshape(1, 150)))
        model_bps = max(model_raw, 0.0); floor_hit = self.floor_on and model_bps < self.FLOOR_BPS
        if floor_hit: model_bps = self.FLOOR_BPS
        bps = self.envelope.apply(model_bps, raw_in, self.collector.clock())
        if self.trace:
            self.trace.write(json.dumps({"r": self.r, "t_ms": self.collector.clock(), "arm": 0, "arm_name": self.ARM_NAME, "preds_mbps": [model_bps / 1e6], "obs": raw, "obs_est": obs,
                                         "schema": self.schema, "map": self.map_tag, "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": bps,
                                         "model_bps": model_bps, "model_raw_bps": model_raw, "floor_hit": floor_hit, "envelope": self.envelope.last, "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        self.r += 1; return int(bps)
