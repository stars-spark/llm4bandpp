# -*- coding: utf-8 -*-
"""Arms arm_schaferct_retrained_d and arm_mlp_d: Schaferct-R or the supervised MLP with the settings of the deployed system. Inherits online_llm_arms_v8._Base (collector, startup guard,
5 kbps floor and probing envelope as for arm_ch_x) and swaps the model for one arm of switcher.ArmBank, scaled from Mbit/s to bit/s; the bank runs all four arms every step
to keep the ONNX LSTM states as in fixed_x_v1.
New file, not a copy of fixed_x_v1.py; loaded by estimator entry point v16 and later (run script v24) for hd720-learned-baselines-v1, hd720-learned-alone-v1, hd720-hb-learned-env-v1
and hd720-hb-learned-alone-v1, the learned-estimator rows of Table V.
"""
import os
from estimator.online_llm_arms_v8 import _Base

ARM_INDEX = {"arm_pioneer_d": 0, "arm_schaferct_public_d": 1, "arm_schaferct_retrained_d": 2, "arm_mlp_d": 3}


class _BankArm:
    def __init__(self, idx):
        from estimator.switcher import ArmBank
        self.bank = ArmBank(os.environ.get("BWE_SWITCH_MODEL_DIR", "/app/model/switch_v1")); self.idx = idx

    def eval(self): return self

    def forward(self, x):
        return float(self.bank.step(x.reshape(-1).tolist())[self.idx]) * 1e6


class FixedDEstimator(_Base):
    def __init__(self, name):
        self._idx = ARM_INDEX[name]; self.ARM_NAME = name
        super().__init__()

    def _build(self, torch, dev):
        return _BankArm(self._idx)
