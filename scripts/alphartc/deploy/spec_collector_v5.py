#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collector v5 (switch-deploy-collector-v5): the v4 features with loss rate f10 and lost count f11 computed per SSRC. Main video (payload type 125) and retransmission (122)
have separate sequence spaces; expected packets are computed per SSRC with 16-bit unwrap and summed, f10 = 1 - received / expected and f11 = expected - received.
Subclass of spec_collector_v4.SlidingCollectorV4 (BWE_COLLECTOR=v5 in switcher.py, switcher_x_v1.py and the online arms). closure_v1.py feeds it packets rebuilt from
a browser capture to obtain the correct interface.
"""
try:
    from estimator.spec_collector_v4 import SlidingCollectorV4
except ImportError:
    from spec_collector_v4 import SlidingCollectorV4


def _expected(seqs):
    lo, hi = min(seqs), max(seqs)
    if hi - lo > 32768:
        seqs = [s + 65536 if s < 32768 else s for s in seqs]; lo, hi = min(seqs), max(seqs)
    return hi - lo + 1


class SlidingCollectorV5(SlidingCollectorV4):
    def _packet(self, stats):
        p = super()._packet(stats); p["ssrc"] = int(stats.get("ssrc", 0) or 0); return p

    def _feat4(self, lo, hi, dur_ms):
        import bisect
        feats, media = super()._feat4(lo, hi, dur_ms)
        pk = self.pk[bisect.bisect_left(self.ts, lo):bisect.bisect_left(self.ts, hi)]
        if pk:
            groups = {}
            for q in pk: groups.setdefault(q["ssrc"], []).append(q["seq"])
            exp = sum(_expected(v) for v in groups.values()); n = len(pk)
            feats = list(feats); feats[10] = 1 - n / exp if exp > 0 else 0.0; feats[11] = exp - n if exp > 0 else 0
        return feats, media
