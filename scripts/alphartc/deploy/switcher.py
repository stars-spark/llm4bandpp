# -*- coding: utf-8 -*-
"""Switching estimator switch_nn (not part of LLM4band++; Sections VI and S9).
The four arms run on every request; every K = 50 requests (60 ms each, so 3 s) the switching network picks an arm from the previous block's 22 observable features, with the challenge baseline for block 0. Block features follow build_blocks in switch_causal_control_v1.py line for line.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

K = 50
W = 3.0
ARMS = ["Pioneer", "Schaferct(public)", "Schaferct(retrained)", "MLP_seed0"]
JFIX = 1


def slope(x):
    n = len(x)
    if n < 2:
        return 0.0
    t = np.arange(n) - (n - 1) / 2
    return float(np.dot(t, x - x.mean()) / np.dot(t, t))


def block_features(f0, f3, f6, f9, f10, p):
    """Build block features from f0 (Mbps) and p, the 4 x n arm predictions in Mbps, line for line as build_blocks."""
    m0 = f0.mean(); h = len(f0) // 2
    r = [m0, f0.std() / m0 if m0 > 0 else 0.0,
         (f0[h:].mean() / f0[:h].mean()) if h > 0 and f0[:h].mean() > 0 else 1.0,
         f3.mean(), np.percentile(f3, 95), slope(f3),
         f6.mean(), f9.mean(), f10.mean()]
    with np.errstate(divide="ignore", invalid="ignore"):
        rp = (p - f0) / f0
    ps_all = np.where(f0 > 1e-6, np.maximum(-rp, 0) + W * np.maximum(rp, 0), np.nan)
    for j in range(4):
        ps = ps_all[j]
        r += [p[j].mean() / m0 if m0 > 0 else 0.0,
              np.nanmean(ps) if np.isfinite(ps).any() else 0.0,
              slope(p[j])]
    mu = p.mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        dis = np.where(mu > 0, p.std(axis=0) / mu, 0.0)
    r.append(float(dis.mean()))
    return np.nan_to_num(np.array(r, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)


class SwitchNet:
    def __init__(self, path):
        z = np.load(path, allow_pickle=True)
        self.mu, self.sd = z["mu"], z["sd"]
        self.W = [(z["W1"], z["b1"]), (z["W2"], z["b2"]), (z["W3"], z["b3"])]

    def choose(self, x):
        h = (x - self.mu) / self.sd
        for i, (w, b) in enumerate(self.W):
            h = h @ w.T + b
            if i < 2:
                h = np.maximum(h, 0.0)
        return int(np.argmax(h))


class SwitchCore:
    """Switching logic decoupled from arm inference: each step takes the five slot-0 features and four arm predictions and returns the adopted prediction and arm."""

    def __init__(self, net):
        self.net = net
        self.r = 0
        self.arm = JFIX
        self.buf = []

    def step(self, f0_mbps, f3, f6, f9, f10, preds):
        if self.r > 0 and self.r % K == 0:
            B = np.array(self.buf, dtype=np.float64)
            c = [np.ascontiguousarray(B[:, k]) for k in range(5)]
            x = block_features(c[0], c[1], c[2], c[3], c[4], np.ascontiguousarray(B[:, 5:9].T))
            self.last_x = x
            self.arm = self.net.choose(x)
            self.buf = []
        self.buf.append([f0_mbps, f3, f6, f9, f10] + [float(v) for v in preds])
        self.r += 1
        return float(preds[self.arm]), self.arm


class ArmBank:
    """Four-arm inference: three ONNX models keep their LSTM state and the MLP loads from its checkpoint, encoder0 included."""

    def __init__(self, model_dir):
        import onnxruntime as ort
        import torch
        from torch import nn
        d = Path(model_dir)
        self.sess, self.state = [], []
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1; so.inter_op_num_threads = 1
        torch.set_num_threads(1)
        for f in ("pioneer.onnx", "schaferct_public.onnx", "schaferct_retrained.onnx"):
            s = ort.InferenceSession(str(d / f), so, providers=["CPUExecutionProvider"])
            shp = tuple(s.get_inputs()[1].shape)
            self.sess.append(s); self.state.append([np.zeros(shp, np.float32), np.zeros(shp, np.float32)])

        class _MLP(nn.Module):
            def __init__(self):
                super().__init__()
                self.register_buffer("encoder0", torch.zeros(150))
                self.network = nn.Sequential(nn.Linear(150, 512), nn.ReLU(), nn.Linear(512, 512), nn.ReLU(),
                                             nn.Linear(512, 256), nn.ReLU(), nn.Linear(256, 1), nn.Softplus())

            def forward(self, x):
                return self.network(x * self.encoder0.to(dtype=x.dtype))

        pay = torch.load(d / "mlp_seed0.pt", map_location="cpu", weights_only=False)
        self.mlp = _MLP()
        self.mlp.load_state_dict(pay["state_dict"] if "state_dict" in pay else pay, strict=True)
        self.mlp.eval()
        self.torch = torch

    def step(self, obs):
        o = np.asarray(obs, dtype=np.float32).reshape(1, 1, -1)
        out = np.empty(4, dtype=np.float32)
        for j, s in enumerate(self.sess):
            h, c = self.state[j]
            y, h, c = s.run(None, {"obs": o, "hidden_states": h, "cell_states": c})
            self.state[j] = [h, c]
            out[j] = np.float32(y[0, 0, 0]) / np.float32(1e6)
        with self.torch.inference_mode():
            out[3] = self.mlp(self.torch.from_numpy(o.reshape(1, -1))).squeeze(-1).numpy()[0]
        return out


class SwitchEstimator:
    """AlphaRTC entry point for BWE_ESTIMATOR=switch_nn, or a single arm arm_* when fixed_arm is set; model directory from BWE_SWITCH_MODEL_DIR."""

    def __init__(self, fixed_arm=None):
        self.fixed = fixed_arm
        from estimator.spec_collector import SlidingCollector
        d = os.environ.get("BWE_SWITCH_MODEL_DIR", "/app/model/switch_v1")
        self.collector_name = (os.environ.get("BWE_COLLECTOR", "") or "v3").strip().lower()
        if self.collector_name == "v5":
            from estimator.spec_collector_v5 import SlidingCollectorV5
            self.collector = SlidingCollectorV5()
        elif self.collector_name == "v3":
            self.collector = SlidingCollector()
        else:
            raise ValueError("BWE_COLLECTOR only accepts v3 or v5, got %r" % self.collector_name)
        self.envelope = None
        self.envelope_name = (os.environ.get("BWE_ENVELOPE", "") or "0").strip()
        if self.envelope_name == "1":
            from estimator.safety_envelope import SafetyEnvelope
            self.envelope = SafetyEnvelope()
        elif self.envelope_name == "3":
            from estimator.safety_envelope_v3 import SafetyEnvelope
            self.envelope = SafetyEnvelope()
        elif self.envelope_name == "4":
            from estimator.safety_envelope_v4 import SafetyEnvelope
            self.envelope = SafetyEnvelope()
        elif self.envelope_name != "0":
            raise ValueError("BWE_ENVELOPE only accepts 0, 1, 3, or 4, got %r" % self.envelope_name)
        self.bank = ArmBank(d)
        self.core = SwitchCore(SwitchNet(Path(d) / "switch_nn_deploy_v1.npz"))
        tp = (os.environ.get("BWE_SWITCH_TRACE", "") or os.environ.get("BWE_OBS_TRACE", "")).strip()
        self.trace = open(tp, "a") if tp else None

    def report_states(self, stats):
        self.collector.report_states(stats)

    def get_estimated_bandwidth(self):
        import time as _t
        t0 = _t.perf_counter()
        obs = self.collector.observation()
        preds = self.bank.step(obs)
        if self.fixed is None:
            pred, arm = self.core.step(obs[0] / 1e6, obs[30], obs[60], obs[90], obs[100], preds)
        else:
            pred, arm = float(preds[self.fixed]), self.fixed
            self.core.r += 1
        est_bps = max(pred, 0.0) * 1e6
        if self.envelope is not None:
            est_bps = self.envelope.apply(est_bps, obs, self.collector.clock())
        if self.trace:
            self.trace.write(json.dumps({"r": self.core.r - 1, "t_ms": self.collector.clock(), "arm": arm,
                                         "preds_mbps": [float(v) for v in preds], "obs": obs,
                                         "truthful_media": self.collector.last_truthful_media,
                                         "wraps": self.collector.n_wraps, "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": est_bps, "envelope": (self.envelope.last if self.envelope is not None else None),
                                         "compute_ms": (_t.perf_counter() - t0) * 1000}) + "\n")
            self.trace.flush()
        return int(est_bps)
