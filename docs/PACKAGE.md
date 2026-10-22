# Package reference

Details that the README leaves out: the full claims table, hardware and time per level, the level-1 commands run by
hand, what counts as reproduced, the directory layout, path placeholders, what the package does not include, the
registry, and checksums.

## Claims, level by level

Level 1 regenerates the tables and figures from the result files in the package. Level 2 recomputes the numbers,
their means, intervals and verdicts, from per-call, per-run or per-answer data. Level 3 reruns the experiments.
"Yes": possible with this package alone. "External": needs data, hardware or a service from outside the package.
"No": not possible from the package, for the reason given.

| Claim (paper) | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| Offline accuracy: the deployed estimator reaches macro MSE 5.795, 16.3% below LLM4Band; the supervised MLP is lowest (Table I, Section V-B, Table S4) | Yes | Yes, from per-step exports | External: re-evaluate the released C-H checkpoints and the MLP on the 870 calls rebuilt from the public challenge data, or retrain on a GPU. No for two rows: LLM4Band (conference checkpoint not included) and the one-token variant (its checkpoint is built on Meta Llama 3 code and not distributed, `NOTICE`); both are recomputed from their per-step exports only |
| Anchor, reward and encoder ablations; reward-weight sweep (Sections V-B, V-C, S4, S6; Fig. S1) | Yes | Yes | External: retrain the four ablation cells C-H, C-B, M-H and M-B (conference or multi-scale encoder, HCQ or conference reward) and the anchor and λ variants from the public data on a GPU |
| Two LLM positions (Table II, Section V-D, Table S3) | Yes | Yes: per-step contrasts from per-call results, designer rows by rescoring saved answers | Per step: No (estimator files and checkpoints of the LLM variants are not included). Designer: External (an API key for the hosted model, or two GPUs for the open models; new synthetic-schema mappings must be replayed on the challenge calls) |
| Cost per decision (Table III) | Yes | Yes: parameter count and FLOPs of the deployed checkpoint; designer wall time and cost from the call records | External: the latency script on your hardware; latencies depend on the machine. The LLM arms run with random weights of the same architecture and need Qwen1.5-0.5B's `config.json` |
| Designer: on 12 held-out client stacks, balanced accuracy 0.92 against 0.56 for the best non-LLM matcher, and the other designer tests (Table IV, Fig. 3, Sections V-E, S8) | Yes | Yes for every offline, replayed and packet-capture number, for Fig. 3(c) and, from per-run rows, for the three 720p closed-loop designer rows of Table IV; the multi-scale variant row only from its recorded reading (no per-run rows) | External: hosted calls (API key; new answers will differ, and the hosted model's full answers were not stored), open models (two GPUs, vLLM), captures of real software (Chrome, iperf3, GStreamer), the testbed for closed-loop rows |
| Closed loop: non-inferior to the Python GCC at 720p, low-capacity, cellular, loss and high-bandwidth results (Table V, Fig. 4, Sections V-F, S6, S7) | Yes | Yes, from per-run rows; the batch judges themselves read per-run logs, which are not shipped | External: an AlphaRTC testbed (the Dockerfile is a draft we have not built), videos and two trace sets rebuilt from their sources; the LLM4Band reference needs the conference checkpoint (not included). No for the envelope batches of Section S7 (their run script and LLM-variant checkpoint are not included) |
| Collector corrections (Section III-E, first paragraph of Section V-F, Table S1) | Table S1 is typeset by hand from the registry entries it cites | Partly, from replay results, run lists and per-step exports (`docs/RESULTS_INDEX.md`, Sections III-E and V-F, Table S1); otherwise recorded readings only (`experiments/registry.jsonl`) | No: the replayed receiver logs and the run scripts of those batches are not shipped |

## Requirements and expected time

Times are approximate and were measured on our machines: a laptop with a Core i9-13900H (20 threads, 30 GB RAM, RTX
4080 Laptop GPU) and GPU servers with V100S-PCIE-32GB cards. The package itself takes about 333 MB.

| Level, experiment family | Hardware | Disk | Expected time |
|---|---|---|---|
| 1, every table and figure | laptop CPU; TeX Live | the package | under 10 s per script |
| 2, offline, designer and closed-loop recomputation | laptop CPU | the package | under 45 s per command; the slowest, `steady_state_qoe_v1.py run`, about 43 s (`judge_nl2x2_v1.py dry` about 38 s) |
| 3, re-evaluate the released checkpoints | CPU | 8.1 GB download, about 72 GB unpacked | a few minutes on a CPU (`docs/OFFLINE.md`) |
| 3, retrain C-H and its variants | a GPU (we ran two runs per V100S; 0.4 to 0.75 GiB of GPU memory per run) and about 20 GB of host memory per run | the unpacked data and an 8.5 GB training pickle | 50,000 updates per run; time per run not recorded for these cells. For scale, Table S2: the LLM variants needed 1.104 s and 1.45 s per update (15.3 and 20.1 GPU hours per run) |
| 3, supervised MLP and Decision Transformer baselines | a GPU | as above | MLP: 210.7 s for three seeds in total; Decision Transformer: about 7060 s per seed (registry) |
| 3, hosted designer calls | an API key | none | median 37.5 s per call (15.9 to 61.0 s) on the seven specifications; median 58.3 s per stack with six calls in parallel on the 12 stacks; about 0.013 to 0.017 USD per call at the provider's peak price. A test has 21 (seven specifications) or 36 (12 stacks) calls |
| 3, open designer models | two 32 GB GPUs, vLLM 0.6.6 | model weights | the 32B distillation (4-bit) handled 21 clients in 5 min 8 s at concurrency 8 |
| 3, closed loop | Linux x86-64 with Docker; arms that run an LLM on the receiver's CPU need about 4 cores and 3 GB per container pair | the job lists require 8 GB free on the results disk and 1.5 GB on the scoring scratch disk | a 720p run takes about 2.5 min (median of the recorded start and end times); the 720p batches of 48 to 108 runs took 1.1 to 4.4 h on one or two container pairs |

## Level 1 by hand

Environment: Python 3.13.13 with the pinned versions in `requirements-level1.txt`
(`pip install -r requirements-level1.txt`), with which levels 1 and 2 were tested; torch and onnxruntime are needed
only for the commands named in the file. TeX Live with `pdflatex` on `PATH` and the packages `helvet`, `sansmath` and
TikZ: Figs. 1 and 2 are TikZ, and Fig. 3 is typeset through matplotlib's PGF backend. With other matplotlib versions
Fig. 3 may fail (`hatchcolor` needs 3.11) and the other figures can differ in a few pixels; the numbers do not change.
Two helper scripts that the levels do not need use one more package each, versions not recorded: `openpyxl`
(`scripts/paper/gt_blind_compare_v1.py`, which reads the engineer's label sheet, not released) and `beautifulsoup4`
(`data/real_telemetry_specs_v2/build.py`, which checks quotes against the documentation snapshots). Training used Python 3.10.18 with the versions in
`docs/requirements-train.txt`.

`python3 reproduce/verify_level1.py` runs every level-1 command in a temporary copy of the package (it sets the path
placeholders there), compares each output with the reference copy under `expected/` (text files byte for byte, PDFs
pixel by pixel) and prints a match table. With the pinned versions every output is identical; the script exits with 0
when that is so, or when an output was skipped for a missing tool.

To run the commands yourself, first set the placeholders through which several scripts locate the package. Set them
once, from the package root:

```bash
grep -rlE "/path/to/(llm4bandpp|testbed/results)" scripts papers | xargs sed -i \
  -e "s#/path/to/testbed/results#$PWD/external/testbed/results#g" -e "s#/path/to/llm4bandpp#$PWD#g"
```

Then:

```bash
python3 scripts/paper/make_tables_v2.py                   # Tables I to V
python3 papers/revision-v2/supplement/make_supp_tables.py # Tables S3 and S4, the per-stack table, the prompt of Fig. S2
python3 scripts/paper/make_fig_lambda_supp_v2.py          # Fig. S1
FIG_OUT=$PWD/papers/revision-v2/figs/fig_designer_three.pdf python3 scripts/paper/make_fig_designer_v6.py   # Fig. 3
python3 scripts/paper/make_fig_closedloop_v1.py           # Fig. 4
python3 scripts/paper/make_fig1_collector_grid_v1.py --palette greys --lighten 0.4 \
  --out papers/revision-v2/figs/src/collector_grid_greys_light.tex   # the observation grid inside Fig. 1
(cd papers/revision-v2/figs/src && pdflatex fig_llm_position.tex && pdflatex fig_envelope.tex)   # Figs. 1 and 2
```

| Output (under `papers/revision-v2/`) | Paper item |
|---|---|
| `tables/table_offline.tex` | Table I |
| `tables/table_position.tex` | Table II |
| `tables/table_cost.tex` | Table III |
| `tables/table_designer.tex` | Table IV |
| `tables/table_closedloop_v2.tex` | Table V |
| `tables/table_closedloop.tex` | an alternative layout of the closed-loop readings, not in the paper; its after-30-s, SSIM and freeze columns back Section V-F |
| `supplement/generated/tab_variants.tex` | Table S3 |
| `supplement/generated/tab_eplus.tex` | Table S4 |
| `supplement/generated/prompt_template.txt` | the prompt of Fig. S2 |
| `supplement/generated/tab_designer_src.tex` | the per-stack table that Section S8 says is released with the code |
| `supplement/figS_lambda.pdf` (data in `figS_lambda.json`) | Fig. S1 |
| `figs/src/fig_llm_position.pdf` | Fig. 1 |
| `figs/src/collector_grid_greys_light.tex` | the observation grid inside Fig. 1; the regenerated file compares equal to the shipped one |
| `figs/src/fig_envelope.pdf` | Fig. 2 |
| `figs/fig_designer_three.pdf` | Fig. 3 |
| `figs/fig_closedloop_dynamics.pdf` | Fig. 4 |
| `figs/fig_closedloop_forest.pdf` | the Table V readings drawn as a forest plot; not in the paper |

Tables S1 and S2 are typeset by hand from the registry entries they cite.

Two scripts print messages that do not match the paper:

- `make_tables_v2.py` prints messages from an older numbering: "Table II generated" refers to Table I
  (`table_offline.tex`), and "Table 6 generated; switcher FLOPs ..." to Table III (`table_cost.tex`).
- `make_fig_closedloop_v1.py` prints for Fig. 4(a) a ramp-up difference of 18.41 (registered 18.79) and a steady
  difference of −0.76 (registered −0.16). The figure averages 2 s bins with equal weight up to 120 s and fills the 1.0%
  of empty bins by interpolation, whereas the registered values of closedloop-steady-qoe-v1, which the paper quotes,
  average all decoded frames of each run within each segment; the script checks that the two agree within 1 VMAF.

## How to tell that a result was reproduced

- **Level 1.** `python3 reproduce/verify_level1.py` prints a match table against `expected/`.
- **Level 2.** `bash reproduce/run_level2.sh` runs the level-2 commands and prints a match table against the recorded
  result files and registry values. The level-2 scripts `finalize_aggregator_mamba_control_v1_offline_v1.py`,
  `finalize_enc_hcq_2x2_v1_offline_v1.py`, `finalize_scharch_v1_offline_v1.py`, `obsschema_rt_openreason_judge_offline_v1.py`,
  `perstep_position_ci_v1.py`, `mask_offline_local_v1.py` and `make_designer_per_stack_v1.py` also compare by themselves and exit with status 1 on
  a mismatch.
- **Level 3, offline.** A re-evaluated checkpoint matches when `compare_ch_equiv_v1.py` passes (every call present,
  per-call MSE within 1e-3 relative, macro MSE within 1e-4). The training pickle is rebuilt exactly, but training on
  GPUs is not bitwise reproducible: a retrained recipe reproduces when its three-seed mean lies within the seed spread
  reported in `docs/OFFLINE.md`, "What is not bitwise reproducible".
- **Level 3, designer.** Rescoring saved answers is deterministic and gives the recorded files byte for byte, except
  one count in one judge file (`docs/DESIGNER.md`, "12 stacks, one count"). New calls may differ: three hosted calls
  with the same prompt agreed on 92% of feature cells, and open-model outputs change with the GPU, the batch and the
  vLLM version.
- **Level 3, closed loop.** A rerun reproduces a reading when the difference has the same sign and the same verdict
  against the registered margin (−6 VMAF for non-inferiority, 5.27 utility points for level arms). Absolute VMAF and
  utility depend on the host.

Judge commands rewrite their result file in place and append to `experiments/registry_local.jsonl`; run them on a copy
of the package, or under git, to compare.

## Layout

| Directory | Contents |
|---|---|
| `scripts/paper/` | table and figure generators |
| `scripts/coldstart/` | designer calls (hosted and open models), generic and two-step LLM schema matching, their judges |
| `scripts/realtel_e2e/` | end-to-end runs on real client telemetry: capture, the browser derivation function, value rules |
| `scripts/arb/` | offline analyses: Table I rows, synthetic-schema replays, HCQ term correlation, stronger baselines, vLLM generation |
| `scripts/encoder/` | the C-H recipe, the encoder and reward ablation, the anchor ablation, the λ sweep, the training pickle |
| `scripts/baselines/` | supervised MLP and Decision Transformer baselines |
| `scripts/alphartc/` | testbed side: estimator arms, run scripts, collectors, envelopes, closed-loop batch scripts; the deployed checkpoint is `scripts/alphartc/deploy/ch_estimator_v1/ckpt/ch.pt` |
| `experiments/results/` | result files read by the generators and judges, including the designer answers and the supervised MLP checkpoints |
| `experiments/registry.jsonl` | numeric results (data events) of the registered experiments |
| `external/testbed/results/` | testbed-side files of the closed-loop batches: sequence lists, per-sequence video-rate ceilings, job lists, weight checks and, for some batches, per-frame quality and decoded-frame times |
| `external/alphartc/` | files to add to the AlphaRTC app directory, and the media recipes and checksums |
| `data/` | field transcriptions of the real telemetry sources (ground truth), documentation snapshots, the interface specification |
| `registry/` | English summary of the registered experiments and their pre-registration notes |
| `papers/` | figure sources and the supplement table generator; the level-1 commands write their outputs here |
| `figures_and_tables/` | one folder per figure and table of the paper and supplement: a copy of the item, its source or plotted data, and a README naming the generator and inputs; Figs. 3 and 4 with standalone plotting scripts (`scripts/paper/export_figure_data_v1.py` writes their CSV files) |
| `docs/` | this reference, the reproduction guides, the results index, the glossary, the training requirements and the testbed Dockerfile draft |
| `docs/figures/` | PNG renderings of Figs. 1, 3 and 4 for the README; the reference PDFs are in `expected/figs/` |
| `reproduce/` | checks for levels 1 and 2 (`verify_level1.py`, `run_level2.sh`) |
| `expected/` | reference copies of the level-1 outputs, taken from the paper sources |

## Path placeholders

Machine-specific paths were replaced by placeholders. Scripts that touch the testbed or a GPU server need them set.

| Placeholder | Stands for |
|---|---|
| `/path/to/llm4bandpp` | the root of this package |
| `/path/to/testbed/results` | closed-loop results; a copy is in `external/testbed/results/` |
| `/path/to/testbed` | working directory of the AlphaRTC testbed |
| `/path/to/alphartc` | AlphaRTC build tree |
| `/path/to/server` | working directory on a GPU server |
| `/path/to/llm4band_conference` | the conference version (https://github.com/WzjCoder/LLM4Band) |
| `/path/to/challenge` | the MMSys 2024 challenge data used for training |
| `/path/to/models`, `/path/to/tools`, `/path/to/storage` | model weights, external tools, bulk storage |
| `gpu-server-1`, `gpu-server-2`, `laptop` | host aliases |

Hosted-model calls read the API key from `~/.config/deepseek/api_key`.

## Not included

- The testbed container image and the AlphaRTC binaries (`docs/TESTBED.md` explains how to build them).
- The challenge corpus, the Qwen1.5-0.5B weights, and the conference version's code and checkpoint; get them from
  their sources.
- Checkpoints of models built on the Meta Llama 3 Transformer code (the multi-scale variants, with or without the LLM,
  and the Mamba arm), and the estimator files of the LLM variants; see `NOTICE`.
- Video sequences (recipes and checksums are given instead) and the UCC 4G and Norwegian 3G trace windows (rebuild them
  from the public traces, `docs/TESTBED.md`, section 5).
- Documentation pages under proprietary terms (links in `data/real_telemetry_specs_raw_NOTICE.md`).
- Full answers of the hosted model, which were not stored; its records keep the parsed mapping, the end of each answer
  and the token usage (`docs/DESIGNER.md`). Answers of the open models are complete.
- Per-run testbed logs and decoded video, except the per-frame quality and timing files that the figures and the
  recomputed numbers need.

## Registry and verdict letters

Every confirmatory test in the paper was registered before it ran.

- `registry/registry_summary.md` and `.jsonl`: question, criterion, tier, verdicts and post hoc revisions of the
  experiments the paper draws on. A revision never replaces the original verdict; both are listed. Void and
  inconclusive runs are kept.
- `registry/preregistrations/`: the pre-registration notes those criteria refer to, with their motivation sections
  removed.
- `experiments/registry.jsonl`: the numeric results (data events) of the same experiments.
- `scripts/exp.py`: a minimal logger with the interface of our registry tool. Judge scripts call it, and it appends
  each call to `experiments/registry_local.jsonl`.

Result files and the registry use verdict strings (holds, direction only, does not hold, inconclusive, void,
exploratory); `docs/RESULTS_INDEX.md` abbreviates them as verdict letters (R, D, N, P, "P, N" and –). `docs/GLOSSARY.md`
defines both and maps one to the other. The paper's tables print no letters; their footnotes mark revised criteria.

## Checksums and language

All comments, docstrings, messages and data fields are in English, normalized through one translation table so that
code and data use the same strings. The generated tables are unchanged, but some files changed by a few bytes. Scripts
that check the SHA-256 of a file they load carry the hash of the released file; hashes quoted in run logs and in the
registry refer to the files before normalization, and `RELEASE_HASHES.tsv` maps each of them to the released file's
hash. Model answers are stored as returned, except for one short phrase inside a reasoning trace of the open 7B model
(`experiments/results/realtel_scale_v1/out_open_r1_7b_sd20261004.jsonl`), which was normalized like the rest; the
answer itself is unchanged.
