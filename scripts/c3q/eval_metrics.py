#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-call metric functions (MSE, overestimation, underestimation, clipped relative error), identical to those in eval_value_per_file.py.
Evaluation scripts import them from here so the metric code exists once.
"""
import numpy as np


def mse(x, y):
    return np.nanmean(np.asarray([(a - b) ** 2 for a, b in zip(x, y)], dtype=np.float32))


def over(x, y):
    return np.nanmean(
        np.asarray([max((a - b) / b, np.float32(0)) for a, b in zip(x.flat, y.flat)], dtype=np.float32)
    )


def under(x, y):
    return np.nanmean(
        np.asarray([max(np.float32(0), (b - a) / b) for a, b in zip(x.flat, y.flat)], dtype=np.float32)
    )


def clipped_relative_error(x, y):
    return np.nanmean(
        np.asarray([min(1, np.float32(abs(a - b) / b)) for a, b in zip(x.flat, y.flat)], dtype=np.float32)
    )
