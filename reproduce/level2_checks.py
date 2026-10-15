#!/usr/bin/env python3
"""Level 2 check: rerun every recomputation command of docs/OFFLINE.md, docs/DESIGNER.md, docs/TESTBED.md and
docs/RESULTS_INDEX.md and check that each one reproduces what the docs say. Called by reproduce/run_level2.sh.

Each command runs in a fresh temporary copy of the package with the path placeholders set, so no command sees
another one's output and the package itself is not touched. A command passes when it exits with status 0 and
  - every result file it rewrites is byte-identical to the released one (three documented exceptions, below), and it
    changes no other released file;
  - the numbers it prints match those quoted in the docs, up to the rounding of the quote; a quoted 4.6 accepts a
    printed 4.58 but not 4.66;
  - scripts that compare themselves with the recorded result files report a match.
Code blocks quoted in the docs (the Table V, low-capacity, lambda and parameter snippets and the engineer agreement)
are read from the docs and run as they stand there.

Documented exceptions: main_table_unified_v1/result.json keeps only the seven rows whose inputs ship; the rewritten
offline_trivial_baselines_v1/result.json holds the absolute path of its input in "source"; realtel_scale_v1.py judge
writes sources_all_correct_all_pres 8 where the released judge.json says 9 and leaves LiveKit out of
per_source_all_correct (docs/DESIGNER.md). Commands that need onnxruntime or torch are skipped when it is missing.

Usage: reproduce/run_level2.sh [--list] [--only NAME[,NAME...]] [--workdir DIR] [--keep] [--timeout SECONDS]
"""
import argparse, ast, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, textwrap, time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_level1 as V1   # noqa: E402  (placeholders, package copies, table printing)

ROOT = V1.ROOT
R = "experiments/results/"
NUM = r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
LOCAL_LOG = "experiments/registry_local.jsonl"   # written by the stand-in scripts/exp.py, not part of the release


# ---------------------------------------------------------------------------------------------------------------------
# Check definitions

class Num:
    """Numbers in the command's output: regex with {N} for each number, the quoted values (None: not checked)."""
    def __init__(self, label, rx, quoted=()):
        self.label, self.rx, self.quoted = label, re.compile(rx.replace("{N}", NUM), re.M), list(quoted)


class Val:
    """A value in a JSON file of the copy after the command, as quoted in the docs."""
    def __init__(self, label, rel, path, quoted):
        self.label, self.rel, self.path, self.quoted = label, rel, path, quoted


class Snippet:
    """A fenced code block of a doc (python or bash), found by a line it contains, or an inline `python3 -c ...`."""
    def __init__(self, doc, marker, inline=False):
        self.doc, self.marker, self.inline = doc, marker, inline


class Check:
    def __init__(self, name, doc, cmd, reproduces, files=(), nums=(), vals=(), self_report=None, needs=(), refs=(),
                 stdout_json=None, note=None):
        self.name, self.doc, self.cmd, self.reproduces = name, doc, cmd, reproduces
        self.files = dict(files)          # rewritten file -> comparison ("bytes" or a function(old, new) -> problems)
        self.nums, self.vals, self.self_report, self.needs = list(nums), list(vals), self_report, list(needs)
        self.refs = list(refs)            # (output in the copy, reference under expected/) compared byte for byte
        self.stdout_json, self.note = stdout_json, note


def json_diff(a, b, path=""):
    """Paths where two JSON values differ."""
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool)):
        return [f"{path or '/'}: {a!r:.40} vs {b!r:.40}"]
    if isinstance(a, dict):
        out = [f"{path}/{k}: missing" for k in a if k not in b] + [f"{path}/{k}: added" for k in b if k not in a]
        for k in a:
            if k in b: out += json_diff(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list):
        if len(a) != len(b): return [f"{path}: {len(a)} items vs {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in json_diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path or '/'}: {a!r:.40} vs {b!r:.40}"]


def main_table_rows(old, new):
    """main_table_unified_v1/result.json: only the rows whose inputs ship, each equal to the released row."""
    p = []
    for k in ("rows", "improvement_over_pioneer_pct"):
        o, n = old.get(k, {}), new.get(k, {})
        extra = sorted(set(n) - set(o))
        if extra: p.append(f"/{k}: rows not in the released file: {extra}")
        p += json_diff({r: o[r] for r in n if r in o}, {r: n[r] for r in n if r in o}, f"/{k}")
    if len(new.get("rows", {})) != 7: p.append(f"/rows: {len(new.get('rows', {}))} rows, the docs say 7")
    p += json_diff({k: v for k, v in old.items() if k not in ("rows", "improvement_over_pioneer_pct")},
                   {k: v for k, v in new.items() if k not in ("rows", "improvement_over_pioneer_pct")})
    return p


def echo_source(old, new):
    """offline_trivial_baselines_v1/result.json: equal apart from the absolute input path in "source"."""
    p = json_diff({k: v for k, v in old.items() if k != "source"}, {k: v for k, v in new.items() if k != "source"})
    if not str(new.get("source", "")).endswith(R + "arb_perstep_dump_v1/perstep.npz"): p.append(f"/source: {new.get('source')!r}")
    return p


def scale_judge(old, new):
    """realtel_scale_v1/judge.json: 8 instead of 9 stacks correct in all orders, LiveKit left out; the rest equal."""
    p = []
    if (old.get("sources_all_correct_all_pres"), new.get("sources_all_correct_all_pres")) != (9, 8):
        p.append(f"/sources_all_correct_all_pres: {old.get('sources_all_correct_all_pres')} -> {new.get('sources_all_correct_all_pres')}, the docs say 9 -> 8")
    po, pn = dict(old.get("per_source_all_correct", {})), new.get("per_source_all_correct", {})
    if "LiveKit protocol" in pn: p.append("/per_source_all_correct: still lists LiveKit protocol")
    po.pop("LiveKit protocol", None)
    p += json_diff(po, pn, "/per_source_all_correct")
    skip = ("sources_all_correct_all_pres", "per_source_all_correct")
    p += json_diff({k: v for k, v in old.items() if k not in skip}, {k: v for k, v in new.items() if k not in skip})
    return p


def checks():
    O, D, T, X = "docs/OFFLINE.md", "docs/DESIGNER.md", "docs/TESTBED.md", "docs/RESULTS_INDEX.md"
    B = "bytes"
    return [
        # ------------------------------------------------------------------ docs/OFFLINE.md
        Check("main-table", O, "python3 scripts/arb/main_table_unified_v1.py", "Table I rows from per-step predictions, Table S4",
              files={R + "main_table_unified_v1/result.json": main_table_rows},
              nums=[Num("MLP 2.345", r"^MLP_seed0\s.*\|\s+{N}$", ["2.345"]),
                    Num("one-token variant 6.743", r"^LLM4band\+\+ \(Qwen\)\s.*\|\s+{N}$", ["6.743"]),
                    Num("Schaferct-R 7.074", r"^Schaferct\(retrained\)\s.*\|\s+{N}$", ["7.074"])],
              note="result.json keeps only the 7 rows whose inputs ship (docs/OFFLINE.md)"),
        Check("echo-row", O, "python3 scripts/arb/offline_echo_row_v1.py", "Table I, receiving-rate echo",
              files={R + "offline_trivial_baselines_v1/result.json": echo_source},
              nums=[Num("echo 14.719, Low BW 0.13", r"^ReceiveRateEcho \{'870': \{'High BW': {N}, 'Low BW': {N}, 'Fluctuating': {N}, 'macro': {N}\}", [None, "0.13", None, "14.719"])],
              note='"source" holds the absolute input path (docs/OFFLINE.md)'),
        Check("table1-deployed", O, "python3 scripts/paper/table1_ch_rows_v1.py", "Table I deployed row, Sec. V-B paired intervals",
              files={R + "table1_ch_paired_v1/result.json": B},
              nums=[Num("16.3% [13.4, 19.4] below LLM4Band", r"^LLM4Band conference version online weights \(Qwen\) \{'870': \({N}, \[{N}, {N}\]\)", ["16.3", "13.4", "19.4"]),
                    Num("14.1% below the one-token variant", r"^LLM4band\+\+ \(Qwen\) \{'870': \({N},", ["14.1"]),
                    Num("18.1% below Schaferct-R", r"^Schaferct\(retrained\) \{'870': \({N},", ["18.1"]),
                    Num("seeds 5.87, 5.795 (deployed), 5.79", r"'CHs0': \{'870': {N}, '712': {N}\}, 'CHs1': \{'870': {N}, '712': {N}\}, 'CHs2': \{'870': {N},", ["5.87", None, "5.795", None, "5.79"])]),
        Check("perstep-ci", O, "python3 scripts/arb/perstep_position_ci_v1.py", "Table II per-step row, Secs. V-D and S4",
              self_report=r"^all three intervals reproduced$",
              nums=[Num("full training +2.2% [-4.0, +8.4]", r"both trained in full \(Table II\): .*change in macro MSE {N}% \[{N}, {N}\]", ["+2.2", "-4.0", "+8.4"]),
                    Num("LoRA vs no LLM +0.1% [-4.8, +5.0]", r"with LoRA vs no LLM: .*change in macro MSE {N}% \[{N}, {N}\]", ["+0.1", "-4.8", "+5.0"]),
                    Num("LoRA vs random init. +2.7% [-0.2, +5.5]", r"with LoRA vs random init\. trained in full: .*change in macro MSE {N}% \[{N}, {N}\]", ["+2.7", "-0.2", "+5.5"])]),
        Check("encoder-reward-2x2", O, "python3 scripts/encoder/nl2x2_v1/judge_nl2x2_v1.py dry", "Sec. V-C ablation, Table S3 2x2 cells",
              files={R + "nl_2x2_v1/result_v1.json": B},
              nums=[Num("8.1% (6.4 to 10.2)", r"^holds Primary endpoint \(C-B - M-H\)/C-B macro MSE improvement {N}%, 90% interval \[{N}, {N}\]", ["8.1", "6.4", "10.2"]),
                    Num("5.76 against 6.27, five seeds", r"Two cells five seeds macro C-B {N}, M-H {N}", ["6.27", "5.76"]),
                    Num("HCQ on Low BW 5.0% (2.5 to 8.0)", r"HCQ main effect low-bandwidth MSE improvement {N}%, 90% interval \[{N}, {N}\]", ["5.0", "2.5", "8.0"]),
                    Num("HCQ main effect 7.7% (6.5 to 9.1)", r"HCQ main effect macro {N}% \[{N}, {N}\]", ["7.7", "6.5", "9.1"]),
                    Num("encoder +0.5% (-1.6 to +2.3), printed as improvement", r"encoder main effect macro {N}% \[{N}, {N}\]", ["-0.5", "-2.3", "1.6"]),
                    Num("encoder Low BW +11.8% (4.1 to 23.5), printed as improvement", r"low bandwidth {N}% \[{N}, {N}\]; HCQ main effect", ["-11.8", "-23.5", "-4.1"]),
                    Num("cells 6.25, 5.82, 6.33, 5.80", r'four cells three seeds macro \{"CB": {N}, "CH": {N}, "MB": {N}, "MH": {N}\}', ["6.25", "5.82", "6.33", "5.80"]),
                    Num("Low BW 1.06, 1.02, 1.20, 1.13", r'Four cells three seeds low bandwidth \{"CB": {N}, "CH": {N}, "MB": {N}, "MH": {N}\}', ["1.06", "1.02", "1.20", "1.13"])]),
        Check("anchor", O, "python3 scripts/encoder/anchor_ablation_v1.py summarize", "Sec. V-B capacity anchor, Sec. S6",
              files={R + "anchor_ablation_v1/summary.json": B},
              nums=[Num("with anchor 5.819, Low BW e+ 0.67", r"^CH anchor macro {N} .* low bandwidth e\+ {N}", ["5.819", "0.67"]),
                    Num("without anchor 6.386, Low BW e+ 0.50", r"^CH no anchor macro {N} .* low bandwidth e\+ {N}", ["6.386", "0.50"]),
                    Num("lambda 0: 6.252 and 6.659 without anchor", r"^CB anchor macro {N}[\s\S]*^CB no anchor macro {N}", ["6.252", "6.659"])]),
        Check("lambda-sweep", O, "python3 scripts/encoder/ch_lambda_sweep_v1.py summarize", "Sec. V-B, Fig. S1 data (HCQ weight)",
              files={R + "ch_lambda_sweep_v1/summary.json": B},
              nums=[Num("6.25 at 0, Low BW e+ 0.59", r"^λ 0\.0 macro {N} .* low bandwidth e\+ {N}", ["6.25", "0.59"]),
                    Num("5.82 at 0.4", r"^λ 0\.4 macro {N}", ["5.82"]),
                    Num("5.45 at 0.8, Low BW e+ 0.78", r"^λ 0\.8 macro {N} .* low bandwidth e\+ {N}", ["5.45", "0.78"]),
                    Num("5.48 at 1.0", r"^λ 1\.0 macro {N}", ["5.48"])]),
        Check("schaferct-recipe", O, "python3 scripts/encoder/finalize_scharch_v1_offline_v1.py", "Sec. V-B, Schaferct's network with our recipe",
              self_report=r"^matches the recorded summary\.json$",
              nums=[Num("5.83", r"Schaferct network with our recipe {N}", ["5.83"])]),
        Check("mamba", O, "python3 scripts/finalize_aggregator_mamba_control_v1_offline_v1.py", "Sec. S4, Mamba aggregator",
              self_report=r"^matches the recorded result_main\.json$",
              nums=[Num("5.674 against 5.797 (-2.1%), [-0.180, -0.058], threshold 0.152", r"Mamba {N} vs Transformer {N} \({N}%\), difference {N}, 95% interval \[{N}, {N}\], threshold {N}", ["5.674", "5.797", "-2.1", None, "-0.180", "-0.058", "0.152"]),
                    Num("e+ 0.930 against 0.869", r"macro e\+: Mamba {N} vs Transformer {N}", ["0.930", "0.869"])]),
        Check("corrected-encoder", O, "python3 scripts/finalize_enc_hcq_2x2_v1_offline_v1.py", "Sec. S2, corrected-encoder ablation",
              self_report=r"^matches the recorded result\.json$",
              nums=[Num("-6.4% (4.6 to 8.5)", r"claim 1, .*: {N}% lower, 90% interval \[{N}, {N}\]", ["6.4", "4.6", "8.5"]),
                    Num("Low BW -27.4% (18.7 to 36.5)", r"claim 2, .*: {N}% lower, 90% interval \[{N}, {N}\]", ["27.4", "18.7", "36.5"]),
                    Num("HCQ -4.7%, encoder -0.2%", r"reward {N}%, encoder {N}%", ["4.7", "0.2"])]),
        Check("flops", X, "python3 scripts/paper/flops_ch_v1.py", "Table III, parameters and FLOPs", needs=["torch"],
              files={R + "client_hw_ch_v1/flops.json": B}, self_report=r"^Self-test passed$",
              nums=[Num("683 160 parameters", r'"params": {N}', ["683160"]), Num("1 356 800 FLOPs", r'"total_flops": {N}', ["1356800"])]),
        Check("parameter-split", X, Snippet(X, "named_children"), "Secs. III-C and S3, encoder 0.16 M, head 0.53 M", needs=["torch"],
              nums=[Num("683 160 = encoder 0.16 M + head 0.53 M + fixed scales", r"^{N} \{'stateencoder': {N}, 'bwe_head': {N}\}", ["683160", "0.16M", "0.53M"])]),
        # ------------------------------------------------------------------ docs/DESIGNER.md
        Check("synthetic-old", D, "python3 scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py old", "Table II hosted row, Table IV synthetic",
              self_report=r"^0 mismatches with the recorded files$",
              nums=[Num("hosted 32/32, masked 24/32, distribution and name 0", r"hosted designer: real names {N}/32, masked {N}/32, distribution {N}, name {N}", ["32", "24", "0", "0"]),
                    Num("R1 32B 24 of 32", r"R1 distillation into Qwen 32B, 4-bit: real names {N}/32", ["24"]),
                    Num("R1 14B 17 of 32", r"R1 distillation into Qwen 14B: real names {N}/32", ["17"]),
                    Num("Qwen2.5-32B 17 of 32", r"Qwen2\.5-32B-Instruct 4-bit, non-reasoning: real names {N}/32", ["17"])]),
        Check("synthetic-new", D, "python3 scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py new", "Table II open rows",
              self_report=r"^0 mismatches with the recorded files$",
              nums=[Num("R1 32B 36 against 1 of 40", r"rt_r1_32b: real names {N}/40, masked {N}/40", ["36", "1"]),
                    Num("R1 14B 27 against 1 of 40", r"rt_r1_14b: real names {N}/40, masked {N}/40", ["27", "1"])]),
        Check("designer-size", D, "python3 scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py designer-scale", "Sec. V-D, Qwen1.5-0.5B-Chat as designer",
              self_report=r"^0 mismatches with the recorded files$",
              nums=[Num("0.500 on 12 stacks, 0 of 40 groups", r"ds_q15_05b: 12 stacks BA {N} with names.*synthetic groups {N}/40 with names", ["0.500", "0"])]),
        Check("unit-aware-matcher", D, "python3 scripts/arb/obsschema_strong_baseline_v1.py judge", "Table IV, 9 held-out schemas",
              files={R + "obsschema_strong_baseline_v1/judge.json": B},
              nums=[Num("60/72 vs 71/72, -0.15 [-0.24, -0.08]", r"R1 distilled 32B success {N}, unit-aware name matching {N}; Δ \(by group proportion\) {N}, 90% interval \[{N}, {N}\]", ["60", "71", "-0.15", "-0.24", "-0.08"])]),
        Check("seven-specs", D, "python3 scripts/coldstart/realtel_revise_v1.py", "Table IV, 7 specifications; Secs. V-E, S8",
              files={R + "realtel_adapter_v1/revise_v3.json": B, R + "realtel_adapter_v1/truth_v3.json": B},
              nums=[Num("70 of 105 pairs with a different definition", r"^Version 3: label count \{'same': {N}, 'none': {N}, 'kind': {N}\}", ["11", "24", "70"]),
                    Num("BA 1.000 vs 0.756 TF-IDF, +0.24 [+0.13, +0.41]", r"^Version 3: .*adapter: DeepSeek full scoring BA {N}, NAME {N}, TFIDF {N}, Δ {N} \[{N}, {N}\]", ["1.000", None, "0.756", "+0.24", "+0.13", "+0.41"]),
                    Num("open 32B and 14B 0.917 and 0.879", r'^Version 3: .*full scoring \{"r1_32b": {N}, "r1_14b": {N}\}', ["0.917", "0.879"]),
                    Num("as missing: 0.940 vs 0.738, +0.201 [+0.094, +0.345], 12.1%", r"^Sensitivity .*adapter: DeepSeek full scoring BA {N}, NAME {N}, TFIDF {N}, Δ {N} \[{N}, {N}\], mis-mapping {N}", ["0.940", None, "0.738", "+0.201", "+0.094", "+0.345", "0.121"])]),
        Check("seven-specs-hidden", D, "python3 scripts/coldstart/realtel_namehide_v1.py judge", "Table IV, field names hidden",
              files={R + "realtel_adapter_v1/namehide_v1/judge.json": B},
              nums=[Num("1.000", r"balanced accuracy {N} \(", ["1.000"])]),
        Check("counterfactual", D, "python3 scripts/coldstart/realtel_cfdoc_v1.py judge", "Sec. V-E, counterfactual documentation",
              files={R + "realtel_adapter_v1/cfdoc_v1/judge.json": B},
              nums=[Num("33 of 33 cells", r"{N} rewritten fields times 3 orders, {N} cells in total: against the rewritten document S {N}", ["11", "33", "1.000"])]),
        Check("twelve-stacks", D, "python3 scripts/coldstart/realtel_scale_v1.py judge", "Table IV 12 stacks, Table III hosted cost",
              files={R + "realtel_scale_v1/judge.json": scale_judge},
              nums=[Num("BA 0.920 vs 0.560 Cupid, +0.36 [+0.27, +0.45], no false map", r"balanced accuracy {N}; seven baselines .*CUPID {N},.*best: CUPID; Δ {N}, 90% interval \[{N}, {N}\]; mis-mapping {N}", ["0.920", "0.560", "+0.36", "+0.27", "+0.45", "0.000"]),
                    Num("72 of 72 unmappable declared missing", r"answers missing where no field exists {N}/72", ["72"]),
                    Num("8 of 11 stacks correct in all orders", r"among the 11 sources with scored cells, {N} are fully correct", ["8"]),
                    Num("58.3 s and 0.017 USD per stack", r"wall-clock median {N} seconds .*cost median {N} USD", ["58.3", "0.0173"]),
                    Num("chosen field 0.940 vs 0.773 COMA", r"looking only at the field LLM {N}, best comparison COMA {N}", ["0.940", "0.773"]),
                    Num("first-round labels +0.255 [0.145, 0.383]", r"first round of checking\) judged holds, Δ {N} \[{N}, {N}\]", ["+0.255", "+0.145", "+0.383"])],
              note="judge.json: sources_all_correct_all_pres 9 -> 8, LiveKit left out (docs/DESIGNER.md)"),
        Check("per-stack", D, "python3 scripts/paper/make_designer_per_stack_v1.py", "Sec. S8 per-stack results",
              files={R + "realtel_scale_v1/per_stack.csv": B}, self_report=r"^0 problems$",
              nums=[Num("8 of the 11 scored stacks", r"stacks with scored features: {N}; designer correct on every scored feature in all three orders: {N}", ["11", "8"]),
                    Num("12 errors on Agora, mediasoup, ns-3", r"designer errors: {N} on Agora Web SDK, mediasoup v3, ns-3 FlowMonitor", ["12"]),
                    Num("0.938 with the ns-3 cell unscored", r"with the ns-3 minimum-delay cell unscored {N}", ["0.938"])]),
        Check("twelve-stacks-hidden", D, "python3 scripts/coldstart/realtel_scale_namehide_v1.py judge", "Table IV, stacks with names hidden",
              files={R + "realtel_scale_v1/namehide/judge.json": B},
              nums=[Num("0.947, +0.39 [+0.30, +0.46]", r"DeepSeek balanced accuracy {N} .*Δ {N}, 90% interval \[{N}, {N}\]", ["0.947", "+0.39", "+0.30", "+0.46"])]),
        Check("repeats", D, "python3 scripts/coldstart/realtel_repeat_v1.py judge", "Secs. V-E and S8, repeated calls",
              files={R + "realtel_repeat_v1/judge.json": B},
              nums=[Num("+0.39 (0.30 to 0.46)", r"merged BA {N}, best control CUPID {N}, Δ {N}, 90% interval \[{N}, {N}\]", [None, None, "+0.39", "0.30", "0.46"]),
                    Num("0.94 and 0.96", r'BA per call \{"0": {N}, "1": {N}, "2": {N}\}', ["0.92", "0.94", "0.96"]),
                    Num("92% of feature cells agree", r"per-cell three-call agreement {N}", ["0.92"])]),
        Check("llm-schema-match", D, "python3 scripts/coldstart/llm_schema_match_v1.py judge", "Table IV, generic LLM matcher",
              files={R + "llm_schema_match_v1/judge.json": B},
              nums=[Num("0.719, +0.20 [+0.12, +0.31]", r"LLM schema matching {N} .*Δ \(designer minus schema matching\) {N}, 90% interval \[{N}, {N}\]", ["0.719", "+0.20", "+0.12", "+0.31"]),
                    Num("chosen field 0.979 vs 0.940", r"fields only designer {N}, schema matching {N}", ["0.940", "0.979"])]),
        Check("two-step-match", D, "python3 scripts/coldstart/llm_twostep_match_v1.py judge", "Table IV, fields then units",
              files={R + "llm_twostep_match_v1/judge.json": B},
              nums=[Num("0.966, -0.046 [-0.092, -0.001]", r"two-step \(.*?\) {N}; Δ {N}, 90% interval \[{N}, {N}\]", ["0.966", "-0.046", "-0.092", "-0.001"]),
                    Num("end to end 42, 38 and 42 of 42", r"end-to-end 42 cells judged correct designer {N}, general matcher {N}, two-step {N}", ["42", "38", "42"])]),
        Check("kind-as-missing", D, "python3 scripts/coldstart/realtel_scale_kindmiss_explore.py", "Sec. S8, different definitions as missing",
              files={R + "realtel_scale_v1/kindmiss_explore.json": B},
              nums=[Num("0.865 vs 0.597 COMA, +0.268 [+0.160, +0.394], 11.0%", r'"kind_as_missing": \{"ba_llm": {N}, "best_base": "COMA", "ba_best": {N}, "delta": {N}, "ci90": \[{N}, {N}\], "false_map_rate": {N}', ["0.865", "0.597", "+0.268", "+0.160", "+0.394", "0.110"])]),
        Check("open-first-sample", D, "python3 scripts/coldstart/realtel_scale_v1.py open_score", "Sec. S8, open models on 12 stacks",
              nums=[Num("R1 32B 59 of 75, 72 of 72, 1 of 36 unparsable", r"r1_32b: same quantity {N}/75, none corresponding to missing answers {N}/72, .*?unparseable {N}/36", ["59", "72", "1"]),
                    Num("R1 14B 29 of 75, 72 of 72, 12 of 36 unparsable", r"r1_14b: same quantity {N}/75, none corresponding to missing answers {N}/72, .*?unparseable {N}/36", ["29", "72", "12"])]),
        Check("open-three-samples", D, "python3 scripts/coldstart/open_sampling_variance_v1.py score", "Fig. 3(a,b) open models",
              files={R + "open_sampling_variance_v1/summary.json": B}, self_report=r"^Self-test passed",
              nums=[Num("R1 32B: end to end 0.62, BA 0.89", r"^r1_32b 3 times \{'e2e_v3': \{'mean': {N}, .*'ba12': \{'mean': {N},", ["0.62", "0.89"]),
                    Num("R1 14B: end to end 0.37, BA 0.70", r"^r1_14b 3 times \{'e2e_v3': \{'mean': {N}, .*'ba12': \{'mean': {N},", ["0.37", "0.70"])]),
        Check("model-size", D, "python3 scripts/coldstart/r1qwen_size_v1.py score", "Sec. V-D, R1 distillations by size",
              files={R + "realtel_scale_r1qwen_size_v1/summary.json": B},
              nums=[Num("1.5B 0.50, 11 to 13 of 36 parse", r"^1\.5B 3 times {N} .*Parse \['{N}/36', '{N}/36', '{N}/36'\]", ["0.50", "11", "12", "13"]),
                    Num("7B 0.55", r"^7B 3 times {N}", ["0.55"]), Num("14B 0.70", r"^14B 3 times {N}", ["0.70"]),
                    Num("32B 0.89", r"^32B 3 times {N}", ["0.89"])]),
        Check("engineer-labels", D, None, "Sec. VI, 38 disagreements settled",
              vals=[Val("38 disagreements", R + "gt_blind_expert_v1_public/adjudication.json", ["n"], "38")],
              note="no command; reads gt_blind_expert_v1_public/adjudication.json"),
        Check("engineer-agreement", D, Snippet(D, "kappa"), "Sec. V-E, agreement with the engineer",
              nums=[Num("68 of 84, kappa 0.22", r"^{N} of {N} kappa {N}$", ["68", "84", "0.22"])]),
        Check("engineer-truth", D, "python3 scripts/coldstart/gt_engineer_sens_v1.py", "Sec. V-E, rescored with the engineer's labels",
              files={R + "gt_blind_expert_v1/engineer_truth_sens_v1.json": B},
              nums=[Num("0.824 vs 0.615 COMA (0.15 to 0.27)", r"Engineer's labels as ground truth: designer BA {N} best baseline COMA {N} Δ {N} \[{N}, {N}\]", ["0.824", "0.615", None, "0.15", "0.27"])]),
        Check("real-software", D, "python3 scripts/realtel_e2e/realtel_e2e_v1.py judge && python3 scripts/paper/make_tables_v2.py",
              "Table IV real software (42 cells via make_tables_v2)",
              files={R + "realtel_e2e_v1/judge.json": B}, refs=[("papers/revision-v2/tables/table_designer.tex", "tables/table_designer.tex")],
              nums=[Num("48 cells, Similarity Flooding 0.667", r"adapter judged correct {N}; control .*,SF {N},", ["1.000", "0.667"])]),
        Check("value-rule", D, "python3 scripts/realtel_e2e/e2e_valuerule_v1.py", "Sec. V-E, lead with the shared value rule",
              files={R + "realtel_e2e_valuerule_v1/judge.json": B},
              nums=[Num("+0.10 (0.02 to 0.18), direction only", r"^direction only .*Δ {N}, 90% interval \[{N}, {N}\]", ["+0.10", "+0.02", "+0.18"])]),
        Check("single-fields", D, "python3 scripts/coldstart/mask_offline_local_v1.py", "Sec. V-E, single-field features",
              self_report=r"^recorded summary\.json: values equal, bytes equal$",
              nums=[Num("5.80 rises to 9.0 to 23.3", r"macro MSE over the 12 stacks: {N} to {N} \(unmasked {N}\)", ["9.0", "23.3", "5.80"])]),
        Check("getstats-closure", D, "python3 scripts/realtel_e2e/closure_v2.py judge", "Table IV browser getStats, Sec. S8", needs=["onnxruntime"],
              files={R + "realtel_closure_v1/v2/judge.json": B},
              vals=[Val("derivation function 0.197", R + "realtel_closure_v1/v2/judge.json", ["mean_dev", "LLM_CODE"], "0.197"),
                    Val("Cupid's mapping 0.463", R + "realtel_closure_v1/v2/judge.json", ["mean_dev", "MAP_CUPID"], "0.463"),
                    Val("single-field mapping 0.240", R + "realtel_closure_v1/v2/judge.json", ["mean_dev", "MAP_LLM"], "0.240"),
                    Val("+0.27", R + "realtel_closure_v1/v2/judge.json", ["delta"], "+0.27"),
                    Val("[+0.14", R + "realtel_closure_v1/v2/judge.json", ["ci90", 0], "+0.14"),
                    Val("+0.37]", R + "realtel_closure_v1/v2/judge.json", ["ci90", 1], "+0.37")]),
        Check("closed-loop-designer", D, "python3 scripts/paper/make_fig_closedloop_designer_v2.py", "Table IV closed loop, Fig. 3(c)",
              nums=[Num("designer 1.16 (signed +0.1), 0 losses", r"'LLM': \({N}, {N}, {N}, {N}, {N},", ["1.16", "+0.1", "0", None, "32"]),
                    Num("name matching 6.01 (signed -1.5), 7 losses", r"'NAME': \({N}, {N}, {N}, {N}, {N},", ["6.01", "-1.5", "7", None, "32"]),
                    Num("distribution matching 7.62, 8 losses", r"'DIST': \({N}, {N}, {N}, {N}, {N},", ["7.62", None, "8", None, "32"]),
                    Num("no adaptation 11.16, 8 losses", r"'NONE': \({N}, {N}, {N}, {N}, {N},", ["11.16", None, "8", None, "24"])],
              note="the script asserts its cells against result_v1.json"),
        # ------------------------------------------------------------------ docs/TESTBED.md
        Check("first-720p-batch", T, Snippet(T, "import hd720_ch_eval_v1 as E"), "Table V first batch",
              nums=[Num("holds, D = 4.5758 [3.4411, 5.7402]", r"^\('holds', \{'D': {N}, 'ci90': \[{N}, {N}\]", ["4.5758", "3.4411", "5.7402"])]),
        Check("ramp-steady", T, "python3 scripts/paper/steady_state_qoe_v1.py run", "Sec. V-F ramp-up and steady state",
              files={R + "closedloop_steady_qoe_v1/summary.json": B},
              vals=[Val("ramp-up lead up to 32", R + "closedloop_steady_qoe_v1/summary.json", ["hd720-randloss-ch-v1", "ramp", "D"], "32"),
                    Val("after 30 s up to +2.1", R + "closedloop_steady_qoe_v1/summary.json", ["hd720-randloss-ch-v1", "steady", "D"], "+2.1")]),
        Check("cellular-steady", T, Snippet(T, 'S.batch("hd720-realtrace-ch-v1")', inline=True), "Sec. V-F cellular batch (exploratory)",
              stdout_json=R + "closedloop_steady_qoe_v1/realtrace_explore_v1.json",
              vals=[Val("ramp-up lead 15", R + "closedloop_steady_qoe_v1/realtrace_explore_v1.json", ["ramp", "D"], "15"),
                    Val("after 30 s -0.5", R + "closedloop_steady_qoe_v1/realtrace_explore_v1.json", ["steady", "D"], "-0.5")]),
        # ------------------------------------------------------------------ docs/RESULTS_INDEX.md
        Check("table5-snippet", X, Snippet(X, "def check(batch, arm, ref"), "Table V rows, echo test",
              nums=[Num(f"{lab} {q[0]} [{q[1]}, {q[2]}]", rf"^{re.escape(b)} {re.escape(a)} vs {re.escape(r)}: .*?, D = {{N}} \[{{N}}, {{N}}\]$", q) for lab, b, a, r, q in [
                  ("first batch", "hd720_closedloop_ch_v1", "arm_ch_x", "gcc_pt125_c200", ["4.6", "3.4", "5.7"]),
                  ("second batch", "hd720_echo_attr_ch_v1", "arm_ch_x", "gcc_pt125_c200", ["4.4", "3.5", "5.3"]),
                  ("seeds 0 and 2", "hd720_seeds_ch_v1", "arm_ch_x", "gcc_pt125_c200", ["6.1", "5.1", "7.1"]),
                  ("cellular", "hd720_realtrace_ch_v1", "arm_ch_x", "gcc_pt125_c200", ["4.3", "3.2", "5.3"]),
                  ("high bandwidth", "hd720_highbw_ch_v1", "arm_ch_x", "gcc_pt125_c200", ["6.6", "5.9", "7.3"]),
                  ("random loss", "hd720_randloss_ch_v1", "arm_ch_x", "gcc_pt125_c200", ["8.9", "7.7", "10.2"]),
                  ("echo test", "hd720_echo_attr_ch_v1", "arm_ch_x", "echo_x", ["2.97", "1.86", "4.13"]),
                  ("Schaferct-R", "hd720_learned_baselines_v1", "arm_ch_x", "arm_schaferct_retrained_d", ["0.5", "-0.3", "1.3"]),
                  ("supervised MLP", "hd720_learned_baselines_v1", "arm_ch_x", "arm_mlp_d", ["1.2", "0.3", "2.0"]),
                  ("Schaferct-R high bandwidth", "hd720_hb_learned_v1", "ch", "scr", ["2.3", "1.7", "2.8"]),
                  ("Schaferct-R high bandwidth, no envelope", "hd720_hb_learned_v1", "ch0", "scr0", ["2.3", "2.0", "2.6"]),
                  ("Schaferct-R, no envelope", "hd720_learned_alone_v1", "arm_ch_x", "arm_schaferct_retrained_d", ["7.2", "5.5", "8.8"])]]),
        Check("envelope-rewrites", X, Snippet(X, "envelope_rewrite_frac"), "Sec. V-F envelope rewrites, no envelope",
              nums=[Num("77% of decisions rewritten", r"\A{N}$", ["0.767"]), Num("deployed estimator 74.6 VMAF without envelope", r"^arm_ch_x {N}$", ["74.6"]),
                    Num("MLP 7.7 VMAF without envelope", r"^arm_mlp_d {N}$", ["7.7"])]),
        Check("low-capacity-snippet", X, Snippet(X, "show = lambda name, vm"), "Fig. 4(c), Sec. V-F low capacities, shared link",
              nums=[Num("behind the envelope +0.5 [-0.7, 1.7]", r"^behind the envelope .*? {N} \[{N}, {N}\]$", ["+0.5", "-0.7", "1.7"]),
                    Num("estimators alone -1.5 [-2.8, 0.0]", r"^no envelope, floor .*? {N} \[{N}, {N}\]$", ["-1.5", "-2.8", "0.0"]),
                    Num("1% loss -1.3 [-2.4, -0.2]", r"^envelope, 1% loss .*? {N} \[{N}, {N}\]$", ["-1.3", "-2.4", "-0.2"]),
                    Num("anchor-free 14.8 behind", r"^no anchor .*? {N} \[", ["-14.8"]),
                    Num("200 kb/s with 1% loss 5.5 behind", r"^200 kb/s, 1% loss .*? {N} \[", ["-5.5"]),
                    Num("against GCC -1.37 [-2.579, -0.146]", r"deployed system - GCC \({N}, \[{N}, {N}\]\)", ["-1.37", "-2.579", "-0.146"]),
                    Num("320x240 Johnny -0.2 [-0.5, 0.1]", r"^320x240 low {N} \[{N}, {N}\]", ["-0.2", "-0.5", "0.1"]),
                    Num("320x240 Mobcal 1.6 [1.1, 2.1]", r"^320x240 medium {N} \[{N}, {N}\]", ["1.6", "1.1", "2.1"]),
                    Num("320x240 Parkrun 0.9 [0.2, 1.7]", r"^320x240 high {N} \[{N}, {N}\]", ["0.9", "0.2", "1.7"]),
                    Num("shared link 0.050 below (-0.12 to 0.02)", r"^shared link .*? {N} \[{N}, {N}\]$", ["-0.050", "-0.12", "0.02"])]),
        Check("lambda-closed-loop", X, Snippet(X, "import hd720_ch_eval_v1 as H, hd720_lambda_v1 as HL"), "Sec. S6 closed loop, reward weight",
              nums=[Num("720p lambda 0.8: -0.4 VMAF", r"\A{N}$", ["-0.4"]),
                    Num("breaks +2.0 of 24; utility -4.7 at 1.0, +0.7 at 0", r"^{N} {N} {N}$", ["+2.0", "-4.7", "+0.7"]),
                    Num("seed 1, lambda 0: -1.2", r"^lowbw_lambda_ch_v2 l00 {N}$", ["-1.2"]),
                    Num("behind the envelope, lambda 1.0: +0.5", r"^lowbw_lambda_env6_v1 l10 {N}$", ["+0.5"]),
                    Num("behind the envelope, lambda 0: -0.05", r"^lowbw_lambda_env6_v1 l00 {N}$", ["-0.05"])]),
    ]


# ---------------------------------------------------------------------------------------------------------------------
# Running and judging

def value_unit(s):
    """'4.58' -> (4.58, 0.01); '0.16M' -> (160000.0, 10000.0): the number and the unit of its last digit."""
    scale = 1e6 if s.endswith("M") else 1.0
    s = s.rstrip("M"); mant = s.lower().split("e")[0]
    exp = int(s.lower().split("e")[1]) if "e" in s.lower() else 0
    d = len(mant.split(".")[1]) if "." in mant else 0
    return float(s) * scale, 10.0 ** (exp - d) * scale


def agrees(printed, quoted):
    """A printed number agrees with a quoted one when the quote is a rounding of it.

    Same precision: equal. Printed coarser than the quote: within half a printed unit. Printed finer: within half a
    unit of the quote's last digit, plus half a printed unit for a printed value that is itself rounded."""
    (p, up), (q, uq) = value_unit(printed), value_unit(quoted)
    eps = 1e-9 * max(1.0, abs(q))
    if abs(up - uq) <= 1e-12 * uq: return abs(p - q) <= eps
    if up > uq: return abs(p - q) <= 0.5 * up + eps
    return abs(p - q) <= 0.5 * uq + 0.5 * up + eps


def snippet_code(root, sn):
    """(language, code, line in the doc) of the snippet, or (None, None, None)."""
    t = (root / sn.doc).read_text(encoding="utf-8")
    if sn.inline:
        m = re.search(r"`([^`\n]*" + re.escape(sn.marker) + r"[^`\n]*)`", t)
        return ("bash", m.group(1), t[:m.start()].count("\n") + 1) if m else (None, None, None)
    for m in re.finditer(r"^([ \t]*)```([A-Za-z]*)[ \t]*\n(.*?)^\1```", t, re.S | re.M):
        if sn.marker in m.group(3):
            return (m.group(2) or "bash"), textwrap.dedent(m.group(3)), t[:m.start()].count("\n") + 1
    return None, None, None


def snapshot(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = Path(dp) / f
            try: s = p.lstat()
            except FileNotFoundError: continue
            out[str(p.relative_to(root))] = (s.st_size, s.st_mtime_ns)
    return out


def get_path(obj, path):
    for k in path: obj = obj[k]
    return obj


def missing_modules(names):
    return [n for n in names if importlib.util.find_spec(n) is None]


def run_check(c, base, logdir, binpath, timeout, keep):
    """Returns (result text, seconds, problems). The copy is removed afterwards unless keep."""
    miss = missing_modules(c.needs)
    if miss: return f"skipped: {', '.join(miss)} not installed", None, []
    work = base / f"pkg-{c.name}"
    if work.exists(): shutil.rmtree(work)
    try:
        return judge_check(c, work, logdir, binpath, timeout)
    finally:
        if not keep: shutil.rmtree(work, ignore_errors=True)


def judge_check(c, work, logdir, binpath, timeout):
    V1.copy_package(ROOT, work)
    pairs = V1.replacement_pairs(work)   # the same substitution, applied to released files before comparing
    V1.set_placeholders(work)
    before = snapshot(work)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PATH=f"{binpath}{os.pathsep}{os.environ.get('PATH', '')}")
    problems, out, dt = [], "", 0.0
    if c.cmd is not None:
        if isinstance(c.cmd, Snippet):
            lang, code, _ = snippet_code(ROOT, c.cmd)
            if code is None: return "error: code block not found in " + c.cmd.doc, None, [f"no code block with {c.cmd.marker!r} in {c.cmd.doc}"]
            argv, stdin = (["python3", "-"], code) if lang == "python" else (["bash", "-c", code], None)
        else:
            argv, stdin = ["bash", "-c", c.cmd], None
        t0 = time.time()
        try:
            r = subprocess.run(argv, cwd=work, env=env, input=stdin, capture_output=True, text=True, timeout=timeout,
                               stdin=None if stdin is not None else subprocess.DEVNULL)
            rc, out, err = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = f"timeout after {timeout:.0f} s", e.stdout or "", e.stderr or ""
            out, err = (out.decode() if isinstance(out, bytes) else out), (err.decode() if isinstance(err, bytes) else err)
        dt = time.time() - t0
        (logdir / f"{c.name}.out").write_text(out, encoding="utf-8"); (logdir / f"{c.name}.err").write_text(err, encoding="utf-8")
        if rc != 0:
            tail = (err.strip().split("\n") or [""])[-1][:120]
            what = rc if isinstance(rc, str) else f"exit {rc}"
            return f"FAILED ({what})", dt, [f"{what}" + (f": {tail}" if tail else "") + f"; log in logs/{c.name}.err"]
    after = snapshot(work)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    # Files the command should rewrite
    for rel, how in c.files.items():
        new = work / rel
        if rel not in changed: problems.append(f"{rel}: not rewritten"); continue
        if not new.is_file(): problems.append(f"{rel}: deleted"); continue
        old_b = V1.apply_pairs((ROOT / rel).read_bytes(), pairs)
        if how == "bytes":
            if new.read_bytes() != old_b: problems.append(f"{rel}: differs from the released file")
        else:
            problems += [f"{rel}{d}" for d in how(json.loads(old_b), json.loads(new.read_bytes()))]
    # Any other released file it changed must be unchanged in content
    for rel in changed:
        if rel in c.files or rel == LOCAL_LOG or not (ROOT / rel).is_file(): continue
        if (work / rel).is_file() and (work / rel).read_bytes() != V1.apply_pairs((ROOT / rel).read_bytes(), pairs):
            problems.append(f"{rel}: changed")
        elif not (work / rel).exists():
            problems.append(f"{rel}: deleted")
    for rel, ref_rel in c.refs:
        ref = ROOT / "expected" / ref_rel
        if not ref.is_file(): problems.append(f"expected/{ref_rel} missing, cannot compare {rel}")
        elif not (work / rel).is_file() or (work / rel).read_bytes() != ref.read_bytes(): problems.append(f"{rel}: differs from expected/{ref_rel}")
    if c.self_report and not re.search(c.self_report, out, re.M): problems.append(f"no match report ({c.self_report.strip('^$')!r} not printed)")
    for n in c.nums:
        m = n.rx.search(out)
        if not m: problems.append(f"not printed: {n.label}"); continue
        for g, q in zip(m.groups(), n.quoted):
            if q is not None and not agrees(g, q): problems.append(f"{n.label}: printed {g}, docs {q}")
    for v in c.vals:
        try: x = get_path(json.loads((work / v.rel).read_text(encoding="utf-8")), v.path)
        except (OSError, KeyError, IndexError, ValueError) as e: problems.append(f"{v.rel}: {v.label}: {type(e).__name__}"); continue
        if not isinstance(x, (int, float)) or isinstance(x, bool):
            problems.append(f"{v.label}: {x!r} in {Path(v.rel).name} is not a number"); continue
        if not agrees(str(x) if isinstance(x, int) else repr(float(x)), v.quoted): problems.append(f"{v.label}: {x} in {Path(v.rel).name}, docs {v.quoted}")
    if c.stdout_json:
        try:
            if ast.literal_eval(out.strip()) != json.loads((work / c.stdout_json).read_text(encoding="utf-8")):
                problems.append(f"printed result differs from {c.stdout_json}")
        except (ValueError, SyntaxError): problems.append("printed result is not a literal")
    return ("reproduced" if not problems else "MISMATCH"), dt, problems


def main():
    ap = argparse.ArgumentParser(prog="reproduce/run_level2.sh", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=__doc__.split("\n\n")[0],
                                 epilog="Set PYTHON to choose the interpreter (default python3). Logs of every command are kept "
                                        "in the work directory when a check fails or with --keep.")
    ap.add_argument("--list", action="store_true", help="list the checks and exit")
    ap.add_argument("--only", help="comma-separated names of checks to run (see --list)")
    ap.add_argument("--workdir", help="directory for the temporary copies and logs (default: the system temporary directory)")
    ap.add_argument("--keep", action="store_true", help="keep the copy of every check (about 0.3 GB each) and the logs")
    ap.add_argument("--timeout", type=float, default=3600, help="seconds per command (default 3600)")
    A = ap.parse_args()
    C = checks()
    if A.list:
        V1.print_table(("Name", "Doc", "Command", "Reproduces"),
                       [(c.name, c.doc, show(c), c.reproduces) for c in C]); return
    if A.only:
        want = [w.strip() for w in A.only.split(",") if w.strip()]
        unknown = [w for w in want if w not in {c.name for c in C}]
        if unknown: sys.exit(f"unknown check(s): {', '.join(unknown)}; see --list")
        C = [c for c in C if c.name in want]
    if A.workdir: Path(A.workdir).mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="llm4bandpp-level2-", dir=A.workdir)); logdir = base / "logs"; logdir.mkdir()
    binpath = base / "bin"; binpath.mkdir()
    (binpath / "python3").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n'); (binpath / "python3").chmod(0o755)
    print(f"package: {ROOT}\npython3: {sys.executable} ({sys.version.split()[0]}); each command runs in a fresh copy under {base}")
    for c in C:
        for part in unlisted(c): print(f"warning: {c.name}: {part!r} does not appear in {c.doc}")
    rows, details, bad = [], [], 0
    for c in C:
        res, dt, probs = run_check(c, base, logdir, binpath, A.timeout, A.keep)
        rows.append((c.name, show(c), c.reproduces, res, "-" if dt is None else f"{dt:.1f}"))
        if probs: details.append((c.name, probs)); bad += 1
        print(f"  {c.name}: {res}" + ("" if dt is None else f" ({dt:.1f} s)"), flush=True)
    print()
    V1.print_table(("Check", "Command", "Reproduces", "Result", "Seconds"), rows)
    for name, probs in details:
        print(f"\n{name}:"); [print(f"  - {p}") for p in probs]
    notes = [(c.name, c.note) for c in C if c.note]
    if notes:
        print("\nNotes:"); [print(f"  {n}: {t}") for n, t in notes]
    skipped = sum(r[3].startswith("skipped") for r in rows); ok = sum(r[3] == "reproduced" for r in rows)
    print(f"\n{ok} of {len(rows)} checks reproduced, {bad} not, {skipped} skipped")
    if bad or A.keep: print(f"logs{' and copies' if A.keep else ''} kept in {base}")
    else: shutil.rmtree(base, ignore_errors=True)
    sys.exit(1 if bad else 0)


def unlisted(c):
    """Parts of a check's command that its doc does not mention (the docs may omit the leading python3)."""
    if not isinstance(c.cmd, str): return []
    t = (ROOT / c.doc).read_text(encoding="utf-8")
    return [p for p in c.cmd.split(" && ") if p not in t and p.replace("python3 ", "", 1) not in t]


def show(c):
    if c.cmd is None: return "(reads the file; no command)"
    if isinstance(c.cmd, Snippet):
        lang, _, line = snippet_code(ROOT, c.cmd)
        if line is None: return f"code block in {c.cmd.doc} (not found)"
        return f"{'inline command' if c.cmd.inline else lang + ' block'} at {c.cmd.doc}:{line}"
    return c.cmd


if __name__ == "__main__":
    main()
