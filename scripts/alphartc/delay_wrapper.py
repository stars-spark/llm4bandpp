# -*- coding: utf-8 -*-
"""Decision-lag injection: wraps any bandwidth estimator so that at time t it returns the value computed at t - d.
The output is delayed rather than the input, because inference latency means the decision in force was computed from older data. The clock is arrival_time_ms from report_states (wall clock as fallback); d is BWE_DELAY_MS, default 0.
"""
import collections
import json
import os
import time


class DelayedEstimator(object):
    def __init__(self, inner, delay_ms=None):
        self.inner = inner
        if delay_ms is None:
            delay_ms = float(os.environ.get("BWE_DELAY_MS", "0"))
        self.delay_ms = float(delay_ms)
        self._buf = collections.deque()
        self._clock_ms = None
        self._t0_wall = time.time() * 1000.0
        self._last_out = None
        self._n_calls = 0
        self._n_stale = 0
        self._trace_path = os.environ.get("BWE_DELAY_TRACE", "").strip()
        self._trace = None
        if self._trace_path:
            parent = os.path.dirname(self._trace_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._trace = open(self._trace_path, "a", buffering=1)

    def _now_ms(self):
        if self._clock_ms is not None:
            return self._clock_ms
        return time.time() * 1000.0 - self._t0_wall

    def report_states(self, stats):
        t = stats.get("arrival_time_ms") if isinstance(stats, dict) else None
        if t is not None:
            self._clock_ms = float(t)
        return self.inner.report_states(stats)

    def get_estimated_bandwidth(self):
        compute_start = time.perf_counter()
        bw_now = self.inner.get_estimated_bandwidth()
        compute_ms = (time.perf_counter() - compute_start) * 1000.0
        self._n_calls += 1
        now = self._now_ms()
        generated_wall_ms = time.time() * 1000.0
        current = {
            "seq": self._n_calls,
            "state_time_ms": now,
            "generated_wall_ms": generated_wall_ms,
            "bandwidth_bps": int(bw_now),
            "compute_ms": compute_ms,
        }
        self._buf.append(current)

        if self.delay_ms <= 0:
            selected = current
            startup_fallback = False
            out = current["bandwidth_bps"]
            self._last_out = out
            self._write_trace(now, current, selected, startup_fallback)
            return out

        cutoff = now - self.delay_ms

        selected = None
        while len(self._buf) >= 2 and self._buf[1]["state_time_ms"] <= cutoff:
            self._buf.popleft()
        if self._buf and self._buf[0]["state_time_ms"] <= cutoff:
            selected = self._buf[0]

        startup_fallback = selected is None
        if startup_fallback:
            self._n_stale += 1
            out = self._last_out if self._last_out is not None else current["bandwidth_bps"]
            selected = current
        else:
            out = selected["bandwidth_bps"]
        self._last_out = out
        self._write_trace(now, current, selected, startup_fallback)
        return out

    def _write_trace(self, now, current, selected, startup_fallback):
        if self._trace is None:
            return
        applied_wall_ms = time.time() * 1000.0
        rec = {
            "event": "bwe_decision",
            "seq": current["seq"],
            "requested_delay_ms": self.delay_ms,
            "media_time_ms": now,
            "current_bandwidth_bps": current["bandwidth_bps"],
            "applied_bandwidth_bps": int(self._last_out),
            "selected_seq": selected["seq"],
            "selected_state_time_ms": selected["state_time_ms"],
            "selected_generated_wall_ms": selected["generated_wall_ms"],
            "applied_wall_ms": applied_wall_ms,
            "state_age_ms": max(0.0, now - selected["state_time_ms"]),
            "wall_age_ms": max(0.0, applied_wall_ms - selected["generated_wall_ms"]),
            "current_compute_ms": current["compute_ms"],
            "selected_compute_ms": selected["compute_ms"],
            "startup_fallback": bool(startup_fallback),
            "buffer_size": len(self._buf),
        }
        self._trace.write(json.dumps(rec, sort_keys=True) + "\n")

    def close(self):
        if self._trace is not None:
            self._trace.close()
            self._trace = None

    def __del__(self):
        self.close()

    def __getattr__(self, name):
        return getattr(self.inner, name)
