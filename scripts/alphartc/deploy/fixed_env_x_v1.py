# -*- coding: utf-8 -*-
"""Arm arm_default_env5: the challenge baseline (schaferct_public.onnx) alone with probing envelope v5, whose constants come from BWE_ENVELOPE_PARAMS.
Built as FixedXEstimator with envelope v4 (collector from BWE_COLLECTOR), then the envelope is replaced by safety_envelope_v5; the trace also records envelope_params.
"""
import json, os
from estimator.fixed_x_v1 import FixedXEstimator


class FixedEnvXEstimator(FixedXEstimator):
    def __init__(self):
        os.environ["BWE_ENVELOPE"] = "4"
        super().__init__("arm_schaferct_public_x")
        from estimator.safety_envelope_v5 import SafetyEnvelope
        self.envelope = SafetyEnvelope(); self.envelope_name = "5"
        if getattr(self, "trace", None) is not None:
            self.trace.write(json.dumps({"envelope_params": self.envelope.params}) + "\n"); self.trace.flush()
