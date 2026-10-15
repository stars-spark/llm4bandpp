# -*- coding: utf-8 -*-
"""NumPy forward pass of the adapted expert MLP, shared by its training script and the adapt_x arm.
Weights are an npz file (scale for encoder0, w1 b1 w2 b2 w3 b3); the network is 150-256-256-1 with ReLU and a Softplus output in Mbps, so the container needs no torch state_dict.
"""
import numpy as np


def load_weights(path):
    return {k: np.asarray(v, dtype=np.float32) for k, v in np.load(path).items()}


def forward_np(W, x):
    """Map raw observations x of shape (n, 150), audio already added, to estimates of shape (n,) in Mbps, layer for layer as the torch model."""
    h = np.asarray(x, dtype=np.float32) * W["scale"]
    h = np.maximum(h @ W["w1"] + W["b1"], 0.0)
    h = np.maximum(h @ W["w2"] + W["b2"], 0.0)
    z = h @ W["w3"] + W["b3"]
    return np.logaddexp(0.0, z)[:, 0]
