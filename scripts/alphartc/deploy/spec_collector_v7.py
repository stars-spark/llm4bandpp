#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collector v7: as v6, but the audio constant is added only to windows whose raw packet count is above 0. Empty windows stay all zero, as at the start of calls in the training data;
windows with packets match v6 bit for bit. raw_observation keeps the observation without audio for the probing envelope.
Subclass of spec_collector_v5.SlidingCollectorV5 with the constants of v6 (BWE_COLLECTOR=v7 in online_llm_arms_v7 and _v8), written after C-H overloaded the 100 kbit/s link
at call start in lowbw-ch-vs-conf-v1. Used only in ch-startup-guard-smoke-explore-v1 (run script v19); the deployed system keeps collector v6.
"""
try:
    from estimator.spec_collector_v5 import SlidingCollectorV5
    from estimator.spec_collector_v6 import AUDIO_BPS, AUDIO_PPS
except ImportError:
    from spec_collector_v5 import SlidingCollectorV5
    from spec_collector_v6 import AUDIO_BPS, AUDIO_PPS


def add_audio_present(obs):
    o = list(obs)
    for s in range(10):
        if obs[10 + s] <= 0: continue
        w = 0.06 if s < 5 else 0.6
        o[s] += AUDIO_BPS; o[10 + s] += AUDIO_PPS * w; o[20 + s] += AUDIO_BPS / 8.0 * w
    return o


class SlidingCollectorV7(SlidingCollectorV5):
    def observation(self, now_ms=None):
        raw = super().observation(now_ms); self.raw_observation = list(raw); return add_audio_present(raw)
