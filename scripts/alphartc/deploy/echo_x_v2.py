# -*- coding: utf-8 -*-
"""Arm echo_x with probing envelope v6, loaded by estimator entry point v10 and later when BWE_ESTIMATOR=echo_x. With BWE_ENVELOPE=6 the parent is built with envelope 0 and its envelope
replaced by safety_envelope_v6.SafetyEnvelope; report_states also feeds packet reports to the envelope's shadow GCC. Other BWE_ENVELOPE values match echo_x_v1 step for step.
Subclass of echo_x_v1.EchoXEstimator. With collector v6 and envelope v6 it is the echo arm of hd720-echo-attr-ch-v1 (hd720_attr_loss_v1.py, run script v20), the batch
whose reading against GCC is the second 720p row of Table V.
"""
import os
from estimator.echo_x_v1 import EchoXEstimator


class EchoXEstimatorV2(EchoXEstimator):
    def __init__(self):
        env = (os.environ.get("BWE_ENVELOPE", "") or "0").strip()
        if env == "6":
            os.environ["BWE_ENVELOPE"] = "0"
            try:
                super().__init__()
            finally:
                os.environ["BWE_ENVELOPE"] = env
            from estimator.safety_envelope_v6 import SafetyEnvelope
            self.envelope = SafetyEnvelope(); self.envelope_name = "6"
        else:
            super().__init__()

    def report_states(self, stats):
        super().report_states(stats)
        rs = getattr(self.envelope, "report_states", None)
        if rs is not None: rs(stats)
