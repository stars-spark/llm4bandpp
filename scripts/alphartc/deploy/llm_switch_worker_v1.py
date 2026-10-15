#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inference worker process for the LLM switcher; runs apart from the per-step path with its own thread count.
Protocol: one JSON per stdin line {id, text}, one JSON per stdout line {id, arm, ms, probs}, after a first line {ready, load_s}; the model is switch_llm_stage_train_v2.Selector.
Usage: llm_switch_worker_v1.py MODEL_DIR [THREADS]; MODEL_DIR holds config.json, tokenizer files and deploy_LLM_FT.pt.
"""
import json, os, sys, time
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import torch
from torch import nn


class Selector(nn.Module):
    def __init__(self, cfg_dir):
        super().__init__()
        from transformers import AutoConfig, AutoModel
        self.body = AutoModel.from_config(AutoConfig.from_pretrained(cfg_dir), torch_dtype=torch.float32)
        self.ln = nn.LayerNorm(self.body.config.hidden_size); self.head = nn.Linear(self.body.config.hidden_size, 4)

    def forward(self, ids, mask):
        h = self.body(input_ids=ids, attention_mask=mask).last_hidden_state
        return self.head(self.ln(h[torch.arange(h.size(0)), mask.sum(1) - 1]))


def load(model_dir):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_dir); tok.padding_side = "right"
    m = Selector(model_dir); w = torch.load(f"{model_dir}/deploy_LLM_FT.pt", map_location="cpu", weights_only=False)
    m.body.load_state_dict({k: v.float() for k, v in w["body"].items()}, strict=True)
    m.ln.load_state_dict(w["ln"], strict=True); m.head.load_state_dict(w["head"], strict=True); m.eval()
    return tok, m, w.get("arms")


def decide(tok, m, text):
    enc = tok([text], return_tensors="pt")
    with torch.inference_mode():
        p = torch.softmax(m(enc["input_ids"], enc["attention_mask"]).float(), -1)[0]
    return int(p.argmax()), [float(x) for x in p]


def main():
    model_dir = sys.argv[1]; threads = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    torch.set_num_threads(threads); t0 = time.time(); tok, m, arms = load(model_dir)
    decide(tok, m, "f0_mean=1 f0_cv=0")
    print(json.dumps({"ready": True, "load_s": round(time.time() - t0, 3), "threads": threads, "arms": arms}), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        req = json.loads(line); t1 = time.perf_counter(); arm, probs = decide(tok, m, req["text"])
        print(json.dumps({"id": req["id"], "arm": arm, "ms": round((time.perf_counter() - t1) * 1000, 2), "probs": probs}), flush=True)


if __name__ == "__main__":
    main()
