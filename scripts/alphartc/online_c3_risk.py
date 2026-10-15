"""AlphaRTC adapter for an estimator of an earlier study (C3 risk3; not in the paper, weights not shipped).

It loads the estimator's training code and checkpoint unchanged and adds the 60/600 ms collector fixed in
online-state-defects-diagnosis-and-fix-v29.
"""

import collections
import importlib
import os
import sys

import torch

_ALPHARTC_ROOT = os.environ.get("BWE_ALPHARTC_ROOT", "/app")
if _ALPHARTC_ROOT not in sys.path:
    sys.path.insert(0, _ALPHARTC_ROOT)
from estimator import estimator as online_base


def load_online_actor(bundle_dir=None, checkpoint=None, device=None):
    bundle_dir = bundle_dir or os.environ.get(
        "BWE_C3_RISK_BUNDLE", "/app/model/c3_risk3_online"
    )
    checkpoint = checkpoint or os.environ.get(
        "BWE_C3_RISK_CHECKPOINT",
        "/app/model/c3_risk3_online/checkpoint_50000.pt",
    )
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)
    training = importlib.import_module("training_estimator")

    class OnlineActor(training.bwe_agent):
        initialize_mi = online_base.bwe_agent_Qwen_base.initialize_mi
        update_mi = online_base.bwe_agent_Qwen_base.update_mi
        report_states = online_base.bwe_agent_Qwen_base.report_states

        def __init__(self, actor_device):
            super().__init__(20, 150, 1, actor_device)
            self.short_term_mis = collections.deque(maxlen=5)
            self.long_term_mis = collections.deque(maxlen=5)
            for _ in range(5):
                self.short_term_mis.append(dict(online_base.empty_mi))
                self.long_term_mis.append(dict(online_base.empty_mi))
            self.mi_duration_short = 60
            self.mi_duration_long = 600
            self.current_short_mi = self.initialize_mi(0, self.mi_duration_short)
            self.current_long_mi = self.initialize_mi(0, self.mi_duration_long)

        def get_estimated_bandwidth(self):
            observation = online_base.get_observation_vector(
                self.short_term_mis, self.long_term_mis
            )
            obs = torch.tensor(
                observation, dtype=torch.float32, device=self.device
            ).reshape(1, 150)
            with torch.inference_mode():
                bandwidth, _ = self.forward(obs)
            return int(bandwidth.reshape(-1)[0].item())

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    actor = OnlineActor(device)
    try:
        state = torch.load(checkpoint, map_location=device, weights_only=True)
    except TypeError:
        state = torch.load(checkpoint, map_location=device)
    incompatible = actor.load_state_dict(state, strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise RuntimeError("strict checkpoint load unexpectedly returned incompatible keys")
    actor.eval()
    actor.online_load_audit = {
        "checkpoint": checkpoint,
        "missing_keys": list(incompatible.missing_keys),
        "unexpected_keys": list(incompatible.unexpected_keys),
        "has_llm_module": hasattr(actor, "llm"),
        "encoder_variant": getattr(actor.stateencoder, "variant", None),
    }
    return actor

