#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic vLLM generation for the open reasoning models: as version 1 it reads JSONL prompts, applies the chat template and appends one line per prompt to OUT.jsonl (id, text,
number of generated tokens, finish_reason), resumes where it stopped and writes OUT.jsonl.DONE; same V100 settings.
Version 2: copy of version 1 that adds --temp, --top-p, --seed and --max-seqs (the defaults give the greedy decoding and concurrency of version 1) and records finish_reason,
so answers cut at the token limit are visible. The R1 distillations run at temperature 0.6 and top_p 0.95, the settings their publisher recommends. Used for the open R1
designer rows (Fig. 3, Tables II and IV) and the small-model runs (realtel-designer-scale-v1, realtel-scale-r1qwen-size-v1); DESIGNER.md gives the commands.
Usage: python vllm_generate_v2.py MODEL IN.jsonl OUT.jsonl --tp 2 --max-len 40960 --max-new 32768 --temp 0.6 --top-p 0.95 [--seed S] [--max-seqs N]
"""
import json, sys
from pathlib import Path
def arg(k, d): return type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
model, inp, outp = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]); tp, ml, mn = arg("--tp", 2), arg("--max-len", 8192), arg("--max-new", 4096); temp, topp, seed, mseq = arg("--temp", 0.0), arg("--top-p", 1.0), arg("--seed", 20261002), arg("--max-seqs", 256)
from vllm import LLM, SamplingParams
from transformers import AutoTokenizer
rows = [json.loads(l) for l in open(inp)]; done = {json.loads(l)["id"] for l in open(outp)} if outp.exists() else set(); rows = [r for r in rows if r["id"] not in done]
tok = AutoTokenizer.from_pretrained(model); texts = [tok.apply_chat_template([{"role": "user", "content": r["prompt"]}], tokenize=False, add_generation_prompt=True) for r in rows]
llm = LLM(model=model, dtype="float16", tensor_parallel_size=tp, max_model_len=ml, gpu_memory_utilization=0.88, enable_prefix_caching=False, enable_chunked_prefill=False, max_num_batched_tokens=ml, enforce_eager=True, seed=seed, max_num_seqs=mseq)
sp = SamplingParams(max_tokens=mn, temperature=temp, top_p=topp, seed=seed)
for s in range(0, len(rows), 16):
    res = llm.generate(texts[s:s + 16], sp)
    with open(outp, "a") as f:
        for r, o in zip(rows[s:s + 16], res): f.write(json.dumps({"id": r["id"], "text": o.outputs[0].text, "n_tokens": len(o.outputs[0].token_ids), "finish_reason": o.outputs[0].finish_reason}, ensure_ascii=False) + "\n")
    print("complete", min(s + 16, len(rows)), "/", len(rows), flush=True)
open(str(outp) + ".DONE", "w").write("ok")
