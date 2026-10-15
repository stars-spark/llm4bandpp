# Cost of the deployment-time designer (designer-cost-v1, exploratory)

Prices from the official DeepSeek pricing page https://api-docs.deepseek.com/quick_start/pricing (retrieved 2026-10-03): deepseek-flash (DeepSeek-V4.1-Flash), per million tokens: input (cache miss) 0.3 USD at peak and 0.15 USD off-peak, output 1.2 USD at peak and 0.6 USD off-peak; the off-peak price is half the peak price.

| Item | Value | Source |
|---|---|---|
| Calls per new client | 1 | by design |
| Prompt tokens (median) | 1028 | the 21 calls of realtel-adapter-v1 |
| Output tokens including reasoning (median, maximum) | 10482, 22381 | as above |
| Output tokens with masked names (median) | 14598 | the 21 calls of realtel-namehide-v1 |
| Cost per client, peak (median, maximum) | 0.0129, 0.0272 USD | tokens times the official price |
| Cost per client, off-peak (median) | 0.0064 USD | as above |
| Wall time (one call per source, 7 real sources; median, range) | 37.5 s, 15.9 to 61.0 s | measured by us, timed_deepseek.jsonl |
| Open R1 distillation 32B, 4-bit, 21 clients in total | 5 min 8 s (two Tesla V100S, concurrency 8), median 1157 output tokens | gpu-server-1 run log |
| Adapter execution per step (15 features) | 0.33 µs (Python on our machine) | measured by us |
| Reference: the one-token LLM variant, per step | median 42 ms on four CPU threads | client-hw-hcq-v1 |

The designer runs outside the real-time loop and is called once, when a new client is integrated, for about one US cent and half a minute to a minute; afterwards each step only runs a lookup, a difference and a scale factor, in under a microsecond.
