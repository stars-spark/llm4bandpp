# -*- coding: utf-8 -*-
"""Arm arm_lambda: no-LLM estimators trained with the HCQ reward at different λ; BWE_LAMBDA_CKPT selects the checkpoint.
Each is the multi-scale encoder (StateEncoderDualScaleLSTM) with an output head (about 4.2 MB); forward pass and input scaling as in training. Collector (v5 or v6) and probing envelope (0 or 4) are chosen as in online_llm_arms_v3.
"""
import json, os, time
from estimator.online_llm_arms_v3 import _collector, _envelope


class _LambdaNet:
    def __init__(self, torch, dev, ckpt):
        import torch.nn as nn
        from estimator.module_dual import StateEncoderDualScaleLSTM
        from estimator.module import BweHead
        self.torch = torch
        state = torch.load(ckpt, map_location=dev)
        hid = int(state["stateencoder.output_projection.0.weight"].shape[0]) if "stateencoder.output_projection.0.weight" in state else 1024

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.log_std = nn.Parameter(torch.zeros(1, dtype=torch.float32))
                self.stateencoder = StateEncoderDualScaleLSTM(150, hid, dev)
                self.bwe_head = BweHead(hid, 512, 1, 20, dev)
                self.encoder0 = nn.Parameter(torch.zeros(150, dtype=torch.float32), requires_grad=False)

            def forward(self, x):
                return self.bwe_head(self.stateencoder(x * self.encoder0))

        self.net = Net().to(dev)
        missing, unexpected = self.net.load_state_dict(state, strict=False)
        assert not missing and not unexpected, f"λ arm weight keys do not match: missing {len(missing)} extra {len(unexpected)}"
        self.net.eval()

    def __call__(self, obs):
        with self.torch.inference_mode():
            return float(self.net.forward(self.torch.tensor(obs, dtype=self.torch.float32).reshape(1, 150)))


class LambdaArmEstimator:
    def __init__(self):
        import torch
        self.torch = torch; torch.set_num_threads(int(os.environ.get("BWE_TORCH_THREADS", "4")))
        self.collector_name, self.collector = _collector(); self.envelope_name, self.envelope = _envelope()
        ck = os.environ.get("BWE_LAMBDA_CKPT", "/app/model/lambda_arms/lam4_50000.pt")
        self.tag = os.path.basename(ck).split("_")[0]; self.model = _LambdaNet(torch, torch.device("cpu"), ck)
        self.r = 0; tp = (os.environ.get("BWE_SWITCH_TRACE", "") or os.environ.get("BWE_OBS_TRACE", "")).strip(); self.trace = open(tp, "a") if tp else None

    def report_states(self, stats): self.collector.report_states(stats)

    def get_estimated_bandwidth(self):
        t0 = time.perf_counter(); obs = self.collector.observation(); raw = getattr(self.collector, "raw_observation", obs)
        model_bps = max(self.model(obs), 0.0)
        bps = self.envelope.apply(model_bps, raw, self.collector.clock()) if self.envelope is not None else model_bps
        if self.trace:
            self.trace.write(json.dumps({"r": self.r, "t_ms": self.collector.clock(), "arm": 0, "arm_name": "lambda_" + self.tag, "preds_mbps": [model_bps / 1e6], "obs": raw,
                                         "audio_restored": self.collector_name == "v6", "truthful_media": self.collector.last_truthful_media, "wraps": self.collector.n_wraps,
                                         "collector": self.collector_name, "envelope_version": self.envelope_name, "est_bps": bps, "model_bps": model_bps,
                                         "envelope": (self.envelope.last if self.envelope is not None else None), "compute_ms": (time.perf_counter() - t0) * 1000}) + "\n"); self.trace.flush()
        self.r += 1; return int(bps)
