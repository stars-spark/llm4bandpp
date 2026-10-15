#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""realtel-designer-scale-v1 (criteria in its pre-registration): small models as the designer, Qwen1.5-0.5B-Chat, Qwen2.5-1.5B-Instruct and Qwen2.5-7B-Instruct (vLLM on gpu-server-2, temperature 0.6, one sample per prompt).
Prompts, all verbatim: the 80 synthetic prompts of obsschema_rt_openreason_v1/prompts.jsonl, the 36 prompts of the 12 stacks with real names (prompts_scale.jsonl) and 36 with masked names (the masked sources of realtel-scale-namehide-v1).
Scoring: synthetic groups by the offline replay of obsschema_rt_offline_v1.py on the server (success when the median ratio is at most 1.2); the 12 stacks by the full scoring of realtel_scale_v1.
Commands: prep (write and upload the merged prompts and the run scripts), launch (start the serial generation on the server), finalize (wait, fetch, score, register).
To rescore from the saved files without the servers: obsschema_rt_openreason_judge_offline_v1.py designer-scale.
"""
import json, subprocess, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_scale_v1 as RS  # noqa: E402
import obsschema_llm_v1 as L  # noqa: E402
OUT = ROOT / "experiments/results/realtel_designer_scale_v1"; ID = "realtel-designer-scale-v1"
W = "/path/to/server/work/openreason_v1"; RO = "/path/to/server/outputs/obsschema_rt_v1"; HOST = "gpu-server-2"
MODELS = {"ds_q15_05b": "/path/to/server/models/Qwen1.5-0.5B-Chat", "ds_q25_15b": "/path/to/server/models/Qwen2.5-1.5B-Instruct", "ds_q25_7b": "/path/to/server/models/Qwen2.5-7B-Instruct"}
MAXLEN = {"ds_q15_05b": 16384, "ds_q25_15b": 16384, "ds_q25_7b": 16384}
SSH = ["ssh", "-n", "-o", "ConnectTimeout=20", "-o", "BatchMode=yes"]
RUN_V4 = '''#!/usr/bin/env bash
# variant of run_openreason_v3.sh (realtel-designer-scale-v1): only two more parameters, max length and max output, for models with a smaller context window. Usage: bash run_openreason_v4.sh TAG MODEL PROMPTS MAXLEN MAXNEW
set -u; TAG=$1; M=$2; PR=$3; ML=$4; MN=$5; W=/path/to/server/work/openreason_v1; PY=/path/to/server/envs/vllm066/bin/python
export HF_HOME=/path/to/server/cache/huggingface TMPDIR=/path/to/server/cache/tmp
cd $W; log() { echo "[$(date \'+%F %T\')] $*" >> $W/run_$TAG.log; }
fail() { log "$*"; date -Is > $W/FAILED_$TAG; exit 1; }
n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l); [ "$n" = 0 ] || fail "there are already $n processes on the GPU, not starting"
head -2 "$PR" > smoke_in_$TAG.jsonl; rm -f smoke_$TAG.jsonl
timeout 3600 $PY vllm_generate_v2.py "$M" smoke_in_$TAG.jsonl smoke_$TAG.jsonl --tp 2 --max-len $ML --max-new $MN --temp 0.6 --top-p 0.95 --max-seqs 8 >> $W/run_$TAG.log 2>&1 || fail "smoke test failed"
$PY -c "import json; r=[json.loads(l) for l in open(\'smoke_$TAG.jsonl\')]; assert len(r)==2 and all(x[\'finish_reason\'] for x in r); print([(x[\'n_tokens\'], x[\'finish_reason\']) for x in r])" >> $W/run_$TAG.log 2>&1 || fail "smoke test output incorrect"
log "smoke test passed, full run starting"
$PY vllm_generate_v2.py "$M" "$PR" out_$TAG.jsonl --tp 2 --max-len $ML --max-new $MN --temp 0.6 --top-p 0.95 --max-seqs 8 >> $W/run_$TAG.log 2>&1 || fail "full run failed"
log "full run complete"
'''
CHAIN = '''#!/usr/bin/env bash
# realtel-designer-scale-v1 serial chain: wait for the two small models to finish downloading, then run the three models in sequence; after each model finishes, write out_TAG.jsonl.DONE (written by vllm_generate_v2.py).
set -u; W=/path/to/server/work/openreason_v1; cd $W
while [ ! -f /path/to/server/models/PULL_DONE_small_designer ]; do sleep 60; done
for spec in "ds_q15_05b /path/to/server/models/Qwen1.5-0.5B-Chat" "ds_q25_15b /path/to/server/models/Qwen2.5-1.5B-Instruct" "ds_q25_7b /path/to/server/models/Qwen2.5-7B-Instruct"; do
  set -- $spec; [ -f "$2/config.json" ] || { echo "[$(date)] missing model $2" >> chain_designer_scale.log; date -Is > FAILED_$1; continue; }
  bash run_openreason_v4.sh $1 $2 prompts_designer_scale.jsonl 16384 8192
  echo "[$(date)] $1 finished" >> chain_designer_scale.log
done
date -Is > CHAIN_DESIGNER_SCALE_DONE
'''


def hidden():
    return {n: {"header": s["header"], "fields": [tuple(f) for f in s["fields"]], "truth": s["truth"]} for n, s in json.load(open(RS.OUT / "namehide/sources_hidden.json")).items()}


def prep():
    OUT.mkdir(parents=True, exist_ok=True); S = RS.load_sources(); H = hidden(); n = 0
    assert M.tmpl_hash().startswith(RS.FROZEN)
    with open(OUT / "prompts_designer_scale.jsonl", "w") as f:
        for l in open(ROOT / "experiments/results/obsschema_rt_openreason_v1/prompts.jsonl"): f.write(l if l.endswith("\n") else l + "\n"); n += 1
        for j in map(json.loads, open(RS.OUT / "prompts_scale.jsonl")):
            _, src, k = j["id"].split("|"); assert j["prompt"] == M.build_prompt(S[src], int(k))
            f.write(json.dumps({"id": f"real|{src}|{k}", "prompt": j["prompt"]}, ensure_ascii=False) + "\n"); n += 1
        for src in H:
            for k in range(M.NPRES): f.write(json.dumps({"id": f"hid|{src}|{k}", "prompt": M.build_prompt(H[src], k)}, ensure_ascii=False) + "\n"); n += 1
    (OUT / "run_openreason_v4.sh").write_text(RUN_V4); (OUT / "chain_designer_scale.sh").write_text(CHAIN)
    for f in ("prompts_designer_scale.jsonl", "run_openreason_v4.sh", "chain_designer_scale.sh"):
        subprocess.run(["scp", "-q", str(OUT / f), f"{HOST}:{W}/{f}"], check=True)
    print("prompt", n, "items (synthetic 80, real-name 36, masked-name 36), uploaded")


def launch():
    r = subprocess.run(SSH + [HOST, f"cd {W} && setsid -f bash chain_designer_scale.sh > chain_designer_scale.out 2>&1 < /dev/null; sleep 2; echo started"], capture_output=True, text=True, timeout=60)
    print(r.stdout.strip(), r.stderr.strip()[-200:])


def ba_rows(SRC, maps):
    return RS.rows(SRC, maps)


def score_tag(tag):
    outp = OUT / f"out_{tag}.jsonl"; subprocess.run(["scp", "-q", f"{HOST}:{W}/out_{tag}.jsonl", str(outp)], check=True)
    S = RS.load_sources(); H = hidden(); T, Lr, Lh, st = {}, {}, {}, {"n": 0, "length": 0, "syn_parsed": 0, "real_parsed": 0, "hid_parsed": 0}
    for r in map(json.loads, open(outp)):
        st["n"] += 1; st["length"] += r.get("finish_reason") == "length"; a = r["text"].split("</think>")[-1]; kind, x, y = r["id"].split("|")
        if kind == "obsschema":
            try: T.setdefault(x, {})[y] = L.parse(a); st["syn_parsed"] += 1
            except Exception: pass
        else:
            src = S if kind == "real" else H; D = Lr if kind == "real" else Lh
            try: D[(x, int(y))] = M.parse(a, len(src[x]["fields"])); st[f"{kind}_parsed"] += 1
            except Exception: D[(x, int(y))] = None
    for D, SRC in ((Lr, S), (Lh, H)):
        for n in SRC:
            for k in range(M.NPRES): D.setdefault((n, k), None)
    tp = OUT / f"transforms_{tag}.json"; tp.write_text(json.dumps(T, ensure_ascii=False))
    subprocess.run(["scp", "-q", str(tp), f"gpu-server-1:{RO}/transforms_{tag}.json"], check=True)
    r = subprocess.run(SSH + ["gpu-server-1", f"cd /path/to/server/work && python3 obsschema_rt_offline_v1.py eval {RO}/transforms_{tag}.json {tag} > {RO}/eval_{tag}.log 2>&1; echo rc=$?"], capture_output=True, text=True, timeout=7200)
    subprocess.run(["scp", "-q", f"gpu-server-1:{RO}/eval_{tag}.json", str(OUT / f"eval_{tag}.json")], check=True)
    E = json.load(open(OUT / f"eval_{tag}.json")); succ = {"LLM": 0, "LLM_OBF": 0}
    for gid, res in E["results"].items():
        for m in succ:
            v = [x.get(m, np.nan) for x in res.values()]
            succ[m] += int(any(m in x for x in res.values()) and float(np.nanmedian(v)) <= 1.2)
    Rr = ba_rows(S, Lr); Rh = ba_rows(H, Lh)
    B = RS.base_maps(S); R_base = {b: RS.rows(S, {(n, 0): B[b][n] for n in S}) for b in B}
    v, m = M.judge(Rr, R_base)
    return {"tag": tag, "model": MODELS[tag], "synthetic_success": succ, "n_groups": len(E["results"]), "ba_real": m["ba_llm"], "ba_hidden": M.ba(Rh), "delta_vs_best": m["delta"], "ci90": m["ci90"],
            "best_base": m["best_base"], "best_base_ba": m["ba_base"][m["best_base"]], "false_map_rate": m["false_map_rate"], "verdict_rule": v, "parse": st, "eval_rc": r.stdout.strip()}


def finalize():
    log = lambda s: print(time.strftime("[%F %T] ") + s, flush=True)
    for _ in range(24 * 12):
        r = subprocess.run(SSH + [HOST, f"test -f {W}/CHAIN_DESIGNER_SCALE_DONE && echo done"], capture_output=True, text=True, timeout=60)
        if "done" in r.stdout: break
        time.sleep(300)
    else: log("24 hours not completed, stopped"); sys.exit(1)
    res = {}
    for tag in MODELS:
        ok = subprocess.run(SSH + [HOST, f"test -f {W}/out_{tag}.jsonl.DONE && echo yes"], capture_output=True, text=True, timeout=60).stdout
        if "yes" not in ok: log(f"{tag} incomplete or failed, skip"); res[tag] = {"tag": tag, "failed": True}; continue
        res[tag] = score_tag(tag); log(json.dumps(res[tag], ensure_ascii=False)[:600])
    (OUT / "judge.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    summ = ";".join(f"{t}: 12 sources, real-name BA {x['ba_real']:.3f}, masked-name {x['ba_hidden']:.3f}, synthetic groups with real names {x['synthetic_success']['LLM']}/{x['n_groups']}, masked-name {x['synthetic_success']['LLM_OBF']}/{x['n_groups']}, parse {x['parse']}" if not x.get("failed") else f"{t}: incomplete" for t, x in res.items())
    ex("data", "--id", ID, "--metrics", json.dumps({t: ({k: x[k] for k in ("ba_real", "ba_hidden", "delta_vs_best", "ci90", "synthetic_success")} if not x.get("failed") else "failed") for t, x in res.items()}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"))
    p = res["ds_q15_05b"]
    if p.get("failed"): ex("note", "--id", ID, "The primary-endpoint model did not complete; no conclusion is drawn." + summ); return
    d, (lo, hi) = p["delta_vs_best"], p["ci90"]
    v = "holds" if lo > 0 and d >= 0.15 else ("direction only" if d > 0 else "does not hold")
    basis = f"Primary endpoint Qwen1.5-0.5B-Chat: 12 sources, real-name BA {p['ba_real']:.3f} versus best control {p['best_base']} {p['best_base_ba']:.3f}, Δ {d:+.3f}, 90% interval [{lo:+.3f}, {hi:+.3f}]. Report only: {summ}. Reference: R1 distillations 14B and 32B, 12 sources with real names 0.693 and 0.893, synthetic groups with real names 27/40 and 36/40."
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered." + basis, "--basis", basis,
       "--limitations", "one sample per prompt; the small models are chat versions without reasoning, a different family from the reasoning-distilled 14B and 32B; synthetic-mode scoring is offline replay.", "--next", "")
    log(f"Conclusion {v} {basis}")


if __name__ == "__main__":
    {"prep": prep, "launch": launch, "finalize": finalize}[sys.argv[1]]()
