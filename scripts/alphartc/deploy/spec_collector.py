# -*- coding: utf-8 -*-
"""Collector of the 150-value observation in the units of the offline training data. SpecCollector is collector v1 (switch-deploy-collector-v1); SlidingCollector, which ends
each window at the request time, served as collectors v2 and v3. Slot 0 is the newest monitor interval (b0-slot-order-audit-v1); f3 to f7 follow the official formulas;
delay origin d = recv - send - first-packet (recv - send) + 200 with f5 the running minimum; 64 s send-timestamp unwrap; f0 in bit/s; f11 is the lost-packet count;
f12 to f14 keep training-set means (true values in last_truthful_media). Independent of estimator.py.
Base of the collector family: spec_collector_v4.py to _v7.py subclass it in turn. Used through switcher.py (BWE_COLLECTOR=v3) and online_llm_arms_v1.py, and by closure_v1.py.
"""
from __future__ import annotations

import collections
import time

BASE_DELAY = 200.0
WRAP_MS = 64000.0
SHORT_MS, LONG_MS, NSLOT = 60.0, 600.0, 5
AUDIO_PT = {111, 0, 8, 9, 103, 104}
MEDIA_PROPORTION = [
    0.5624007667367734, 0.525428472491675, 0.5398770595127375, 0.5335882890791457, 0.5281944796582948,
    0.5539928326103514, 0.5492280111798816, 0.5472668176812704, 0.5433039898216068, 0.5410861365126697,
    0.4329668165684116, 0.41940919988014613, 0.41652523714865447, 0.41276113321926694, 0.4230384000352399,
    0.4406922450131523, 0.43879027296869594, 0.4365506371537228, 0.43526221668141996, 0.432693335013149,
    0.00461964258628507, 0.0043729238066349254, 0.004236135735652494, 0.004341627231086488, 0.004255546605263082,
    0.005299858381903476, 0.005274764207886763, 0.005284779819482612, 0.005265374225193354, 0.005229165976840806]


def _empty(start, dur):
    return {"start": start, "end": start + dur, "pk": []}


class _Track:
    """Monitor-interval sequence for one time scale; queue[0] is the newest finished interval."""

    def __init__(self, dur):
        self.dur = dur
        self.queue = collections.deque([_empty(0.0, dur) for _ in range(NSLOT)], maxlen=NSLOT)
        self.cur = None

    def advance(self, now):
        if self.cur is None:
            return
        while now >= self.cur["end"]:
            self.queue.appendleft(self.cur)
            self.cur = _empty(self.cur["end"], self.dur)

    def add(self, p):
        if self.cur is None:
            self.cur = _empty(p["t"], self.dur)
        self.advance(p["t"])
        self.cur["pk"].append(p)


class SpecCollector:
    def __init__(self, clock=None):
        self.clock = clock or (lambda: time.time() * 1000.0)
        self.short, self.long = _Track(SHORT_MS), _Track(LONG_MS)
        self.last_send = None
        self.rmin = float("inf")
        self.raw_first = None
        self.last_truthful_media = None
        self.n_packets = 0
        self.n_wraps = 0

    def _unwrap(self, s):
        """Return the value s + k*64000 closest to the last unwrapped send time; late out-of-order packets do not advance last_send."""
        s = float(s)
        if self.last_send is None:
            self.last_send = s
            return s
        u = s + round((self.last_send - s) / WRAP_MS) * WRAP_MS
        if u > self.last_send:
            if int(u // WRAP_MS) > int(self.last_send // WRAP_MS):
                self.n_wraps += 1
            self.last_send = u
        return u

    def report_states(self, stats):
        p = self._packet(stats)
        self.short.add(p); self.long.add(p)
        self.n_packets += 1

    def _packet(self, stats):
        """Turn one stats record into a packet record and update the unwrap state, first-packet origin and running minimum delay."""
        send = self._unwrap(stats["send_time_ms"])
        arr = float(stats["arrival_time_ms"])
        raw = arr - send
        if self.raw_first is None:
            self.raw_first = raw
        self.rmin = min(self.rmin, raw)
        pt = int(stats["payload_type"]) if stats.get("payload_type") is not None else -1
        size = stats["header_length"] + stats["payload_size"] + stats["padding_length"]
        kind = ("probe" if stats["payload_size"] == 0 and stats["padding_length"] > 0
                else "audio" if pt in AUDIO_PT else "video")
        return {"t": arr, "raw": raw, "seq": int(stats["sequence_number"]), "size": size, "kind": kind}

    def close_until(self, now_ms):
        self.short.advance(now_ms); self.long.advance(now_ms)

    def _features(self, mi):
        pk = mi["pk"]; n = len(pk)
        if n == 0:
            return [0.0] * 15, None
        d = [q["raw"] - self.raw_first + BASE_DELAY for q in pk]
        A = sum(d) / n
        m = min(d)
        M = self.rmin - self.raw_first + BASE_DELAY
        dur_s = (mi["end"] - mi["start"]) / 1000.0
        nbytes = sum(q["size"] for q in pk)
        ts = sorted(q["t"] for q in pk)
        inter = [ts[i] - ts[i - 1] for i in range(1, n)]
        if inter:
            mi_ = sum(inter) / len(inter)
            jit = (sum((x - mi_) ** 2 for x in inter) / len(inter)) ** 0.5
        else:
            mi_, jit = 0.0, 0.0
        seqs = [q["seq"] for q in pk]
        exp = max(seqs) - min(seqs) + 1
        loss = 1 - n / exp if exp > 0 else 0.0
        media = [sum(q["kind"] == k for q in pk) / n for k in ("video", "audio", "probe")]
        lost = exp - n if exp > 0 else 0
        return [nbytes * 8 / dur_s, n, nbytes, A - M, A - BASE_DELAY, M, A / m, A - m,
                mi_, jit, loss, lost] + media, media

    def observation(self, now_ms=None):
        """Return the 150-dim observation laid out as feature x 10 + slot; slots 0 to 4 are short intervals and 5 to 9 long, newest first."""
        self.close_until(self.clock() if now_ms is None else now_ms)
        S = [self._features(mi) for mi in self.short.queue]
        L = [self._features(mi) for mi in self.long.queue]
        obs = []
        for f in range(15):
            obs.extend(x[0][f] for x in S)
            obs.extend(x[0][f] for x in L)
        truthful = obs[-30:]
        self.last_truthful_media = list(truthful)
        obs[-30:] = MEDIA_PROPORTION
        return obs


class SlidingCollector(SpecCollector):
    """Collector with sliding windows ending at request time T: short slot i is [T - 60(i+1), T - 60i) ms and long slot i is [T - 600(i+1), T - 600i) ms."""
    KEEP_MS = 3100.0

    def __init__(self, clock=None):
        super().__init__(clock=clock)
        self.pk, self.ts = [], []

    def report_states(self, stats):
        p = self._packet(stats)
        if self.ts and p["t"] < self.ts[-1]:
            import bisect
            i = bisect.bisect_right(self.ts, p["t"]); self.ts.insert(i, p["t"]); self.pk.insert(i, p)
        else:
            self.ts.append(p["t"]); self.pk.append(p)
        cut = self.ts[-1] - self.KEEP_MS
        if self.ts[0] < cut:
            import bisect
            j = bisect.bisect_left(self.ts, cut); del self.ts[:j]; del self.pk[:j]
        self.n_packets += 1

    def _window(self, lo, hi):
        import bisect
        return self.pk[bisect.bisect_left(self.ts, lo):bisect.bisect_left(self.ts, hi)]

    def _feat(self, pk, dur_ms):
        mi = {"start": 0.0, "end": dur_ms, "pk": pk}
        return self._features(mi)

    def observation(self, now_ms=None):
        T = self.clock() if now_ms is None else float(now_ms)
        S = [self._feat(self._window(T - 60.0 * (i + 1), T - 60.0 * i), 60.0) for i in range(5)]
        L = [self._feat(self._window(T - 600.0 * (i + 1), T - 600.0 * i), 600.0) for i in range(5)]
        obs = []
        for f in range(15):
            obs.extend(x[0][f] for x in S)
            obs.extend(x[0][f] for x in L)
        self.last_truthful_media = list(obs[-30:])
        obs[-30:] = MEDIA_PROPORTION
        return obs
