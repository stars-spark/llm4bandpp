#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The single copy of encoder0, the fixed scale of the 150 input values that every estimator of the paper multiplies its
observation by; every script imports it from here. The values were extracted programmatically from the estimator code of the
paper's implementation and match it bit for bit. Layout is feature-major: dimension = feature index * 10 + interval
index, intervals 0 to 4 being the five 60 ms windows and 5 to 9 the five 600 ms windows. Features in order: receiving
rate, received packets, received bytes, queuing delay, delay minus base delay, minimum observed delay, delay ratio,
delay difference, packet inter-arrival time, jitter, loss ratio, mean lost packets, video, audio and probing packet
shares. Features 1 and 2 scale their short and long windows differently, as in the original implementation.
"""

ENCODER0 = (
    1e-06, 1e-06, 1e-06, 1e-06, 1e-06, 1e-06, 1e-06, 1e-06, 1e-06, 1e-06,
    0.1, 0.1, 0.1, 0.1, 0.1, 0.01, 0.01, 0.01, 0.01, 0.01,
    0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 1e-05, 1e-05, 1e-05, 1e-05, 1e-05,
    0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1,
    0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
    0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1,
    0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1,
    0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1,
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
)

assert len(ENCODER0) == 150, f"encoder0 must be 150, got {len(ENCODER0)}"


def as_numpy(dtype="float64"):
    import numpy as np
    return np.asarray(ENCODER0, dtype=dtype)


def as_tensor(device=None, dtype=None):
    import torch
    t = torch.tensor(ENCODER0, dtype=dtype or torch.float32)
    return t.to(device) if device is not None else t


def assert_matches(agent) -> None:
    """Compare with the encoder0 of a live estimator; every script that uses encoder0 calls this once."""
    import numpy as np
    live = agent.encoder0.detach().cpu().numpy().astype("float64")
    ref = as_numpy()
    if live.shape != ref.shape or not np.allclose(live, ref, rtol=0, atol=0):
        raise AssertionError(f"agent's encoder0 does not match the authoritative copy: {live.shape} versus {ref.shape}")
