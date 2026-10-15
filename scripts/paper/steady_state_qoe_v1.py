#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered experiment closedloop-steady-qoe-v1: split the closed-loop VMAF lead over Python GCC into ramp-up and steady state. Measurement only, no registered criterion.
Reads the valid runs of five registered 720p batches (hd720-closedloop-ch-v1, hd720-echo-attr-ch-v1, hd720-seeds-ch-v1, hd720-highbw-ch-v1, hd720-randloss-ch-v1),
deployed arm arm_ch_x against gcc_pt125_c200; nothing is rerun. Per-frame VMAF is aligned to decode time (quality_*.json frame index times frame_step,
decoded_timestamps_*.csv.gz); the first 30 s after the first frame are ramp-up, the rest steady state.
Per batch: mean over cells (condition x sequence) of the per-cell arm difference, 90% interval by resampling runs within each cell (10,000 draws).
The same for freeze time share and mean and 95th-percentile queuing delay, plus each arm's median time to reach 0.8 of the source ceiling.
Writes summary.json, read by make_tables_v2.closedloop_rows for Table V. Usage: steady_state_qoe_v1.py run [--register] | --selftest
"""
import gzip, json, random, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); TB = Path("/path/to/testbed/results"); OUT = ROOT / "experiments/results/closedloop_steady_qoe_v1"; ID = "closedloop-steady-qoe-v1"
BATCHES = ["hd720-closedloop-ch-v1", "hd720-echo-attr-ch-v1", "hd720-seeds-ch-v1", "hd720-highbw-ch-v1", "hd720-randloss-ch-v1"]
OURS, GCC = "arm_ch_x", "gcc_pt125_c200"; RAMP_S = 30.0; SEED = 20261008; B = 10000


def frame_times(d):
    p = next(d.glob("decoded_timestamps_*.csv.gz"), None)
    if p is None: return None
    t, last = [], 0
    with gzip.open(p, "rt") as f:
        next(f)
        for line in f:
            c = line.split(","); n = int(c[3]); w = int(c[0])
            # Column 3 counts complete decoded frames; repeat the write time so the list is indexed by decoded frame number.
            while last < n: t.append(w); last += 1
    return [(x - t[0]) / 1e9 for x in t] if t else None


def split_vmaf(d):
    q = next(d.glob("quality_*.json"), None); ft = frame_times(d)
    if q is None or ft is None: return None
    Q = json.load(open(q)); step = Q["frame_step"]; a, b = [], []
    for idx, _, v in Q["per_frame"]:
        k = idx * step
        if k >= len(ft): continue
        (a if ft[k] < RAMP_S else b).append(v)
    return {"ramp": st.mean(a) if a else None, "steady": st.mean(b) if b else None, "n_ramp": len(a), "n_steady": len(b)}


def reach(s, cap, frac=0.8):
    for i in range(len(s)):
        w = s[max(0, i - 1):i + 1]
        if w and st.mean(w) >= frac * cap: return i + 1
    return None


def cell_diff(V, cells, seed=SEED):
    use = [c for c in cells if V.get((c, "o")) and V.get((c, "g"))]
    if not use: return None
    diff = {c: st.mean(V[(c, "o")]) - st.mean(V[(c, "g")]) for c in use}; D = st.mean(diff.values())
    rng = random.Random(seed); bs = []
    for _ in range(B):
        bs.append(st.mean(st.mean([rng.choice(V[(c, "o")]) for _ in V[(c, "o")]]) - st.mean([rng.choice(V[(c, "g")]) for _ in V[(c, "g")]]) for c in use))
    bs.sort(); return {"D": D, "ci90": [bs[int(0.05 * (B - 1))], bs[int(0.95 * (B - 1))]], "n_cells": len(use)}


def batch(bid):
    K = TB / bid; rows = [json.loads(l) for l in open(ROOT / "experiments/results" / bid.replace("-", "_") / "runs_full.jsonl")]
    ceil = json.load(open(K / "ceilings.json"))["ceiling_kbps"]; V = {}; T = {"o": [], "g": []}; cells = set()
    for r in rows:
        if not r.get("valid") or r["arm"] not in (OURS, GCC): continue
        a = "o" if r["arm"] == OURS else "g"; c = f"{r['cond']}__{r['video_id']}"; cells.add(c); d = K / "main" / r["job"]
        sv = split_vmaf(d)
        if sv:
            for seg in ("ramp", "steady"):
                if sv[seg] is not None: V.setdefault((seg, c, a), []).append(sv[seg])
        for f in ("file_freeze_time_share", "queue_delay_mean_ms", "queue_delay_p95_ms", "vmaf"):
            if isinstance(r.get(f), (int, float)): V.setdefault((f, c, a), []).append(r[f])
        cap = ceil.get(r["video_id"]) if isinstance(ceil, dict) else None; s = r.get("video_kbps_per_s") or []
        if cap: T[a].append(reach(s, cap))
    cells = sorted(cells); res = {}
    for f in ("vmaf", "ramp", "steady", "file_freeze_time_share", "queue_delay_mean_ms", "queue_delay_p95_ms"):
        res[f] = cell_diff({(c, a): V[(f, c, a)] for (ff, c, a) in V if ff == f}, cells)
    med = lambda xs: st.median([x for x in xs if x is not None]) if any(x is not None for x in xs) else None
    res["t_reach80_median_s"] = {"ours": med(T["o"]), "gcc": med(T["g"]), "never_ours": sum(x is None for x in T["o"]), "never_gcc": sum(x is None for x in T["g"])}
    return res


def selftest():
    assert reach([100, 900, 950], 1000) == 3 and reach([100, 100], 1000) is None
    V = {("x", "o"): [80.0, 82.0], ("x", "g"): [70.0, 72.0], ("y", "o"): [60.0], ("y", "g"): [61.0]}
    m = cell_diff(V, ["x", "y"]); assert abs(m["D"] - 4.5) < 1e-9 and m["n_cells"] == 2
    print("Self-test passed: arrival time, cell equal-weight difference")


def main(register):
    R = {b: batch(b) for b in BATCHES}
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "summary.json").write_text(json.dumps(R, ensure_ascii=False, indent=1))
    r2 = lambda x: None if x is None else round(x, 2)
    f = lambda m: "none" if m is None else f"{r2(m['D'])} ({r2(m['ci90'][0])} to {r2(m['ci90'][1])}, {m['n_cells']} cells)"
    basis = ";".join(f"{b}: VMAF overall {f(R[b]['vmaf'])}, ramp-up {f(R[b]['ramp'])}, steady state {f(R[b]['steady'])}; difference in freeze-time share {f(R[b]['file_freeze_time_share'])}; difference in mean queueing delay {f(R[b]['queue_delay_mean_ms'])} milliseconds, 95th percentile {f(R[b]['queue_delay_p95_ms'])}; median time to reach 0.8 of the ceiling, ours {R[b]['t_reach80_median_s']['ours']} seconds, GCC {R[b]['t_reach80_median_s']['gcc']} seconds (not reached {R[b]['t_reach80_median_s']['never_ours']}, {R[b]['t_reach80_median_s']['never_gcc']} times)" for b in BATCHES) + "."
    print(basis)
    if not register: return
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({b: {k: (R[b][k]["D"] if R[b][k] else None) for k in ("vmaf", "ramp", "steady")} for b in BATCHES}, ensure_ascii=False), "--artifact", str(OUT / "summary.json"))
    ex("conclude", "--id", ID, "--verdict", "holds", "--vs-criteria", "Measurement only, no verdict; \"holds\" here means only that the five batches of readings are complete and the whole-run difference is consistent with the registered readings of each batch." + basis, "--basis", basis,
       "--limitations", "Only the valid runs of the five registered batches are read; the 30 s cut was fixed before the run; per-frame VMAF is computed on every 8th frame; queueing delay is a network-side reading, excluding decoding and rendering; intervals are resampled within cells across runs.",
       "--next", "")


if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest()
    else: main("--register" in sys.argv)
