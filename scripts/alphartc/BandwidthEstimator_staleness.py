#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AlphaRTC receiver-side bandwidth-estimator entry point, installed as BandwidthEstimator.py in the receiver container: BWE_ESTIMATOR selects the arm,
BWE_DELAY_MS injects output staleness, and BWE_DELAY_TRACE records the requested and realised age of every applied estimate.
Base of the family: BandwidthEstimator_staleness_v2.py to _v18.py are copies that each add or reroute one or two arms and leave the other branches unchanged.
Installed by run_staleness_once_twocontainer.sh (early closed-loop batches such as switch-deploy-collector-v1) and by the midsnap run scripts before v3,
which are not in this package (trace-replay-shaping-diag-v2). No Table V or Fig. 4 batch uses this version.
"""
import os
import sys
import time

import torch

from delay_wrapper import DelayedEstimator
from estimator.gcc import GCCEstimator

from fixed_bandwidth_estimator import FixedBandwidthEstimator


def _load_qwen_dual():
    from estimator.estimator_dual import bwe_agent_Qwen_dual

    threads = int(os.environ.get("BWE_TORCH_THREADS", "4"))
    torch.set_num_threads(threads)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = bwe_agent_Qwen_dual(device=device)
    checkpoint = os.environ.get(
        "BWE_QWEN_CHECKPOINT", "/app/model/Qwen_dual_merged.pth"
    )
    started = time.time()
    try:
        state = torch.load(checkpoint, map_location=device, weights_only=True)
    except TypeError:  # PyTorch before weights_only was introduced
        state = torch.load(checkpoint, map_location=device)
    for name in ("stateencoder", "llm", "bwe_head"):
        getattr(model, name).load_state_dict(state[name], strict=True)
    if "encoder0" in state:
        model.encoder0.data.copy_(state["encoder0"].to(device))
    model.eval()
    print(
        "[staleness] loaded qwen_dual checkpoint=%s threads=%d seconds=%.3f"
        % (checkpoint, threads, time.time() - started),
        flush=True,
    )

    # The original online class builds an autograd graph for every decision.
    # Estimators are used for inference only, so gradients are disabled here.
    original_get = model.get_estimated_bandwidth

    obs_trace_path = os.environ.get("BWE_OBS_TRACE", "").strip()
    obs_handle = None
    if obs_trace_path:
        import json as _json
        from estimator.estimator import get_observation_vector as _get_obs
        parent = os.path.dirname(obs_trace_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        obs_handle = open(obs_trace_path, "a", buffering=1)

    def inference_get():
        with torch.inference_mode():
            if obs_handle is not None:
                try:
                    vec = _get_obs(model.short_term_mis, model.long_term_mis)
                    obs_handle.write(_json.dumps({"obs": [float(v) for v in vec]}) + "\n")
                except Exception as exc:
                    obs_handle.write(_json.dumps({"error": repr(exc)}) + "\n")
            return original_get()

    model.get_estimated_bandwidth = inference_get
    return model


def _make_inner(name):
    if name == "gcc":
        return GCCEstimator()
    if name == "gcc_pt125":
        from estimator.gcc_pt125_v1 import GCCEstimatorPT125
        return GCCEstimatorPT125()
    if name == "qwen_dual":
        return _load_qwen_dual()
    if name == "fixed_240":
        return FixedBandwidthEstimator(240000)
    if name == "fixed_env":
        return FixedBandwidthEstimator()
    if name == "qwen25_contextual":
        bundle = os.environ.get(
            "BWE_QWEN25_BUNDLE", "/app/model/contextual_qwen25_online"
        )
        if bundle not in sys.path:
            sys.path.insert(0, bundle)
        from online_contextual_qwen25 import load_online_actor

        started = time.time()
        actor = load_online_actor(bundle_dir=bundle)
        print(
            "[staleness] loaded qwen25 contextual audit=%r seconds=%.3f"
            % (actor.online_load_audit, time.time() - started),
            flush=True,
        )
        return actor
    if name == "c3_risk3":
        bundle = os.environ.get(
            "BWE_C3_RISK_BUNDLE", "/app/model/c3_risk3_online"
        )
        if bundle not in sys.path:
            sys.path.insert(0, bundle)
        from online_c3_risk import load_online_actor

        started = time.time()
        actor = load_online_actor(bundle_dir=bundle)
        print(
            "[staleness] loaded c3 risk3 audit=%r seconds=%.3f"
            % (actor.online_load_audit, time.time() - started),
            flush=True,
        )
        return actor
    if name == "switch_nn":
        from estimator.switcher import SwitchEstimator

        started = time.time()
        est = SwitchEstimator()
        print("[staleness] loaded switch_nn seconds=%.3f" % (time.time() - started), flush=True)
        return est
    fixed_arms = {"arm_pioneer": 0, "arm_schaferct_public": 1, "arm_schaferct_retrained": 2, "arm_mlp": 3}
    if name in fixed_arms:
        from estimator.switcher import SwitchEstimator

        started = time.time()
        est = SwitchEstimator(fixed_arm=fixed_arms[name])
        print("[staleness] loaded %s seconds=%.3f" % (name, time.time() - started), flush=True)
        return est
    if name == "switch_llm":
        from estimator.online_llm_arms_v1 import LLMSwitchEstimator

        started = time.time()
        est = LLMSwitchEstimator()
        print("[staleness] loaded switch_llm seconds=%.3f" % (time.time() - started), flush=True)
        return est
    if name == "arm_llm4bandpp":
        from estimator.online_llm_arms_v1 import LLM4bandppV5Estimator

        started = time.time()
        est = LLM4bandppV5Estimator()
        print("[staleness] loaded arm_llm4bandpp seconds=%.3f" % (time.time() - started), flush=True)
        return est
    if name == "arm_lambda":
        from estimator.online_lambda_arms_v1 import LambdaArmEstimator

        started = time.time()
        est = LambdaArmEstimator()
        print("[staleness] loaded arm_lambda seconds=%.3f" % (time.time() - started), flush=True)
        return est
    if name == "switch_nn_x":
        from estimator.switcher_x_v1 import SwitchXEstimator

        started = time.time()
        est = SwitchXEstimator()
        print("[staleness] loaded switch_nn_x seconds=%.3f" % (time.time() - started), flush=True)
        return est
    if name in ("arm_pioneer_x", "arm_schaferct_public_x", "arm_schaferct_retrained_x", "arm_mlp_x"):
        from estimator.fixed_x_v1 import FixedXEstimator

        started = time.time()
        est = FixedXEstimator(name)
        print("[staleness] loaded %s seconds=%.3f" % (name, time.time() - started), flush=True)
        return est
    if name in ("arm_llm4bandpp_x", "arm_llm4band_conf_x"):
        from estimator.online_llm_arms_v3 import LLM4bandppXEstimator, LLM4bandConfXEstimator

        started = time.time()
        est = LLM4bandppXEstimator() if name == "arm_llm4bandpp_x" else LLM4bandConfXEstimator()
        print("[staleness] loaded %s seconds=%.3f" % (name, time.time() - started), flush=True)
        return est
    if name == "switch_gccguard":
        from estimator.switcher_gcc_guard_v1 import GccGuardSwitchEstimator

        started = time.time()
        est = GccGuardSwitchEstimator()
        print("[staleness] loaded switch_gccguard seconds=%.3f" % (time.time() - started), flush=True)
        return est
    if name == "arm_llm4band_conf":
        from estimator.online_conference_arm_v1 import LLM4bandConfV5Estimator

        started = time.time()
        est = LLM4bandConfV5Estimator()
        print("[staleness] loaded arm_llm4band_conf seconds=%.3f" % (time.time() - started), flush=True)
        return est
    raise ValueError(
        "unsupported BWE_ESTIMATOR=%r; use gcc, gcc_pt125, qwen_dual, fixed_240, fixed_env, qwen25_contextual, c3_risk3, switch_nn, switch_llm, "
        "switch_gccguard, switch_nn_x, arm_lambda, arm_llm4bandpp, arm_llm4band_conf, arm_llm4bandpp_x, arm_llm4band_conf_x, arm_schaferct_public_x or arm_pioneer, arm_schaferct_public, arm_schaferct_retrained, arm_mlp"
        % name
    )


class Estimator(DelayedEstimator):
    def __init__(self):
        name = os.environ.get("BWE_ESTIMATOR", "gcc").strip().lower()
        delay_ms = float(os.environ.get("BWE_DELAY_MS", "0"))
        super().__init__(_make_inner(name), delay_ms=delay_ms)
        print(
            "[staleness] estimator=%s requested_delay_ms=%g trace=%s"
            % (name, delay_ms, os.environ.get("BWE_DELAY_TRACE", "")),
            flush=True,
        )
