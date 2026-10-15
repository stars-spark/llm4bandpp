# -*- coding: utf-8 -*-
"""Arm arm_ch_schema_tel: the telemetry-only configuration. Same as arm_ch_schema except that the probing envelope is v4, with no shadow GCC: a client that sees only aggregate
telemetry (getStats) has no per-packet reports, so the adapted observation drives both the estimate and the envelope.
Copy of fixed_schema_ch_v1.py that sets BWE_ENVELOPE=4 instead of 6. Loaded by estimator entry point v18 (run script v27) for hd720-designer-tel-v1, hd720-designer-tel-v2 and
hd720-designer-tel-fid-v1; the last two are the telemetry-only rows of Table IV.
"""
import json, os, time
from estimator.online_llm_arms_v8 import CHXEstimator
from estimator.fixed_schema_nl_v1 import PERM, adapt
from estimator.fixed_schema_x_v1 import IDENTITY


class SchemaCHTelEstimator(CHXEstimator):
    ARM_NAME = "C-H schema, telemetry-only envelope"

    def __init__(self):
        os.environ["BWE_ENVELOPE"] = "4"; os.environ["BWE_COLLECTOR"] = "v6"; os.environ["BWE_MIN_BPS_FLOOR"] = "1"
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
