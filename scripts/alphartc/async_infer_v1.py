# -*- coding: utf-8 -*-
"""Asynchronous inference wrapper for receiver-side estimators on the AlphaRTC testbed.
Packet reports enter the collector on the main thread at once; inference runs on a background thread on a snapshot of the observation, and a bandwidth request waits at most the deadline (default 40 ms) before returning the last finished estimate.
Estimators without a collector (GCC, fixed rate) are called synchronously; BWE_ASYNC_TRACE writes one line per request.
"""
import json
import sys
import threading
import time


class AsyncInferEstimator(object):
    def __init__(self, inner, deadline_ms=40.0, trace_path=""):
        self.inner = inner
        self.deadline_s = float(deadline_ms) / 1000.0
        coll = getattr(inner, "collector", None)
        self.enabled = coll is not None and callable(getattr(coll, "report_states", None)) and callable(getattr(coll, "observation", None))
        self._mu = threading.Condition(threading.Lock())
        self._busy = False; self._pending = False; self._exc = None
        self._n_done = 0; self._n_started = 0; self._n_req = 0
        self._latest = None; self._latest_meta = None
        self._trace = open(trace_path, "a", buffering=1) if trace_path else None
        torch = sys.modules.get("torch")
        self._torch_threads = torch.get_num_threads() if torch is not None else None
        if self.enabled:
            self._wrap_collector(coll)
            self._go = threading.Event()
            self._thread = threading.Thread(target=self._loop, name="bwe-infer", daemon=True)
            self._thread.start()

    def _wrap_collector(self, coll):
        lock = threading.RLock(); rs, ob = coll.report_states, coll.observation

        def report_states(stats):
            with lock:
                return rs(stats)

        def observation(*a, **k):
            with lock:
                return ob(*a, **k)
        coll.report_states = report_states; coll.observation = observation

    def report_states(self, stats):
        return self.inner.report_states(stats)

    def _loop(self):
        if self._torch_threads is not None:
            sys.modules["torch"].set_num_threads(self._torch_threads)
        while True:
            self._go.wait(); self._go.clear()
            while True:
                t_wall = time.time() * 1000.0; t0 = time.perf_counter()
                try:
                    out = self.inner.get_estimated_bandwidth(); exc = None
                except BaseException as e:
                    out, exc = None, e
                comp = (time.perf_counter() - t0) * 1000.0
                with self._mu:
                    self._n_done += 1
                    if exc is not None:
                        self._exc = exc; self._busy = False; self._pending = False; self._mu.notify_all(); return
                    self._latest = out; self._latest_meta = (t_wall, comp, self._n_done)
                    again = self._pending; self._pending = False
                    if again:
                        self._n_started += 1
                    else:
                        self._busy = False
                    self._mu.notify_all()
                if not again:
                    break

    def get_estimated_bandwidth(self):
        if not self.enabled:
            return self.inner.get_estimated_bandwidth()
        t_req = time.time() * 1000.0; p0 = time.perf_counter()
        with self._mu:
            self._n_req += 1
            if self._exc is not None:
                raise self._exc
            if self._busy:
                self._pending = True; mode = "held_busy"
            else:
                self._busy = True; self._n_started += 1; target = self._n_done + 1; first = self._latest is None
                last_c = self._latest_meta[1] if self._latest_meta else None
                wait = None if first else (self.deadline_s if (last_c is None or last_c <= self.deadline_s * 1000.0) else 0.0)
                self._go.set()
                ok = self._mu.wait_for(lambda: self._n_done >= target or self._exc is not None, timeout=wait)
                if self._exc is not None:
                    raise self._exc
                mode = "first" if first else ("fresh" if ok else ("held_wait" if wait else "held_nowait"))
            out = self._latest; meta = self._latest_meta; n_done = self._n_done
        if self._trace is not None:
            self._trace.write(json.dumps({"i": self._n_req, "t_req_ms": t_req, "mode": mode, "reply_ms": (time.perf_counter() - p0) * 1000.0, "n_done": n_done,
                                          "out_start_ms": meta[0] if meta else None, "out_compute_ms": meta[1] if meta else None, "out_seq": meta[2] if meta else None,
                                          "bps": out}) + "\n")
        return out

    def close(self):
        if self._trace is not None:
            self._trace.close(); self._trace = None

    def __getattr__(self, name):
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)
