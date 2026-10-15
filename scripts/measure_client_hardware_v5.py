# -*- coding: utf-8 -*-
"""Latency and energy of the estimators on the client hardware (client-hw-ch-v1, Table III). Protocol fixed at registration: batch size 1 (batch 512 only as a side note); 50 warm-up
and 500 timed calls with torch.cuda.synchronize around each; p50, p95, p99 and maximum; inputs drawn with the per-dimension mean and std of the MRE_4 training set; energy from
power.draw over the window minus idle, per call, once the readings are checked; temperature, SM clock and charger state recorded. The LLM arms (hcq, full_conf) use a randomly
initialized network of the same architecture, since latency, energy and memory do not depend on the weights; ch and nl load their real weights.
Version 5: copy of v4 (not in this package; v4 added the multi-scale no-LLM arm nl for client-hw-nl-v1, v2 the one-token HCQ model for client-hw-hcq-v1) that adds the arm ch,
C-H from deploy/ch_estimator_v1/ckpt/ch.pt (seed 1, policy mean). Usage: measure_client_hardware_v5.py --code CODE_DIR --stats STATS.json --config QWEN_CONFIG.json --out OUT.json [--ckpt-dir DIR] [--reps 500] [--warmup 50] [--arms A,B] [--devices D]
"""
from __future__ import annotations

import argparse, json, os, statistics as st, subprocess, sys, threading, time
from pathlib import Path

import numpy as np
import torch

S = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--code", required=True)
ap.add_argument("--stats", required=True)
ap.add_argument("--ckpt-dir", default="")
ap.add_argument("--config", required=True, help="Qwen1.5-0.5B config.json")
ap.add_argument("--out", required=True)
ap.add_argument("--reps", type=int, default=500)
ap.add_argument("--warmup", type=int, default=50)
ap.add_argument("--arms", default="", help="Comma-separated; test only these arms")
ap.add_argument("--devices", default="", help="Comma-separated; test only these devices")
args = ap.parse_args()
sys.path.insert(0, args.code)

DS = json.loads(Path(args.stats).read_text(encoding="utf-8"))
MU = np.asarray(DS["mu"], dtype=np.float32)
SD = np.asarray(DS["sd"], dtype=np.float32)


def gpu_query(fields):
    r = subprocess.run(["nvidia-smi", f"--query-gpu={fields}",
                        "--format=csv,noheader,nounits"], text=True, capture_output=True)
    return [x.strip() for x in r.stdout.strip().split(",")]


class PowerSampler(threading.Thread):
    """Sample the GPU power every 50 ms in the background, for the energy integral."""

    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop_flag = [], False

    def run(self):
        while not self.stop_flag:
            try:
                self.samples.append((time.perf_counter(), float(gpu_query("power.draw")[0])))
            except Exception:
                pass
            time.sleep(0.05)

    def energy_j(self, t0, t1):
        pts = [(t, p) for t, p in self.samples if t0 <= t <= t1]
        if len(pts) < 2:
            return None, None
        e = sum((pts[i + 1][0] - pts[i][0]) * (pts[i + 1][1] + pts[i][1]) / 2
                for i in range(len(pts) - 1))
        return e, st.mean(p for _, p in pts)


def on_ac_power() -> str:
    for p in Path("/sys/class/power_supply").glob("A*/online"):
        try:
            return "connect external power" if p.read_text().strip() == "1" else "Battery powered"
        except OSError:
            pass
    return "unknown"


def build(name, device):
    """Build the arms. Version of client-hw-hcq-v1: the two end-to-end arms follow the deployed forward pass, randomly initialized
    with the same architecture.
        hcq: input times the 150-value scaling vector, through StateEncoderDualScaleLSTM (including the TemporalAttention whose
             output is discarded but which runs at every call), reshaped into one token fed as inputs_embeds to the
             Qwen1.5-0.5B body, last hidden state, then BweHead.
        full_conf: the same with the conference StateEncoder, as the Full arm of v1, measured in the same round.
        Deployment uses merged weights without LoRA adapters at inference, so the body is the Qwen2Model of AutoModel.from_config.
        Encoders alone: E_hcq is the HCQ encoder with its dead module, E_conf the conference encoder.
    """
    if name == "ch":
        sys.path.insert(0, str(S / "alphartc/deploy/ch_estimator_v1"))
        from ch_estimator_v1 import load_agent as load_ch
        agent_ch = load_ch(str(S / "alphartc/deploy/ch_estimator_v1/ckpt/ch.pt"), device)

        class MeanCH(torch.nn.Module):
            def __init__(self):
                super().__init__(); self.agent = agent_ch

            def forward(self, x):
                return self.agent(x)[0]
        return MeanCH().to(device).eval()
    if name == "nl":
        sys.path.insert(0, str(S / "alphartc/deploy/nl_estimator_v1"))
        from nl_estimator_v1 import load_agent
        agent = load_agent(str(S / "alphartc/deploy/nl_estimator_v1/ckpt/NLs1/checkpoint_50000.pt"), device)

        class Mean(torch.nn.Module):
            def __init__(self):
                super().__init__(); self.agent = agent

            def forward(self, x):
                return self.agent(x)[0]
        return Mean().to(device).eval()
    from transformers import AutoConfig, AutoModel
    import module as M
    if name in ("hcq", "hcq_fast", "full_conf"):
        cfg = AutoConfig.from_pretrained(args.config)
        cfg.torch_dtype = torch.float32
        from hcq_encoder_fast_v1 import FastStateEncoderDualScale

        class Est(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder0 = torch.nn.Parameter(torch.ones(150), requires_grad=False)
                encoder_cls = (M.StateEncoderDualScaleLSTM if name == "hcq"
                               else FastStateEncoderDualScale if name == "hcq_fast"
                               else M.StateEncoder)
                self.stateencoder = encoder_cls(150, 1024, device)
                self.llm = AutoModel.from_config(cfg)
                self.bwe_head = M.BweHead(1024, 512, 1, 20, device)

            def forward(self, x):
                x = self.stateencoder(x * self.encoder0)
                x = self.llm(inputs_embeds=torch.unsqueeze(x, dim=1)).last_hidden_state
                return self.bwe_head(torch.squeeze(x, dim=1))
        return Est().to(device).eval()
    from hcq_encoder_fast_v1 import FastStateEncoderDualScale
    enc = {"E_hcq": lambda: M.StateEncoderDualScaleLSTM(150, 1024, device),
           "E_hcq_fast": lambda: FastStateEncoderDualScale(150, 1024, device),
           "E_conf": lambda: M.StateEncoder(150, 1024, device)}[name]()
    return enc.to(device).eval()


def timed(model, device, batch, reps, warmup, is_agent):
    x = torch.from_numpy(MU + SD * np.random.randn(batch, 150).astype(np.float32)).to(device)
    cuda = device.startswith("cuda")
    if cuda:
        torch.cuda.reset_peak_memory_stats()
    with torch.inference_mode():
        for _ in range(warmup):
            model(x)
        if cuda:
            torch.cuda.synchronize()
        lat = []
        t0 = time.perf_counter()
        for _ in range(reps):
            s = time.perf_counter()
            model(x)
            if cuda:
                torch.cuda.synchronize()
            lat.append((time.perf_counter() - s) * 1000.0)
        t1 = time.perf_counter()
    lat.sort()
    q = lambda p: lat[min(len(lat) - 1, int(round(p * (len(lat) - 1))))]
    out = {"batch": batch, "reps": reps, "p50": q(.5), "p95": q(.95), "p99": q(.99),
           "max": lat[-1], "mean": st.mean(lat), "window": (t0, t1)}
    if cuda:
        out["peak_alloc_mib"] = torch.cuda.max_memory_allocated() / 2**20
        out["peak_reserved_mib"] = torch.cuda.max_memory_reserved() / 2**20
    return out


ARMS = args.arms.split(",") if args.arms else ["hcq", "hcq_fast", "E_hcq", "E_hcq_fast"]
result = {"host": os.uname().nodename, "ac_power": on_ac_power(),
          "torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
          "note_full_arm": "The Full arm is randomly initialized with the same architecture; latency, energy, and memory are independent of the weight values; we do not copy others' trained weights to this machine",
          "arms": {}}
if torch.cuda.is_available():
    result["gpu"] = torch.cuda.get_device_name(0)

if torch.cuda.is_available():
    base = PowerSampler(); base.start(); time.sleep(3.0); base.stop_flag = True; base.join(1)
    result["idle_power_w"] = st.mean(p for _, p in base.samples) if base.samples else None

DEVS = (args.devices.split(",") if args.devices
        else (["cuda:0"] if torch.cuda.is_available() else []) + ["cpu"])
for dev in DEVS:
    torch.set_num_threads(4 if dev == "cpu" else torch.get_num_threads())
    for arm in ARMS:
        key = f"{arm}@{dev}"
        try:
            m = build(arm, dev)
        except Exception as e:
            result["arms"][key] = {"error": str(e)[:300]}
            print(f"{key:<16} construction failed {str(e)[:120]}", flush=True)
            continue
        n_par = sum(p.numel() for p in m.parameters())
        pre = gpu_query("temperature.gpu,clocks.sm") if dev.startswith("cuda") else None
        smp = None
        if dev.startswith("cuda"):
            smp = PowerSampler(); smp.start()
        r1 = timed(m, dev, 1, args.reps, args.warmup, arm in ("hcq", "full_conf"))
        r512 = timed(m, dev, 512, max(20, args.reps // 20), 5, arm in ("hcq", "full_conf"))
        post = gpu_query("temperature.gpu,clocks.sm") if dev.startswith("cuda") else None
        if smp:
            smp.stop_flag = True; smp.join(1)
            e_j, p_mean = smp.energy_j(*r1["window"])
            idle = result.get("idle_power_w") or 0.0
            if e_j is not None:
                dur = r1["window"][1] - r1["window"][0]
                r1["energy_total_j"] = e_j
                r1["energy_net_mj_per_inference"] = (e_j - idle * dur) / args.reps * 1000.0
                r1["mean_power_w"] = p_mean
        for r in (r1, r512):
            r.pop("window", None)
        result["arms"][key] = {"params": n_par, "batch1": r1, "batch512": r512,
                               "temp_clock_before": pre, "temp_clock_after": post}
        del m
        if dev.startswith("cuda"):
            torch.cuda.empty_cache()
        print(f"{key:<16} parameter {n_par:>11,}  batch1 p50 {r1['p50']:7.3f}  p95 {r1['p95']:7.3f}  p99 {r1['p99']:7.3f} ms", flush=True)

Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
print("\nWritten", args.out)
