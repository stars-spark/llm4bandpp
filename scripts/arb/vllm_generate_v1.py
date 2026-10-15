#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic vLLM generation, version 1: reads JSONL (one id and prompt per line), applies the chat template, decodes greedily (temperature 0) up to MAX_NEW tokens and appends one line
per prompt to OUT.jsonl (id, text, number of generated tokens); resumes where it stopped and writes OUT.jsonl.DONE at the end. On V100 GPUs: tensor parallel, prefix caching and
chunked prefill off, CUDA graphs off.
Used for the greedy Qwen2.5-32B-Instruct designer runs (obsschema-llm-openmodel-v1); vllm_generate_v2.py adds sampling for the reasoning models.
Usage: python vllm_generate_v1.py MODEL IN.jsonl OUT.jsonl --tp 2 --max-len 8192 --max-new 4096
"""
import json, sys
from pathlib import Path
def arg(k, d): return type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
model, inp, outp = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]); tp, ml, mn = arg("--tp", 2), arg("--max-len", 8192), arg("--max-new", 4096)
from vllm import LLM, SamplingParams
from transformers import AutoTokenizer
rows = [json.loads(l) for l in open(inp)]; done = {json.loads(l)["id"] for l in open(outp)} if outp.exists() else set(); rows = [r for r in rows if r["id"] not in done]
tok = AutoTokenizer.from_pretrained(model); texts = [tok.apply_chat_template([{"role": "user", "content": r["prompt"]}], tokenize=False, add_generation_prompt=True) for r in rows]
llm = LLM(model=model, dtype="float16", tensor_parallel_size=tp, max_model_len=ml, gpu_memory_utilization=0.88, enable_prefix_caching=False, enable_chunked_prefill=False, max_num_batched_tokens=ml, enforce_eager=True, seed=20261002)
sp = SamplingParams(max_tokens=mn, temperature=0.0)
for s in range(0, len(rows), 16):
    res = llm.generate(texts[s:s + 16], sp)
    with open(outp, "a") as f:
        for r, o in zip(rows[s:s + 16], res): f.write(json.dumps({"id": r["id"], "text": o.outputs[0].text, "n_tokens": len(o.outputs[0].token_ids)}, ensure_ascii=False) + "\n")
    print("complete", min(s + 16, len(rows)), "/", len(rows), flush=True)
open(str(outp) + ".DONE", "w").write("ok")
