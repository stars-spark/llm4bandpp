# -*- coding: utf-8 -*-
"""Training-time configuration check, run manifest and monitor for ablation-enc-hcq-2x2-v1; imported by the patched IQL.py in the shared code directory.
enc_hcq_2x2_setup: reads BWE_ENC, BWE_REWARD_LAMBDA, BWE_PICKLE and BWE_QWEN_DIR (no defaults; a missing or unlisted value exits),
  rejects any change to the frozen recipe, and checks that the cell and seed in --env match the environment variables.
enc_hcq_2x2_write_manifest: once the replay buffer is filled, writes code hashes, library versions, the reward audit and hashes of the six buffer
  columns; across the four cells every column except rewards must hash identically.
Enc2x2Monitor: aborts on a non-finite loss, records peak GPU memory at steps 3 and 200 (allocator and nvidia-smi), seconds per step over
  steps 100 to 200 and per 1000-step window, and writes TRAIN_DONE.json at the end. Nothing here changes training values.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

EXPERIMENT = "ablation-enc-hcq-2x2-v1"
ALLOWED_ENC = ("conf15", "ms15")
ALLOWED_LAMBDA = {"0.0": 0.0, "0.4": 0.4}
CELL_OF = {("conf15", "0.0"): "CB", ("conf15", "0.4"): "CH",
           ("ms15", "0.0"): "MB", ("ms15", "0.4"): "MH"}
FROZEN = dict(batch_size=512, discount=0.99, tau=0.005, beta=3.0, iql_tau=0.7,
              iql_deterministic=False, vf_lr=3e-4, qf_lr=3e-4, actor_lr=3e-4,
              actor_dropout=None, reward_mode="capped_mre", source_reward_lambda=0.4,
              capacity_aux_weight=1.0, capacity_huber_delta=1.0, load_model="")
CODE_FILES = ("IQL.py", "estimator.py", "module.py", "model.py", "dualEncoder.py",
              "enc_hcq_2x2_encoders.py", "enc_hcq_2x2_runtime.py", "variants.py")
HERE = Path(__file__).resolve().parent


def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def code_sha256() -> dict:
    return {f: sha256_file(HERE / f) for f in CODE_FILES if (HERE / f).is_file()}


def enc_hcq_2x2_setup(config) -> dict:
    enc = os.environ.get("BWE_ENC")
    lam = os.environ.get("BWE_REWARD_LAMBDA")
    pk = os.environ.get("BWE_PICKLE")
    qd = os.environ.get("BWE_QWEN_DIR")
    if enc not in ALLOWED_ENC:
        raise SystemExit(f"BWE_ENC must explicitly take one of {ALLOWED_ENC}, got {enc!r}, refusing to start")
    if lam not in ALLOWED_LAMBDA:
        raise SystemExit(f"BWE_REWARD_LAMBDA must explicitly take one of {sorted(ALLOWED_LAMBDA)}, got {lam!r}, refusing to start")
    if not pk or not os.path.isfile(pk):
        raise SystemExit(f"BWE_PICKLE not set or file does not exist: {pk!r}")
    if not qd or not os.path.isfile(os.path.join(qd, "config.json")):
        raise SystemExit(f"BWE_QWEN_DIR not set or not a Qwen weights directory: {qd!r}")
    bad = {k: getattr(config, k) for k, v in FROZEN.items() if getattr(config, k) != v}
    if bad:
        raise SystemExit(f"Frozen recipe was modified: {bad}, expected { {k: FROZEN[k] for k in bad} }")
    if not (isinstance(config.reward_error_cap, float) and math.isinf(config.reward_error_cap)
            and config.reward_error_cap > 0):
        raise SystemExit(f"The relative error term must not be truncated, reward_error_cap should be inf, actual {config.reward_error_cap}")
    # -1.0 is the command-line default; λ may only come from BWE_REWARD_LAMBDA.
    if config.reward_lambda != -1.0:
        raise SystemExit("reward_lambda can only be specified by BWE_REWARD_LAMBDA, and must not be given on the command line")
    cell = CELL_OF[(enc, lam)]
    parts = str(config.env).split("-")
    if len(parts) != 3 or parts[0] not in ("e2x2", "e2x2smk", "e2x2pair") or parts[1] != cell \
            or parts[2] != f"s{config.seed}":
        raise SystemExit(f"--env {config.env!r} does not match the cell {cell} or seed {config.seed} given by the environment variable, refusing to start")
    config.reward_lambda = ALLOWED_LAMBDA[lam]
    print("ENC_HCQ_2X2_CELL " + json.dumps({"cell": cell, "enc": enc, "reward_lambda": lam,
                                             "seed": config.seed, "pickle": pk, "qwen_dir": qd}),
          flush=True)
    return {"cell": cell, "enc": enc, "reward_lambda": lam, "pickle_path": pk, "qwen_dir": qd}


def _hash_tensor(t: torch.Tensor, n: int) -> str:
    a = np.ascontiguousarray(t[:n].numpy())
    return hashlib.sha256(a.reshape(-1).view(np.uint8)).hexdigest()


def state_dict_sha256(*modules) -> str:
    h = hashlib.sha256()
    for m in modules:
        for k, v in m.state_dict().items():
            h.update(k.encode())
            a = np.ascontiguousarray(v.detach().float().cpu().numpy())
            h.update(a.reshape(-1).view(np.uint8))
    return h.hexdigest()


def _versions() -> dict:
    out = {"python": sys.version.split()[0], "torch": torch.__version__, "numpy": np.__version__}
    for name in ("transformers", "peft"):
        try:
            out[name] = __import__(name).__version__
        except Exception as e:
            out[name] = f"unavailable: {e}"
    return out


def manifest_path(config) -> Path:
    return Path(config.checkpoints_path) / "enc_hcq_2x2_run.json"


def enc_hcq_2x2_write_manifest(config, cell: dict, replay_buffer) -> None:
    n = int(replay_buffer._size)
    rb = replay_buffer
    t0 = time.time()
    buf = {"states": _hash_tensor(rb._states, n), "actions": _hash_tensor(rb._actions, n),
           "rewards": _hash_tensor(rb._rewards, n), "next_states": _hash_tensor(rb._next_states, n),
           "dones": _hash_tensor(rb._dones, n), "capacities": _hash_tensor(rb._capacities, n)}
    rew = rb._rewards[:n].numpy().astype(np.float64)
    man = {
        "experiment": EXPERIMENT, "created_at": _now(), "host": socket.gethostname(),
        "argv": sys.argv, "cell": cell["cell"], "BWE_ENC": cell["enc"],
        "BWE_REWARD_LAMBDA": cell["reward_lambda"], "seed": int(config.seed), "env": config.env,
        "device": config.device, "max_timesteps": int(config.max_timesteps),
        "eval_freq": int(config.eval_freq), "batch_size": int(config.batch_size),
        "reward_error_cap": str(config.reward_error_cap),
        "pickle_path": cell["pickle_path"], "pickle_size": os.path.getsize(cell["pickle_path"]),
        "qwen_dir": cell["qwen_dir"], "code_dir": str(HERE), "code_sha256": code_sha256(),
        "versions": _versions(), "reward_audit": getattr(rb, "reward_audit", None),
        "rows_valid": n, "buffer_sha256": buf,
        "reward_stats": {"mean": float(rew.mean()), "min": float(rew.min()), "max": float(rew.max())},
        "hash_seconds": round(time.time() - t0, 1),
    }
    manifest_path(config).write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
    print("ENC_HCQ_2X2_MANIFEST " + json.dumps({"rows_valid": n, "buffer_sha256": buf}), flush=True)


def _physical_gpu(device: str):
    if not str(device).startswith("cuda"):
        return None
    idx = int(str(device).split(":")[1]) if ":" in str(device) else 0
    vis = [x.strip() for x in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if x.strip()]
    return vis[idx] if idx < len(vis) else str(idx)


def _smi_used_mib(phys):
    if phys is None:
        return None
    try:
        r = subprocess.run(["nvidia-smi", "-i", str(phys), "--query-gpu=memory.used",
                            "--format=csv,noheader,nounits"], text=True, capture_output=True,
                           timeout=30)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return None


class Enc2x2Monitor:
    def __init__(self, config, actor, q_network, v_network):
        self.config = config
        self.dev = torch.device(config.device)
        self.cuda = self.dev.type == "cuda"
        self.phys = _physical_gpu(config.device)
        self.t0 = time.time()
        self.t100 = None
        self.win_t = time.time()
        self.records = {}
        self.ticks = {}
        self.last = {}
        trainable = sum(p.numel() for p in actor.parameters() if p.requires_grad)
        enc_params = sum(p.numel() for p in actor.stateencoder.parameters())
        init_sha = state_dict_sha256(q_network, v_network, actor)
        self.models = {"actor_trainable_params": int(trainable), "encoder_params": int(enc_params),
                       "encoder_kind": getattr(actor, "encoder_kind", None),
                       "init_sha256_q_v_actor": init_sha}
        print("ENC_HCQ_2X2_MODELS " + json.dumps(self.models), flush=True)
        mp = manifest_path(config)
        man = json.loads(mp.read_text(encoding="utf-8"))
        man["models"] = self.models
        mp.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _mem(self, step):
        rec = {"step": step, "elapsed_s": round(time.time() - self.t0, 2)}
        if self.cuda:
            torch.cuda.synchronize(self.dev)
            rec["max_reserved_mib"] = round(torch.cuda.max_memory_reserved(self.dev) / 2**20, 1)
            rec["max_allocated_mib"] = round(torch.cuda.max_memory_allocated(self.dev) / 2**20, 1)
            rec["smi_gpu_used_mib"] = _smi_used_mib(self.phys)
        return rec

    def after_step(self, step: int, log_dict: dict) -> None:
        for k, v in log_dict.items():
            if not math.isfinite(float(v)):
                raise FloatingPointError(f"Step {step} {k}={v} is not finite, aborting this run")
        self.last = {k: float(v) for k, v in log_dict.items()}
        if step == 100:
            self.t100 = time.time()
        if step % 100 == 0:
            self.ticks[str(step)] = round(time.time(), 3)
            print(f"ENC_HCQ_2X2_TICK {step} {self.ticks[str(step)]}", flush=True)
        if step in (3, 200):
            rec = self._mem(step)
            rec.update(self.last)
            if step == 200 and self.t100 is not None:
                rec["s_per_step_100_200"] = round((time.time() - self.t100) / 100, 4)
            self.records[str(step)] = rec
            print("ENC_HCQ_2X2_PROBE " + json.dumps(rec), flush=True)
        if step % 1000 == 0:
            now = time.time()
            rec = self._mem(step)
            rec["window_s_per_step"] = round((now - self.win_t) / 1000, 4)
            rec.update(self.last)
            self.win_t = now
            self.records["last_window"] = rec
            print("ENC_HCQ_2X2_PROGRESS " + json.dumps(rec), flush=True)

    def finish(self) -> None:
        cp = Path(self.config.checkpoints_path)
        ckpts = sorted(cp.glob("checkpoint_*.pt"), key=lambda p: int(p.stem.split("_")[1]))
        done = {"experiment": EXPERIMENT, "finished_at": _now(), "host": socket.gethostname(),
                "steps": int(self.config.max_timesteps), "total_s": round(time.time() - self.t0, 1),
                "probes": self.records, "final_losses": self.last, "models": self.models,
                "ticks": self.ticks,
                "checkpoints": {p.name: p.stat().st_size for p in ckpts}}
        (cp / "TRAIN_DONE.json").write_text(json.dumps(done, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
        print("ENC_HCQ_2X2_DONE " + json.dumps({k: done[k] for k in ("steps", "total_s")}), flush=True)
