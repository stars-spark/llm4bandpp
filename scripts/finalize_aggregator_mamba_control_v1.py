#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge of aggregator-mamba-control-v1, written before the results existed: waits for the evaluation marker of the main
criterion on the GPU server, copies the per-call evaluation files, reads them with the rule given in finalize_aggregator_mamba_control_v1_offline_v1.py and
registers the result; the single-seed result of the arm with the LLM was planned but not completed. One
instance only. finalize_aggregator_mamba_control_v1_offline_v1.py repeats the computation from the released files.
"""
import json, os, subprocess, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; RES = ROOT / "experiments/results/aggregator_mamba_control_v1"; RES.mkdir(parents=True, exist_ok=True)
H = "gpu-server-2"; EV = "/path/to/server/outputs/mamba_aggregator_eval"; EVL = "/path/to/server/outputs/mamba_aggregator_eval_llm"
MET = ["mse", "over", "under", "err"]; ORDER = ["High BW", "Low BW", "Fluctuating"]; SEED, NBOOT = 20260909, 10000
ssh = lambda c: subprocess.run(["ssh", "-o", "ConnectTimeout=30", H, c], capture_output=True, text=True).stdout
try: os.close(os.open(RES / "FINALIZER_LOCK", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
except FileExistsError: print("another finalizer holds the lock; exiting"); sys.exit(0)


def wait(path, hours):
    end = time.time() + hours * 3600
    while "OK" not in ssh(f"test -s {path} && echo OK"):
        if time.time() > end: return False
        time.sleep(300)
    return True


def load(files):
    arrs, scen = [], None
    for p in files:
        f = sorted(json.load(open(p))["files"], key=lambda r: r["file"]); arrs.append(np.array([[r[k] for k in MET] for r in f], dtype=np.float64)); s = np.array([r["scenario"] for r in f])
        assert scen is None or np.array_equal(scen, s); scen = s
    return np.stack(arrs), scen


def read(A, B, scen, multi):
    a, b = A.mean(0), B.mean(0); rng = np.random.default_rng(SEED); BI = {s: rng.integers(0, (scen == s).sum(), size=(NBOOT, (scen == s).sum())) for s in ORDER}; out = {}
    for s in ORDER + ["macro"]:
        out[s] = {}
        for j, k in enumerate(MET[:2]):
            if s == "macro":
                va = np.mean([a[scen == t][:, j].mean() for t in ORDER]); vb = np.mean([b[scen == t][:, j].mean() for t in ORDER])
                bs = np.mean([a[scen == t][:, j][BI[t]].mean(1) - b[scen == t][:, j][BI[t]].mean(1) for t in ORDER], axis=0)
                sd = np.std([np.mean([B[i][scen == t][:, j].mean() for t in ORDER]) for i in range(len(B))], ddof=1) if multi else None
            else:
                m = scen == s; va, vb = a[m][:, j].mean(), b[m][:, j].mean(); bs = a[m][:, j][BI[s]].mean(1) - b[m][:, j][BI[s]].mean(1)
                sd = np.std([B[i][m][:, j].mean() for i in range(len(B))], ddof=1) if multi else None
            dl = 2 * sd if multi else 0.0382 * abs(vb); d = va - vb; lo, hi = np.percentile(bs, [2.5, 97.5])
            rd = "better" if hi < 0 and abs(d) >= dl else ("worse" if lo > 0 and abs(d) >= dl else ("tie" if lo >= -dl and hi <= dl else "indistinguishable"))
            out[s][k] = {"mamba": float(va), "transformer": float(vb), "diff": float(d), "rel_pct": float(d / vb * 100), "ci95": [float(lo), float(hi)], "delta": float(dl), "reading": rd}
    return out


exp = ["/usr/bin/python3", str(ROOT / "scripts/exp.py")]
if not wait(f"{EV}/EVAL_COMPLETE_gpu-server-2.json", 30): print("no evaluation marker of the main criterion after 30 hours; exiting"); sys.exit(2)
for t in [f"{a}s{s}_50000.json" for a in ("MB", "NL") for s in (0, 1, 2)] + ["EVAL_COMPLETE_gpu-server-2.json"]:
    subprocess.run(["scp", "-q", "-o", "ConnectTimeout=30", f"{H}:{EV}/{t}", str(RES) + "/"], check=True)
A, scen = load([RES / f"MBs{s}_50000.json" for s in (0, 1, 2)]); B, scen2 = load([RES / f"NLs{s}_50000.json" for s in (0, 1, 2)]); assert np.array_equal(scen, scen2)
main = read(A, B, scen, True); rd = main["macro"]["mse"]["reading"]; verdict = "holds" if rd in ("tie", "worse") else ("does not hold" if rd == "better" else "inconclusive")
(RES / "result_main.json").write_text(json.dumps({"verdict": verdict, "readings": main}, ensure_ascii=False, indent=2))
line = lambda x: f"Mamba {x['mamba']:.3f} versus Transformer {x['transformer']:.3f}, difference {x['rel_pct']:+.2f}%, {x['reading']}"
subprocess.run(exp + ["data", "--id", "aggregator-mamba-control-v1", "--metrics", json.dumps({f"{s.replace(' ', '')}_{k}_{w}": main[s][k][w] for s in main for k in main[s] for w in ("mamba", "transformer")}),
                      "--artifact", str(RES / "result_main.json"), "--artifact", str(RES / "EVAL_COMPLETE_gpu-server-2.json")], check=True)
subprocess.run(exp + ["conclude", "--id", "aggregator-mamba-control-v1", "--verdict", verdict,
                      "--vs-criteria", "Decided by the pre-registered rule. Macro MSE:" + line(main["macro"]["mse"]) + f"; interval {main['macro']['mse']['ci95'][0]:.3f} to {main['macro']['mse']['ci95'][1]:.3f}, threshold {main['macro']['mse']['delta']:.3f}.",
                      "--basis", ";".join(f"{s} MSE:" + line(main[s]["mse"]) + f"; overestimation rate {main[s]['over']['reading']}" for s in ORDER),
                      "--limitations", "The primary criterion is run on the arm without the LLM (otherwise the same network), three seeds, 50k steps; the state-space block is a pure PyTorch implementation of a Mamba-style selective scan, not the official fused kernel; the aggregated sequence has only 15 tokens. The single-seed results of the arm with the LLM will be appended once complete.",
                      "--next", ""], check=True)
print("main criterion judged:", verdict)
if wait(f"{EVL}/EVAL_COMPLETE_gpu-server-2.json", 40):
    for t in ("MBLs0_50000.json", "LLMs0_50000.json"): subprocess.run(["scp", "-q", "-o", "ConnectTimeout=30", f"{H}:{EVL}/{t}", str(RES) + "/"], check=True)
    A, scen = load([RES / "MBLs0_50000.json"]); B, _ = load([RES / "LLMs0_50000.json"]); llm = read(A, B, scen, False); (RES / "result_llm_arm.json").write_text(json.dumps(llm, ensure_ascii=False, indent=2))
    subprocess.run(exp + ["data", "--id", "aggregator-mamba-control-v1", "--artifact", str(RES / "result_llm_arm.json"), "--note", "LLM arm, seed 0, report only. Macro MSE:" + line(llm["macro"]["mse"]) + "; low bandwidth:" + line(llm["Low BW"]["mse"]) + "."], check=True)
    print("LLM arm appended")
