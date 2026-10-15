# The deployment-time designer: rescoring and rerunning

The designer is an LLM called once per client to map its telemetry fields (names and documentation, or names and value
percentiles) onto the 15 interface features. Part (a) recomputes every designer number of the paper and the supplement
from the files in this package, without calling a model. Part (b) reruns the calls, which needs a key for the hosted
model or two GPUs for the open models.

`experiments/results/designer_models_v1/models.json` lists every designer result file that holds model answers: model,
request or decoding settings, seed, GPUs, what was stored and when the calls were made. Names used below (`realtel`,
`obsschema`, `namehide`, `truth_v3`, ...) are defined in `docs/GLOSSARY.md`.

## Before you start

- Python 3.13.13 with `requirements-level1.txt` (tested). The getStats closure test (`closure_v2.py judge`) also needs
  onnxruntime; figures need matplotlib. Each command of part (a) runs in under 40 s on a laptop CPU.
- Set the path placeholders as in `docs/PACKAGE.md`. Most scripts find the package from their own location;
  `scripts/arb/obsschema_judge_v1.py` and the closed-loop scripts need the placeholders.
- Judge commands rewrite their result file in place (`docs/PACKAGE.md`, "How to tell that a result was reproduced"). We reran every command below on a
  copy of the package: each rewritten file came out byte-identical, except for one count ("12 stacks, one count").
- Three scripts only read and compare, writing nothing or only their own new output: the offline rescoring
  `scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py`, `scripts/coldstart/mask_offline_local_v1.py` and
  `scripts/paper/make_designer_per_stack_v1.py`. Each exits with status 1 if it does not reproduce the recorded files.

## (a) Rescore every designer number

Commands run from the package root with `python3`. The estimator downstream of the designer in the synthetic-schema
replays, the getStats derivation test and the closed-loop test of Fig. 3(c) is the challenge baseline,
`schaferct_public.onnx` (`docs/GLOSSARY.md`).

| Result | Command | Reads, writes |
|---|---|---|
| Synthetic schemas, 4 held-out schemas: hosted designer 32 of 32 groups, 24 with names masked; name and distribution matching 0 (Tables IV and II) | `scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py old` | checks `obsschema_v1/llm_test.jsonl` mappings against `transforms_test.json`, the replayed mappings and `judge_test.json` |
| Same groups, open models: R1 32B 24 of 32, R1 14B 17 of 32 (reparsed from the full answers), Qwen2.5-32B 17 of 32 | same command | `openreason_v1/out_r1_*.jsonl`, `obsschema_v1/open_qwen32b.jsonl` |
| Five newer schemas, real against masked names: R1 32B 36 against 1 of 40, R1 14B 27 against 1 of 40 (Table II) | `scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py new` | `obsschema_rt_openreason_v1/out_rt_r1_*.jsonl`, `eval_*`, `judge_*` |
| Unit-aware matcher 32 of 32 and 71 of 72; open 32B 60 of 72 pooled | `scripts/arb/obsschema_strong_baseline_v1.py judge` | `obsschema_strong_baseline_v1/judge.json` |
| Seven specifications: balanced accuracy (BA) 1.000 against 0.756 for TF-IDF; with different definitions scored as missing 0.940 against 0.738; open 32B and 14B 0.917 and 0.879 | `scripts/coldstart/realtel_revise_v1.py` | writes `realtel_adapter_v1/truth_v3.json` (the third, revised version of the ground truth, built from `truth_v2.json`) and `revise_v3.json` (the readings under it) |
| Seven specifications, field names hidden: 1.000 | `scripts/coldstart/realtel_namehide_v1.py judge` | `realtel_adapter_v1/namehide_v1/judge.json` |
| Counterfactual documentation: rewrite followed in 33 of 33 cells | `scripts/coldstart/realtel_cfdoc_v1.py judge` | `realtel_adapter_v1/cfdoc_v1/judge.json` |
| 12 client stacks: BA 0.920 against 0.560 for Cupid (+0.36, 0.27 to 0.45); chosen field only 0.940 against 0.773 for COMA; first-round labels 0.962 against 0.707; no false map in 72 decisions; wall time and cost per client | `scripts/coldstart/realtel_scale_v1.py judge` | `realtel_scale_v1/judge.json` (see the note below) |
| Per stack: 8 of the 11 scored stacks correct in all field orders; 12 errors on Agora, mediasoup and ns-3; 0.938 with the ns-3 cell unscored | `scripts/paper/make_designer_per_stack_v1.py` | writes `realtel_scale_v1/per_stack.csv` |
| 12 stacks, field names hidden: 0.947 | `scripts/coldstart/realtel_scale_namehide_v1.py judge` | `realtel_scale_v1/namehide/judge.json` |
| Two repeated calls: 0.94 and 0.96, 92% of feature cells agreeing | `scripts/coldstart/realtel_repeat_v1.py judge` | `realtel_repeat_v1/judge.json` |
| Same LLM as generic schema matcher: 0.719 (chosen field 0.979 against 0.940) | `scripts/coldstart/llm_schema_match_v1.py judge` | `llm_schema_match_v1/judge.json` |
| Fields then units in two calls: 0.966; end to end 38 of 42 for one call, 42 for two | `scripts/coldstart/llm_twostep_match_v1.py judge` | `llm_twostep_match_v1/judge.json` |
| Different definitions scored as missing on the 12 stacks: 0.865 against 0.597 for COMA | `scripts/coldstart/realtel_scale_kindmiss_explore.py` | `realtel_scale_v1/kindmiss_explore.json` |
| Open models on the 12 stacks, first sample: 59 and 29 of 75 mappable cases, all 72 unmappable declared missing, 1 and 12 of 36 answers unparsable | `scripts/coldstart/realtel_scale_v1.py open_score` | prints; reads `out_open_r1_32b.jsonl`, `out_open_r1_14b.jsonl` |
| Open models, three samples: BA 0.89 and 0.70; end-to-end shares 0.62 and 0.37 | `scripts/coldstart/open_sampling_variance_v1.py score` | `open_sampling_variance_v1/summary.json` (also scores the 70B, which the paper does not use) |
| Model size, R1 distillations into Qwen: 0.50, 0.55, 0.70, 0.89 at 1.5B to 32B; 11 to 13 of 36 answers parse at 1.5B | `scripts/coldstart/r1qwen_size_v1.py score` | `realtel_scale_r1qwen_size_v1/summary.json` |
| Qwen1.5-0.5B-Chat as designer: 0.500 on the 12 stacks, 0 of 40 synthetic groups | `scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py designer-scale` | checks `realtel_designer_scale_v1/judge.json` |
| Engineer's blind labels: 38 disagreements and their categories | read `gt_blind_expert_v1_public/adjudication.json` | |
| Rescored with the engineer's labels: 0.824 against 0.615 for COMA (0.15 to 0.27) | `scripts/coldstart/gt_engineer_sens_v1.py` | `gt_blind_expert_v1/engineer_truth_sens_v1.json` |
| Real software end to end: 42 of 42 cells, Similarity Flooding 32 (0.762) | `scripts/realtel_e2e/realtel_e2e_v1.py judge`, then `scripts/paper/make_tables_v2.py` | run alone, the judge scores all 48 cells against the first ground truth, the labels fixed at registration (Similarity Flooding 0.667); the paper's 42 cells and 0.762 use the third, revised ground truth, applied by the function `e2e_v3` in `make_tables_v2.py` (status P in Table IV) |
| Lead over the generic LLM matcher when all methods share one value rule (every field whose values never fall during the run is differenced): +0.10 (0.02 to 0.18) | `scripts/realtel_e2e/e2e_valuerule_v1.py` | `realtel_e2e_valuerule_v1/judge.json` |
| Features a stack exposes as single fields: macro MSE 5.80 rises to 9.0 to 23.3 | `scripts/coldstart/mask_offline_local_v1.py` | checks `realtel_mask_offline_v2/summary.json` |
| Browser getStats derivation function: 0.197 against 0.463 for Cupid's mapping, 0.240 for the single-field mapping | `scripts/realtel_e2e/closure_v2.py judge` | `realtel_closure_v1/v2/judge.json`; needs onnxruntime |
| Closed loop with the challenge baseline downstream: deviation 1.16 against 6.01, 7.62, 11.16; losses over 10 points 0, 7, 8, 8 | `scripts/paper/make_fig_closedloop_designer_v2.py` | recomputes the cells from the per-run results in `external/testbed/results/obsschema-closedloop-v2/` and checks `result_v1.json` |
| Tables IV and II | `scripts/paper/make_tables_v2.py` | `papers/revision-v2/tables/table_designer.tex`, `table_position.tex` |

**12 stacks, one count.** Of the 11 stacks with a scored feature, 8 are correct on every scored feature in all field
orders, as the paper reports and as `make_designer_per_stack_v1.py` and `realtel_scale_v1.py judge` compute. The
shipped `realtel_scale_v1/judge.json` was written by an earlier version of the judge that also counted LiveKit, which
has no scored feature, and gives `sources_all_correct_all_pres` = 9. Rerunning the judge writes 8 and leaves LiveKit out
of `per_source_all_correct`; every other field is unchanged.

The agreement with the engineer (68 of 84 scored pairs, Cohen's kappa 0.22) was computed by
`scripts/paper/gt_blind_compare_v1.py` from the engineer's filled sheet, which is not released;
`gt_blind_expert_v1/result.json` holds every cell it extracted. The same two numbers, from the package root:

```bash
python3 - <<'EOF'
import json
cells = json.load(open("experiments/results/gt_blind_expert_v1/result.json"))["cells"]
def agree(c):
    if c["truth"] == "none": return c["label"] == "none"
    return (c["label"] == "same" and c["field"] == c["truth_field"] and c["diff"] == c["truth_diff"]
            and isinstance(c["scale"], float) and abs(c["scale"] - c["truth_scale"]) <= 0.02 * abs(c["truth_scale"]))
scored = [c for c in cells if c["truth"] in ("same", "none")]
a, b = [c["truth"] for c in cells], [c["label"] for c in cells]; n = len(a)
po = sum(x == y for x, y in zip(a, b)) / n; pe = sum(a.count(k) / n * b.count(k) / n for k in ("same", "kind", "none"))
print(sum(map(agree, scored)), "of", len(scored), "kappa", round((po - pe) / (1 - pe), 3))
EOF
```

The synthetic-schema rows are rescored from saved replays. A synthetic group succeeds when the mapped estimator's
error, divided by its error under the true mapping, has a median of at most 1.2 over the group's evaluation
calls. The per-call ratios come from replaying the challenge calls on a server (`scripts/arb/obsschema_v1.py eval`,
`scripts/arb/obsschema_rt_offline_v1.py eval`, with `schaferct_public.onnx` as the estimator). The package holds
their outputs, `eval_*.json`, which also record the mapping each arm was replayed with. The offline rescoring
reparses every saved answer, checks that it yields exactly those mappings, and rebuilds groups and verdicts from the
saved ratios; replaying new answers needs the challenge calls. The masking study is split the same way: its runs,
`realtel_mask_offline_v2/M*.json`, hold the per-call errors.

## (b) Rerun the designer calls

**Hosted model.** Every call sends one user message to `deepseek-flash` with temperature 0 and at most 48 000 output
tokens (the limit each caller passes to `ask` in `scripts/coldstart/coldstart_rule_v1.py`); the key is read from `~/.config/deepseek/api_key`. The
prompts are rebuilt from the field transcriptions and the source files, never read from the records, and each script
except `scripts/realtel_e2e/closure_v1.py` checks the template hash before sending (realtel template: SHA-256 prefix `d2467ef5dc35`).

| Test | Command |
|---|---|
| Synthetic schemas (32 groups, real and masked names) | `scripts/coldstart/obsschema_llm_v1.py test` |
| Seven specifications; names hidden; counterfactual | `scripts/coldstart/realtel_adapter_v1.py llm test`; `realtel_namehide_v1.py llm`; `realtel_cfdoc_v1.py llm` |
| 12 stacks; names hidden; two repeats | `scripts/coldstart/realtel_scale_v1.py llm`; `realtel_scale_namehide_v1.py llm`; `realtel_repeat_v1.py llm` |
| Generic and two-step LLM matching | `scripts/coldstart/llm_schema_match_v1.py llm`; `llm_twostep_match_v1.py llm` |
| Browser derivation function | `scripts/realtel_e2e/closure_v1.py prompt`, `design 1`, `devcheck 1`, `freeze 1` |

The record file of each test is also its cache: a call already in it is skipped. Move the released file aside first,
then run the matching judge from part (a).

Cost guard: the scripts except `closure_v1.py`, which has no guard, send only when `ok_to_send()` in `scripts/coldstart/api_runner_v1.py` returns True, which it
does not during the provider's weekday peak-price hours (`is_peak`, 01:00 to 04:00 and 06:00 to 10:00 UTC, with a
20-minute margin), and they stop when the account balance is below `MIN_BALANCE`. To send at any time, edit
`ok_to_send()` to return True, or lower `MIN_BALANCE`.

Expect different answers. The hosted model answered in reasoning mode, and repeated calls with the same prompt
differed: two repeats on one day agreed on 95% of feature cells, and with the first call five days earlier on 92%
(realtel-repeat-v1). `deepseek-flash` is an alias whose weights may have changed since our calls (1 to 8 October
2026); note the date and the `model` field the API returns.

**Open models.** The prompts are saved: `realtel_adapter_v1/prompts_open.jsonl` (7 specifications),
`realtel_scale_v1/prompts_scale.jsonl` (12 stacks), `obsschema_rt_openreason_v1/prompts.jsonl` (40 newer synthetic
groups), `openreason_v1/prompts.jsonl` (the 32 older groups, ids `obsschema|...`) and
`realtel_designer_scale_v1/prompts_designer_scale.jsonl` (small models). With vLLM 0.6.6 on two GPUs:

```bash
python3 scripts/arb/vllm_generate_v2.py MODEL_DIR PROMPTS.jsonl OUT.jsonl --tp 2 --max-len 40960 --max-new 32768 \
  --temp 0.6 --top-p 0.95 --seed 20261002        # R1 distillations; samples 2 and 3 used seeds 20261003 and 20261004
python3 scripts/arb/vllm_generate_v2.py MODEL_DIR PROMPTS.jsonl OUT.jsonl --tp 2 --max-len 16384 --max-new 8192 \
  --temp 0.6 --top-p 0.95 --max-seqs 8           # Qwen1.5-0.5B-Chat and Qwen2.5-7B-Instruct
python3 scripts/arb/vllm_generate_v1.py MODEL_DIR PROMPTS.jsonl OUT.jsonl --tp 2 --max-len 8192 --max-new 4096   # Qwen2.5-32B, greedy
```

`models.json` gives the Hugging Face repository of every model and the file each run wrote. Put the output in place of
the released file of the same name and run the scorer from part (a). For synthetic groups the new mappings must
first be replayed on the challenge calls. Even with the same seed, outputs can change with the GPU, the batch and the
vLLM version, which is why the 14B and 32B readings in the paper are means over three seeds.

## (c) What is not included

- The hosted model's full answers. Its records keep the parsed mapping, the last 300 or 400 characters of the answer
  and the token usage, not the reasoning text. The one exception is the derivation function of the closure test,
  whose full answer is `realtel_closure_v1/design_r1.raw.json`. Open-model answers are complete, reasoning included.
- Documentation pages not cleared for redistribution: Agora, Daily, the mediasoup.org site, pkg.go.dev, the Twilio
  documentation pages and the Teams Call Quality Dashboard page (license not verified), and the RFC Editor errata
  page. `data/real_telemetry_specs_raw_NOTICE.md` lists their URLs and archived copies, and the transcriptions quote
  the text the ground truth relies on. Every other page and source file we read is in
  `data/real_telemetry_specs_v*/raw/`.
- The engineer's filled sheet. Its cells are in `gt_blind_expert_v1/result.json`; `gt_blind_compare_v1.py` cannot be
  rerun without it. The engineer is not named anywhere in the package.
- The records of the two LLM passes that checked the ground truth before any method ran.
- The challenge calls and the model weights, which the replays and the generation need; their outputs are included.
- Per-run closed-loop logs. The closed-loop judges audit them, so those judges cannot be rerun; the per-run results
  (none for obsschema-closedloop-nl-v1, which ships only `result_v1.json`) are included, and for obsschema-closedloop-v2
  also the deployed mappings (`maps.json`) and the job lists.
