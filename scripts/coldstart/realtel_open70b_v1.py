#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scoring of realtel-open70b-e2e-v1 (criteria in its pre-registration); open-sampling-variance-v1 reuses its scoring functions.
fetch: copies the 70B outputs from the GPU server (7 specifications, 21 prompts, end to end in the first field order; 12 stacks, 36 prompts; closure) into realtel_adapter_v1 and realtel_scale_v1 as out_open_r1_70b.jsonl and into experiments/results/realtel_open70b_v1.
judge: applies the 70B adapters (first field order, parsed as the open-model branch of realtel_e2e_v1.adapters) to the 24 runs and scores every cell with realtel_e2e_v1, leaving out the tcp_info byte count (k=2) as the third ground truth does, which gives the 42 cells of the paper.
The 70B takes the place of the hosted arm in realtel_e2e_v1.judge against the seven non-LLM methods of judge.json; reported only: BA on the 12 stacks, parse rates, and the same readings for the hosted model, 32B and 14B.
selftest: the same code must reproduce the 32B and 14B cells of judge.json, their registered rates 0.619 and 0.714 and their 12-stack BA 0.893 and 0.693.
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for p in ("scripts/coldstart", "scripts/realtel_e2e", "scripts/paper"): sys.path.insert(0, str(ROOT / p))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_scale_v1 as RS  # noqa: E402
import realtel_e2e_v1 as E2  # noqa: E402
OUT = ROOT / "experiments/results/realtel_open70b_v1"; ID = "realtel-open70b-e2e-v1"; TAG = "r1_70b"; W = "/path/to/server/work/openreason_v1"
RUNS = E2.OUT / "runs"; REG_E2E_V3 = {"OPEN_r1_32b": 0.619, "OPEN_r1_14b": 0.714}; REG_BA12 = {"r1_32b": 0.893, "r1_14b": 0.693}


def open_adapter(tag):
    """As the open-model branch of realtel_e2e_v1.adapters: the first-order mapping as {end-to-end source: {feature: (field name, differenced, scale) or None}}."""
    O = {}
    for j in map(json.loads, open(M.OUT / f"out_open_{tag}.jsonl")):
        _, n, k = j["id"].split("|")
        if k == "0":
            try: O[n] = M.parse(j["text"], len(M.TEST[n]["fields"]))
            except Exception: O[n] = None
    def from_map(mp, src):
        f = M.TEST[src]["fields"]; return {k: (None if (mp is None or mp[k] is None) else (f[mp[k]["source"]][0], bool(mp[k]["diff"]), float(mp[k]["scale"]))) for k in range(15)}
    return {e: from_map(O.get(s), s) for e, s in E2.SRC.items()}


def units(A):
    R = []
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir() or not (d / "OK").exists(): continue
        src = d.name.split("_")[0]; Wn = E2.LOAD[src](d)
        for k in E2.FEATS[src]:
            e, ok = E2.unit_err(Wn, k, A[src].get(k)); R.append({"run": d.name, "k": k, "src": src, "ok": int(ok), "err": e})
    return R


def v3(us): return [u for u in us if not (u["src"] == "tcpinfo" and u["k"] == 2)]
def rate(us): return sum(u["ok"] for u in us) / len(us)


def ba12(tag):
    import make_fig_designer_v2 as F
    return F.open_ba(tag)


def parse_stats(path, n_fields_of):
    n = ok = lim = 0
    for j in map(json.loads, open(path)):
        n += 1; lim += j.get("finish_reason") == "length"
        try: M.parse(j["text"], n_fields_of(j["id"].split("|")[1])); ok += 1
        except Exception: pass
    return {"n": n, "parsed": ok, "hit_limit": lim}


def selftest():
    U = json.load(open(E2.OUT / "judge.json"))["units"]
    for tag in ("r1_32b", "r1_14b"):
        mine = units(open_adapter(tag)); ref = U["OPEN_" + tag]
        assert [(u["run"], u["k"], u["ok"]) for u in mine] == [(u["run"], u["k"], u["ok"]) for u in ref], f"{tag} end-to-end cell inconsistent with judge.json"
        r = round(rate(v3(mine)), 3); assert r == REG_E2E_V3["OPEN_" + tag], (tag, r)
        b = round(ba12(tag), 3); assert b == REG_BA12[tag], (tag, b)
        print(f"{tag}: end-to-end cell {len(mine)} entries match judge.json entry by entry, correct share under the third ground truth {r}, 12-source balanced accuracy {b}, all reproduce the registered values")
    rows = v3(U["DEEPSEEK"]); assert len(rows) == 42, len(rows)
    print("Self-test passed: 32B and 14B reproduced, third ground truth, 42 cells")


def fetch():
    sh = lambda c: subprocess.run(["ssh", "-o", "BatchMode=yes", "gpu-server-1", c], capture_output=True, text=True, timeout=120)
    if "yes" not in sh(f"test -f {W}/CHAIN_70B_DONE && echo yes").stdout: sys.exit(f"CHAIN_70B_DONE not seen on gpu-server-1: {sh(f'cat {W}/CHAIN_70B_FAILED 2>/dev/null').stdout.strip()}")
    OUT.mkdir(parents=True, exist_ok=True)
    for remote, local in ((f"out_realtel_{TAG}.jsonl", M.OUT / f"out_open_{TAG}.jsonl"), (f"out_scale_{TAG}.jsonl", RS.OUT / f"out_open_{TAG}.jsonl"),
                          (f"out_closure_{TAG}.jsonl", OUT / f"out_closure_{TAG}.jsonl"), ("run_70b_chain_v1.log", OUT / "run_70b_chain_v1.log"),
                          (f"run_realtel_{TAG}.log", OUT / f"run_realtel_{TAG}.log"), (f"run_scale_{TAG}.log", OUT / f"run_scale_{TAG}.log")):
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"gpu-server-1:{W}/{remote}", str(local)], check=True)
    print("Retrieved")


def judge():
    selftest()
    U = json.load(open(E2.OUT / "judge.json"))["units"]; A70 = open_adapter(TAG); u70 = units(A70)
    R = {"DEEPSEEK": v3(u70), **{m: v3(us) for m, us in U.items() if m != "DEEPSEEK" and not m.startswith("OPEN_")}}
    v, m = E2.judge(R)
    ref_rates = {"hosted_DEEPSEEK": rate(v3(U["DEEPSEEK"])), "OPEN_r1_32b": rate(v3(U["OPEN_r1_32b"])), "OPEN_r1_14b": rate(v3(U["OPEN_r1_14b"]))}
    b70 = ba12(TAG); S = RS.load_sources()
    ps = {"realtel_7src": parse_stats(M.OUT / f"out_open_{TAG}.jsonl", lambda n: len(M.TEST[n]["fields"])), "scale_12src": parse_stats(RS.OUT / f"out_open_{TAG}.jsonl", lambda n: len(S[n]["fields"]))}
    res = {"verdict": v, **m, "rate_70b_v3": rate(v3(u70)), "ref_rates_v3": ref_rates, "ba12_70b": b70, "ba12_ref": REG_BA12, "parse": ps, "adapter_70b": A70, "units_70b": u70}
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "judge.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    rt = m["rate"]
    basis = (f"Third ground truth, 42 cells: open R1 distillation into Llama 70B (4-bit) judged correct {rt['DEEPSEEK']:.3f}; seven controls " + ",".join(f"{b} {x:.3f}" for b, x in rt.items() if b != "DEEPSEEK") +
             f"(best: {m['best_base']}); Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; 70B cells with severe errors {m['gross_llm']}. Report only: under the same scoring, hosted model {ref_rates['hosted_DEEPSEEK']:.3f}, 32B {ref_rates['OPEN_r1_32b']:.3f}, 14B {ref_rates['OPEN_r1_14b']:.3f}; 12-source balanced accuracy 70B {b70:.3f} (32B 0.893, 14B 0.693); parsing {json.dumps(ps, ensure_ascii=False)}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({"delta": m["delta"], "ci90": m["ci90"], "rate": rt, "gross": m["gross_llm"], "ba12_70b": b70}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered, section 2 (as realtel-e2e-v1, 42 cells under the third ground truth)." + basis, "--basis", basis,
       "--limitations", "Single open-source reasoning model GPTQ four-bit, one sample per entry (temperature 0.6); end-to-end uses only the first field order; 24 runs on the loopback interface with netem, not a real wide-area network; prompts and generation settings identical to those of 32B and 14B.",
       "--next", "")


if __name__ == "__main__":
    {"fetch": fetch, "judge": judge, "selftest": selftest}[sys.argv[1]]()
