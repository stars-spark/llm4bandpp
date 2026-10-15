#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collector v6: the v5 features plus the audio stream that the testbed does not report to the estimator. Audio runs at a constant 50.8 packets/s (about 41 kbps at RTP level,
testbed-sender-floor-audio-audit-v1) and is part of the receiving rate, packet and byte counts in the training data, so the measured constant is added to f0, f1 and f2 in every
window. raw_observation keeps the observation without audio for the probing envelope. A real client reports audio and needs no such step.
Subclass of spec_collector_v5.SlidingCollectorV5 (BWE_COLLECTOR=v6), written for llm4bandpp-online-unlock-v1; the collector of the deployed system in every closed-loop batch
of the paper. The weight checks seed_weight_check_v1.py to _v7.py use its add_audio.
"""
try:
    from estimator.spec_collector_v5 import SlidingCollectorV5
except ImportError:
    from spec_collector_v5 import SlidingCollectorV5
AUDIO_BPS, AUDIO_PPS = 41000.0, 50.8


def add_audio(obs):
    o = list(obs)
    for s in range(10):
        w = 0.06 if s < 5 else 0.6
        o[s] += AUDIO_BPS; o[10 + s] += AUDIO_PPS * w; o[20 + s] += AUDIO_BPS / 8.0 * w
    return o


class SlidingCollectorV6(SlidingCollectorV5):
    def observation(self, now_ms=None):
        raw = super().observation(now_ms); self.raw_observation = list(raw); return add_audio(raw)
