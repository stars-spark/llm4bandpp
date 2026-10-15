#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ablation-enc-hcq-2x2-v1: build the code directory shared by the four cells of the encoder by reward ablation on the
fifteen-token LLM variant (16 runs of one directory). Two environment variables without defaults select the cell:
BWE_ENC (conf15 or ms15, the encoder) and BWE_REWARD_LAMBDA (0.0 or 0.4; rewards relabelled from MRE_4 by
relabel_hcq_reward with no cap on the error term); BWE_PICKLE and BWE_QWEN_DIR hold the machine-specific paths, so the
code hashes match on both servers. The source is the mt_anchor directory of llm-indispensability-mt-anchor-3seed; the
hashes of its five files are checked and every patch anchor below must occur exactly once. Three new files are copied
(enc_hcq_2x2_encoders.py, enc_hcq_2x2_runtime.py, variants.py). The source estimator.py of the LLM arm is not in this
package, so the directory cannot be rebuilt from it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path("/path/to/server/work/rcaiql_screen_v1/mt_anchor")
HERE = Path(__file__).resolve().parent
DST = Path("/path/to/server/work/enc_hcq_2x2_v1/arm")
MANIFEST = Path("/path/to/server/work/enc_hcq_2x2_v1/arm_manifest.json")
EXPECTED = {
    "IQL.py": "f8c834926b7908751d725f1afa80303dc9218c859d0fd0c4a42d85bf7778c06b",
    "module.py": "645ddc461220e508234d4e1cd68968fa641a97237fbeb83c9bb9f8f44b92feef",
    "estimator.py": "18c653b10067c53344c249f4d43e159624b23722ad992a20f6c46482dd895805",
    "model.py": "c8dad8401fefb358fe0fe8dc37abfe3fe9542d9781f3b1bb91bf441b860a9a11",
    "dualEncoder.py": "2b7bca18000ac8ece958a6bf44927be2860bd471c2462c4ad3934f9ebf8e3b2e",
}
NEW_FILES = ("enc_hcq_2x2_encoders.py", "enc_hcq_2x2_runtime.py", "variants.py")
MAX_COPY_BYTES = 50 * 1024 * 1024
TAG = "ENC_HCQ_2X2_V1"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: the anchor should appear exactly once, got {n}, rejecting the change")
    return text.replace(old, new, 1)


def patch_estimator(s: str) -> str:
    assert TAG not in s, "estimator.py has been patched"
    assert "import os" in s
    s = once(s,
             'Qwen1_5_weight_hf_format_dir = "/path/to/challenge/Qwen1.5/Qwen1.5-0.5B-hf"\n'
             'Qwen1_5_config_hf_format_dir = "/path/to/challenge/Qwen1.5/Qwen1.5-0.5B-hf/config.json"\n',
             f'# {TAG}: the Qwen weight directory differs across machines, so it is specified by BWE_QWEN_DIR instead, with no default, and a missing value raises KeyError\nQwen1_5_weight_hf_format_dir = os.environ["BWE_QWEN_DIR"]\nQwen1_5_config_hf_format_dir = os.path.join(Qwen1_5_weight_hf_format_dir, "config.json")\n',
             "estimator Qwen path")
    s = once(s, "from dualEncoder import StateEncoderDualScaleLSTMpro\n",
             "from dualEncoder import StateEncoderDualScaleLSTMpro\n"
             f"from enc_hcq_2x2_encoders import ENCODERS  # {TAG}\n", "estimator import")
    s = once(s,
             "class bwe_agent(nn.Module):\n    def __init__(self, max_action, state_dim, action_dim, device):\n",
             "class bwe_agent(nn.Module):\n    def __init__(self, max_action, state_dim, action_dim, device, encoder=None):\n",
             "bwe_agent constructs the signature")
    s = once(s, "        self.stateencoder = StateEncoderDualScaleLSTM(self.state_dim, 1024, self.device)\n",
             f"        # {TAG}: make_actor passes the encoder chosen by BWE_ENC; everything outside the two encoders is unchanged\n        if encoder not in ENCODERS:\n            raise ValueError(f\"bwe_agent encoder must be one of {{sorted(ENCODERS)}}, got {{encoder!r}}\")\n        self.encoder_kind = encoder\n        self.stateencoder = ENCODERS[encoder](self.state_dim, 1024, self.device)\n",
             "bwe_agent encoder")
    s += (f"\n\n# {TAG}\ndef bwe_enc_from_env():\n    \"\"\"Read BWE_ENC, no default: on misconfiguration it must fail immediately, not silently run as another cell.\"\"\"\n    which = os.environ.get(\"BWE_ENC\", \"\")\n    if which not in ENCODERS:\n        raise ValueError(f\"BWE_ENC must explicitly be one of {{sorted(ENCODERS)}}, got {{which!r}}\")\n    return which\n\n\ndef make_actor(max_action, state_dim, action_dim, device):\n    return bwe_agent(max_action, state_dim, action_dim, device, encoder=bwe_enc_from_env())\n")
    return s


def patch_iql(t: str) -> str:
    assert TAG not in t, "IQL.py has been patched"
    t = once(t, "from estimator import bwe_agent\n",
             f"from estimator import bwe_agent, make_actor  # {TAG}\n"
             "from enc_hcq_2x2_runtime import (Enc2x2Monitor, enc_hcq_2x2_setup,\n"
             "                                 enc_hcq_2x2_write_manifest)\n", "IQL import")
    t = once(t,
             "pickle_path = '/path/to/challenge/solution/dataset/training_dataset_pickle/MRE/MRE_4.pickle'\n",
             f"# {TAG}: the original value was the absolute path of MRE_4 on gpu-server-2, changed to be specified at runtime by BWE_PICKLE, with no default\npickle_path = None\n", "IQL pickle path")
    t = once(t,
             "evaluation_dataset_path = '/path/to/challenge/solution/evaluate_dataset'\n"
             "ENUM = 120  # every 5 evaluation set\n"
             "small_evaluation_datasets = []\n"
             "evaluate_dataset_file_names = os.listdir(evaluation_dataset_path)\n"
             "for e_f_name in evaluate_dataset_file_names[:ENUM]:\n"
             "    e_f_path = os.path.join(evaluation_dataset_path, e_f_name)\n"
             "    small_evaluation_datasets.append(e_f_path)\n",
             f"# {TAG}: the original code listed the evaluation directories on gpu-server-2 at import time, training never uses it (the evaluate call has been commented out),\n# keeping it would make the code differ between the two machines, so it is changed to an empty list\nENUM = 120  # every 5 evaluation set\nsmall_evaluation_datasets = []\n", "IQL evaluation directory")
    t = once(t, "os.environ['CUDA_VISIBLE_DEVICES'] = '0, 1'\n",
             f"# {TAG}: originally an unconditional override; changed to set only when unset, the effect is the same for formal runs,\n# it just lets the pure CPU initialization hash check on gpu-server-2 completely avoid the GPU with an empty CUDA_VISIBLE_DEVICES\nos.environ.setdefault('CUDA_VISIBLE_DEVICES', '0, 1')\n", "IQL CUDA_VISIBLE_DEVICES")
    t = once(t,
             "    reward_lambda: float = 0.4\n    reward_error_cap: float = 5.0\n",
             f"    reward_lambda: float = -1.0  # {TAG}: can only be specified by BWE_REWARD_LAMBDA, -1 means not yet read\n    reward_error_cap: float = float(\"inf\")  # {TAG}: relative error term is not truncated\n",
             "TrainConfig reward")
    t = once(t,
             '        print("REWARD_AUDIT " + json.dumps(audit, sort_keys=True))\n',
             f'        print("REWARD_AUDIT " + json.dumps(audit, sort_keys=True))\n        self.reward_audit = audit  # {TAG}: write into the run manifest\n', "replay buffer audit")
    t = once(t,
             '    torchBwModel = bwe_agent(MAX_ACTION, STATE_DIM, ACTION_DIM, "cuda")\n',
             '    torchBwModel = make_actor(MAX_ACTION, STATE_DIM, ACTION_DIM, "cuda")\n', "export2onnx instantiation")
    t = once(t,
             "        else bwe_agent(\n            max_action, state_dim, action_dim, config.device\n        )\n",
             "        else make_actor(\n            max_action, state_dim, action_dim, config.device\n        )\n",
             "actor instantiation")
    t = once(t,
             "    train_policy_loss = []\n\n    testdataset_file = open(pickle_path, 'rb')\n",
             f"    train_policy_loss = []\n    cell = enc_hcq_2x2_setup(config)  # {TAG}: read the two factors and machine paths, verify the frozen recipe\n\n    testdataset_file = open(cell[\"pickle_path\"], 'rb')\n", "train start")
    t = once(t,
             '        with open(os.path.join(config.checkpoints_path, "config.yaml"), "w") as f:\n'
             "            pyrallis.dump(config, f)\n",
             '        with open(os.path.join(config.checkpoints_path, "config.yaml"), "w") as f:\n'
             "            pyrallis.dump(config, f)\n"
             f"    enc_hcq_2x2_write_manifest(config, cell, replay_buffer)  # {TAG}\n", "run manifest")
    t = once(t,
             "    default_tensor_type = torch.get_default_dtype()\n\n"
             "    for t in range(int(config.max_timesteps)):\n"
             "        batch = replay_buffer.sample(config.batch_size)\n"
             "        batch = [b.to(config.device) for b in batch]\n"
             "        log_dict, policy_loss = trainer.train(batch)\n",
             f"    default_tensor_type = torch.get_default_dtype()\n    monitor = Enc2x2Monitor(config, actor, q_network, v_network)  # {TAG}\n\n    for t in range(int(config.max_timesteps)):\n        batch = replay_buffer.sample(config.batch_size)\n        batch = [b.to(config.device) for b in batch]\n        log_dict, policy_loss = trainer.train(batch)\n        monitor.after_step(t + 1, log_dict)  # {TAG}: abort on non-finite loss, record GPU memory and seconds per step\n",
             "training loop")
    t = once(t,
             "                train_policy_loss = []\n\n\nif __name__ == \"__main__\":\n",
             f"                train_policy_loss = []\n    monitor.finish()  # {TAG}: write TRAIN_DONE.json\n\n\nif __name__ == \"__main__\":\n",
             "Training finished")
    return t


def busy_with(d: Path) -> list:
    """Processes whose working directory lies inside the target directory, so that we never rebuild it while a run uses it."""
    hits = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if str(Path(os.readlink(p / "cwd"))).startswith(str(d)):
                hits.append(p.name)
        except OSError:
            continue
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="Replace the target directory if it already exists; still refuse if it is in use by a process")
    a = ap.parse_args()

    for f, h in EXPECTED.items():
        got = sha(SRC / f)
        if got != h:
            raise SystemExit(f"{SRC / f} hash {got[:8]} does not match {h[:8]} registered in Section 1.3 of the pre-registration, aborting")
    if DST.exists():
        if not a.rebuild:
            raise SystemExit(f"{DST} already exists; pass --rebuild to replace it (refused while a process runs inside it)")
        users = busy_with(DST)
        if users:
            raise SystemExit(f"A process is using {DST} as its working directory: {users}, refusing to rebuild")
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    total = 0
    for f in list(EXPECTED) + list(NEW_FILES):
        src = (SRC / f) if f in EXPECTED else (HERE / f)
        total += src.stat().st_size
        assert total <= MAX_COPY_BYTES, f"files to copy total {total} bytes, above the limit {MAX_COPY_BYTES}; stopping"
        shutil.copy2(src, DST / f)
        (DST / f).chmod(0o644)
    print(f"Copy {len(EXPECTED) + len(NEW_FILES)} files per the whitelist, {total / 1024:.1f} KiB total")

    est, iql = DST / "estimator.py", DST / "IQL.py"
    est.write_text(patch_estimator(est.read_text(encoding="utf-8")), encoding="utf-8")
    t = patch_iql(iql.read_text(encoding="utf-8"))
    iql.write_text(t, encoding="utf-8")

    bad = [ln for ln in t.split("\n")
           if "bwe_agent(" in ln and not ln.strip().startswith("#")]
    assert not bad, f"IQL.py still has direct calls to bwe_agent: {bad}"
    imports = [ln for ln in t.split("\n") if ln.startswith("from estimator import")]
    assert imports == [f"from estimator import bwe_agent, make_actor  # {TAG}"], imports
    assert t.count("make_actor(") == 2, "make_actor should have exactly two instantiations"
    assert "os.listdir(" not in t, "Must not list the directory again during import"
    assert "/path/to/challenge_home" not in t and "/path/to/challenge_home" not in est.read_text(encoding="utf-8"), \
        "The code must no longer contain machine-specific absolute paths"
    for f in ("estimator.py", "IQL.py", "enc_hcq_2x2_encoders.py", "enc_hcq_2x2_runtime.py", "variants.py"):
        r = subprocess.run([sys.executable, "-m", "py_compile", str(DST / f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f} compilation failed: {r.stderr[-400:]}"
    shutil.rmtree(DST / "__pycache__", ignore_errors=True)

    files = sorted(p.name for p in DST.iterdir() if p.is_file())
    man = {"experiment": "ablation-enc-hcq-2x2-v1", "source": str(SRC),
           "source_sha256": EXPECTED, "arm_dir": str(DST),
           "code_sha256": {f: sha(DST / f) for f in files}}
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Hash of the code shared by the four cells:")
    for f in files:
        print(f"  {f:<26} {man['code_sha256'][f]}")
    print(f"Generation complete: {DST}, manifest {MANIFEST}")


if __name__ == "__main__":
    main()
