# -*- coding: utf-8 -*-
"""Deployment core of the LLM switcher, same interface as switcher.SwitchCore.
At a block boundary it hands the previous block's feature text to the worker process instead of waiting; the current arm stays in use until the answer arrives and takes effect from the next step. If the worker is not ready or has exited, the fixed arm is used and the per-step path never blocks.
"""
import json, os, queue, subprocess, sys, threading, time
import numpy as np

K, JFIX = 50, 1
NAMES = ["f0_mean", "f0_cv", "f0_trend", "f3_mean", "f3_p95", "f3_slope", "f6_mean", "f9_mean", "f10_mean"]
for _t in ("Pioneer", "Schaferct_public", "Schaferct_retrained", "MLP_seed0"):
    NAMES += [f"{_t}_ratio", f"{_t}_pseudo", f"{_t}_slope"]
NAMES.append("disagree")


def fmt(v):
    """Format with three significant digits, identical to fmt in switch_llm_stage_build_table_v1.py."""
    if not np.isfinite(v) or v == 0:
        return "0"
    return f"{v:.3g}"


def serialize(row):
    return " ".join(f"{n}={fmt(v)}" for n, v in zip(NAMES, row))


class AsyncLLMSwitchCore:
    def __init__(self, block_features, worker_script, model_dir, threads=4):
        self.block_features = block_features; self.r = 0; self.arm = JFIX; self.buf = []
        self.next_id = 0; self.sent = {}; self.results = queue.Queue(); self.ready = False; self.alive = True
        self.last = {"applied_id": None, "decision_ms": None, "delay_steps": None, "pending": 0, "ready": False}
        self.proc = subprocess.Popen([sys.executable, "-u", worker_script, model_dir, str(threads)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.proc.stdout:
            try: self.results.put(json.loads(line))
            except Exception: pass
        self.alive = False

    def _poll(self):
        newest = None
        while True:
            try: m = self.results.get_nowait()
            except queue.Empty: break
            if m.get("ready"): self.ready = True; self.last["ready"] = True; self.last["load_s"] = m.get("load_s"); continue
            if newest is None or m["id"] > newest["id"]: newest = m
        if newest is not None:
            sent_r = self.sent.pop(newest["id"], None); self.arm = int(newest["arm"])
            self.last.update(applied_id=newest["id"], decision_ms=newest["ms"], delay_steps=None if sent_r is None else self.r - sent_r)
            for k in [k for k in self.sent if k < newest["id"]]: self.sent.pop(k)
        self.last["pending"] = len(self.sent)

    def step(self, f0_mbps, f3, f6, f9, f10, preds):
        self._poll()
        if self.r > 0 and self.r % K == 0:
            B = np.array(self.buf, dtype=np.float64); c = [np.ascontiguousarray(B[:, k]) for k in range(5)]
            x = self.block_features(c[0], c[1], c[2], c[3], c[4], np.ascontiguousarray(B[:, 5:9].T)); self.last_x = x; self.buf = []
            if self.ready and self.alive and self.proc.poll() is None:
                try:
                    self.proc.stdin.write(json.dumps({"id": self.next_id, "text": serialize(x)}) + "\n"); self.proc.stdin.flush()
                    self.sent[self.next_id] = self.r; self.next_id += 1
                except Exception:
                    self.alive = False
        self.buf.append([f0_mbps, f3, f6, f9, f10] + [float(v) for v in preds]); self.r += 1
        return float(preds[self.arm]), self.arm

    def close(self):
        try: self.proc.stdin.close(); self.proc.terminate()
        except Exception: pass
