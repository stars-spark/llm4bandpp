#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analytic FLOPs per decision of the deployed estimator (conference encoder, HCQ, no LLM) for the cost table, Table III (client-hw-ch-v1).
Convention: a multiply-add counts 2; linear layers, attention and other matrix products are counted by torch FlopCounterMode; biases and element-wise ops are not.
FlopCounterMode does not count nn.LSTM, so gate products 2*4*H*(I_l+H)*steps*directions are added per layer from forward hooks; this encoder has
no LSTM, so the counter gives the total. dead_code_flops counts TemporalAttention, executed but unused (zero for this model).
Self-test first: Linear gives 2*in*out, a lone LSTM gives 0, the two-layer bidirectional formula matches a hand count.
Model: load_agent of ch_estimator_v1 with the seed-1 checkpoint ckpt/ch.pt, batch 1, CPU. Output: experiments/results/client_hw_ch_v1/flops.json.
Usage: python3 scripts/paper/flops_ch_v1.py
"""
import json, sys
from pathlib import Path
import torch, torch.nn as nn
from torch.utils.flop_counter import FlopCounterMode
ROOT = Path(__file__).resolve().parents[2]; D = ROOT / "scripts/alphartc/deploy/ch_estimator_v1"; sys.path.insert(0, str(D))
OUT = ROOT / "experiments/results/client_hw_ch_v1/flops.json"


def lstm_flops(m, x):
    """Gate matrix-product FLOPs of LSTM m on input x (a multiply-add counts 2), summed over layers and directions."""
    T = x.shape[1] if m.batch_first else x.shape[0]; B = x.shape[0] if m.batch_first else x.shape[1]
    nd = 2 if m.bidirectional else 1; H = m.hidden_size; tot = 0
    for layer in range(m.num_layers):
        I = m.input_size if layer == 0 else H * nd
        tot += 2 * 4 * H * (I + H) * T * nd * B
    return tot


def count(model, x):
    lst = []
    hooks = [mod.register_forward_hook(lambda mod, inp, out: lst.append(lstm_flops(mod, inp[0]))) for mod in model.modules() if isinstance(mod, nn.LSTM)]
    with torch.no_grad(), FlopCounterMode(display=False) as fc: model(x)
    for h in hooks: h.remove()
    return fc.get_total_flops(), sum(lst), len(lst)


def selftest():
    lin = nn.Linear(7, 5);
    with torch.no_grad(), FlopCounterMode(display=False) as fc: lin(torch.randn(1, 7))
    assert fc.get_total_flops() == 2 * 7 * 5, fc.get_total_flops()
    l = nn.LSTM(4, 16, batch_first=True)
    with torch.no_grad(), FlopCounterMode(display=False) as fc: l(torch.randn(1, 5, 4))
    assert fc.get_total_flops() == 0
    l2 = nn.LSTM(3, 6, num_layers=2, bidirectional=True, batch_first=True)
    manual = 2 * (2 * 4 * 6 * (3 + 6) * 9) + 2 * (2 * 4 * 6 * (12 + 6) * 9)
    assert lstm_flops(l2, torch.randn(1, 9, 3)) == manual
    print("Self-test passed")


def main():
    selftest()
    from ch_estimator_v1 import load_agent
    model = load_agent(str(D / "ckpt/ch.pt"), "cpu"); x = torch.randn(1, 150)
    mm, lstm, n_lstm = count(model, x)
    ta = [m for n, m in model.named_modules() if type(m).__name__ == "TemporalAttention"]
    dead = 0
    for m in ta:
        cap = {}
        h = m.register_forward_hook(lambda mod, inp, out: cap.setdefault("in", inp))
        with torch.no_grad(): model(x)
        h.remove()
        with torch.no_grad(), FlopCounterMode(display=False) as fc: m(*cap["in"])
        dead += fc.get_total_flops()
    res = {"model": "C-H seed 1 (ch_estimator_v1/ckpt/ch.pt)", "params": sum(p.numel() for p in model.parameters()), "batch": 1,
           "matmul_flops": mm, "lstm_flops": lstm, "n_lstm_calls": n_lstm, "total_flops": mm + lstm, "dead_code_flops": dead,
           "convention": "A multiply-add counts as 2; only linear layers, attention and LSTM gate matrix products are counted, not biases or element-wise operations"}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1)); print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
