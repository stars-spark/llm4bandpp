#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collector v4 (switch-deploy-collector-v4): inter-arrival f8 and jitter f9 include the gap from the last packet before the window to the window's first packet; f8 is the mean
and f9 the population std of the arrival gaps of [last packet before window, packets in window], so a window with one packet has a nonzero gap, as in the offline data.
Other features as spec_collector.py.
Subclass of spec_collector.SlidingCollector, written after closedloop-collapse-attribution-v1 showed that f8 = 0 inflates the experts' predictions; no arm selects it directly, collector v5 builds on it.
"""
import bisect
try:
    from estimator.spec_collector import SlidingCollector, MEDIA_PROPORTION
except ImportError:
    from spec_collector import SlidingCollector, MEDIA_PROPORTION


class SlidingCollectorV4(SlidingCollector):
    KEEP_MS = 3800.0

    def _feat4(self, lo, hi, dur_ms):
        i0, i1 = bisect.bisect_left(self.ts, lo), bisect.bisect_left(self.ts, hi)
        feats, media = self._features({"start": 0.0, "end": dur_ms, "pk": self.pk[i0:i1]})
        if i1 > i0 and i0 > 0:
            ts = [self.ts[i0 - 1]] + self.ts[i0:i1]
            inter = [ts[k] - ts[k - 1] for k in range(1, len(ts))]
            m = sum(inter) / len(inter)
            feats = list(feats); feats[8] = m; feats[9] = (sum((x - m) ** 2 for x in inter) / len(inter)) ** 0.5
        return feats, media

    def observation(self, now_ms=None):
        T = self.clock() if now_ms is None else float(now_ms)
        S = [self._feat4(T - 60.0 * (i + 1), T - 60.0 * i, 60.0) for i in range(5)]
        L = [self._feat4(T - 600.0 * (i + 1), T - 600.0 * i, 600.0) for i in range(5)]
        obs = []
        for f in range(15):
            obs.extend(x[0][f] for x in S); obs.extend(x[0][f] for x in L)
        self.last_truthful_media = list(obs[-30:]); obs[-30:] = MEDIA_PROPORTION
        return obs
