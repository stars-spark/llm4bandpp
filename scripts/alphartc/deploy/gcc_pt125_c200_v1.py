# -*- coding: utf-8 -*-
"""Estimator gcc_pt125_c200: the corrected Python GCC called every 200 ms, the GCC reference arm of the closed-loop batches.
Between computations it returns the previous estimate while packets keep accumulating in packets_list; once 200 ms have passed since the last computation (by last arrival time) it runs the original formula. Everything else is inherited from GCCEstimatorPT125.
"""
from estimator.gcc_pt125_v1 import GCCEstimatorPT125


class GCCEstimatorPT125C200(GCCEstimatorPT125):
    CADENCE_MS = 200

    def __init__(self):
        super().__init__(); self.last_call_ms = None

    def get_estimated_bandwidth(self) -> int:
        now = self.now_ms
        if self.last_call_ms is not None and now - self.last_call_ms < self.CADENCE_MS:
            return self.last_bandwidth_estimation
        self.last_call_ms = now
        return super().get_estimated_bandwidth()
