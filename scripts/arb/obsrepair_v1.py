#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Server side of obsrepair-llm-v1 (repairing unit and collection errors in client telemetry): error catalogue, groups and evidence statistics, non-LLM repairs, and evaluation of the challenge baseline after repair (criteria in its pre-registration).
The challenge baseline is the ONNX file onnx_model_for_evaluation/baseline.onnx of the public Schaferct repository (the challenge's offline RL baseline model), run as in obsrepair_feas_v1 and arb_perstep_dump_v1 (one thread, LSTM state carried step by step).
Commands: sens N (sensitivity of the candidate held-out errors on development calls, as the median error ratio; writes sens.json); groups (draws calls as pre-registered and builds development, test and control groups; writes groups.json and the per-group evidence statistics evidence.json from the first 30 s of the first three calls); eval TRANSFORMS.json PHASE (repairs the evaluation calls of every group of that phase with every method and writes eval_<PHASE>.json).
Observation layout: dim = feature x 10 + window; windows 0 to 4 are the 60 ms windows, 5 to 9 the 600 ms windows.
The obsschema replays reuse its data loading, ONNX inference and evidence statistics; all of it needs the challenge calls.
"""
import glob, json, math, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
SCEN = os.path.expanduser("~/work/datasets/dt_stage_v1/validation/prepare_scenario"); NEW = os.path.expanduser("~/work/datasets/newscen_v1")
OUT = os.path.expanduser("~/work/outputs/obsrepair_v1"); ONNX = "/path/to/llm4band_conference/Schaferct/onnx_model_for_evaluation/baseline.onnx"
DIRS = ["high_bw_call", "low_bw_call", "high_fluctuating_bw", "low_fluctuating_bw"]; LEGIT = ["medium_bw_call", "4g_car", "4g_ped", "3g_tram", "3g_metro"]
DEV_FAULTS = ["F_kbps", "F_sec"]; CAND_TEST = ["F_bits", "F_off", "F_swap", "F_mbps", "F_us", "F_kB", "F_pktps"]
EV_CALLS, EV_SECONDS, STEP_S = 3, 30.0, 0.06
idx = lambda f: list(range(f * 10, f * 10 + 10))


def fault(o, name):
    o = o.copy()
    if name == "F_kbps": o[:, idx(0)] *= 1e-3
    elif name == "F_mbps": o[:, idx(0)] *= 1e-6
    elif name == "F_bits": o[:, idx(2)] *= 8
    elif name == "F_kB": o[:, idx(2)] *= 1e-3
    elif name == "F_sec":
        for f in (3, 4, 5, 7): o[:, idx(f)] *= 1e-3
    elif name == "F_us":
        for f in (3, 4, 5, 7): o[:, idx(f)] *= 1e3
    elif name == "F_off":
        for f in (3, 5): o[:, idx(f)] += 100.0
    elif name == "F_swap":
        for f in range(15): a = o[:, f * 10:f * 10 + 5].copy(); o[:, f * 10:f * 10 + 5] = o[:, f * 10 + 5:f * 10 + 10]; o[:, f * 10 + 5:f * 10 + 10] = a
    elif name == "F_pktps": o[:, f_short(1)] /= 0.06; o[:, f_long(1)] /= 0.6
    elif name != "CLEAN": raise ValueError(name)
    return o


def f_short(f): return list(range(f * 10, f * 10 + 5))
def f_long(f): return list(range(f * 10 + 5, f * 10 + 10))


def apply_ops(o, ops):
    """Repair specification: [{"feature": k, "windows": "all|short|long", "scale": a, "offset": b}, {"swap_windows": true}]; the swap is applied first, then scale and offset per feature."""
    o = o.copy()
    for op in ops:
        if op.get("swap_windows"):
            for f in range(15): a = o[:, f * 10:f * 10 + 5].copy(); o[:, f * 10:f * 10 + 5] = o[:, f * 10 + 5:f * 10 + 10]; o[:, f * 10 + 5:f * 10 + 10] = a
    for op in ops:
        if "feature" in op:
            k = int(op["feature"]); w = op.get("windows", "all"); cols = idx(k) if w == "all" else (f_short(k) if w == "short" else f_long(k))
            o[:, cols] = o[:, cols] * float(op.get("scale", 1.0)) + float(op.get("offset", 0.0))
    return o


def load(path): c = json.load(open(path)); return np.asarray(c["observations"], np.float64), np.asarray(c["true_capacity"], np.float64) / 1e6


def run_onnx(obs):
    import onnxruntime as ort
    so = ort.SessionOptions(); so.intra_op_num_threads = 1; so.inter_op_num_threads = 1
    s = ort.InferenceSession(ONNX, sess_options=so, providers=["CPUExecutionProvider"]); sh = tuple(s.get_inputs()[1].shape)
    h = np.zeros(sh, np.float32); c = np.zeros(sh, np.float32); pr = np.empty(len(obs), np.float32)
    for t in range(len(obs)):
        y, h, c = s.run(None, {"obs": obs[t:t + 1].reshape(1, 1, -1).astype(np.float32), "hidden_states": h, "cell_states": c}); pr[t] = y[0, 0, 0]
    return pr / 1e6


def mse(pred, tr): m = np.isfinite(tr); return float(np.mean((pred[m] - tr[m]) ** 2))


def stats(obs_list):
    """Evidence statistics: 5th, 25th, 50th, 75th and 95th percentiles of every feature, short and long windows separately (first 30 s of each call only)."""
    n = int(EV_SECONDS / STEP_S); X = np.concatenate([o[:n] for o in obs_list]); out = {}
    for f in range(15):
        out[str(f)] = {"short": np.percentile(X[:, f_short(f)], [5, 25, 50, 75, 95]).round(6).tolist(), "long": np.percentile(X[:, f_long(f)], [5, 25, 50, 75, 95]).round(6).tolist()}
    return out


SNAP_1000 = [1e3, 1e-3, 1e6, 1e-6]; SNAP_ALL = SNAP_1000 + [8.0, 1 / 8, 100.0, 1 / 100]


def snap(ev, ref, factors):
    """Unit snapping: when the log of the ratio between the evidence median and the reference median of a feature (all windows) is within 0.2 of the log of a candidate factor, correct by that factor."""
    ops = []
    for f in range(15):
        a = np.median(ev[str(f)]["short"][2:3] + ev[str(f)]["long"][2:3]); b = np.median(ref[str(f)]["short"][2:3] + ref[str(f)]["long"][2:3])
        if a <= 0 or b <= 0: continue
        r = math.log10(a / b); best = min(factors, key=lambda c: abs(r - math.log10(c)))
        if abs(r - math.log10(best)) <= 0.2: ops.append({"feature": f, "windows": "all", "scale": 1.0 / best})
    return ops


def hand(ev, ref):
    """Our rule-based consistency check, designed on the two error types of the development groups before the test: correct the rate when rate and byte count disagree by about 1000, and change seconds to milliseconds when queuing delay and minimum delay are both below 1."""
    ops = []
    rate = ev["0"]["long"][2]; byts = ev["2"]["long"][2]; implied = byts * 8 / 0.6
    if implied > 0 and rate > 0:
        r = math.log10(rate / implied)
        if abs(r + 3) <= 0.3: ops.append({"feature": 0, "windows": "all", "scale": 1e3})
        elif abs(r - 3) <= 0.3: ops.append({"feature": 0, "windows": "all", "scale": 1e-3})
    if ev["3"]["long"][2] < 1.0 and ev["5"]["long"][2] < 1.0 and ref["5"]["long"][2] > 5.0:
        for f in (3, 4, 5, 7): ops.append({"feature": f, "windows": "all", "scale": 1e3})
    return ops


def qn_apply(o, ev_raw_q, ref_q):
    out = o.copy()
    for d in range(o.shape[1]):
        if not np.allclose(ev_raw_q[d], ev_raw_q[d][0]): out[:, d] = np.interp(o[:, d], ev_raw_q[d], ref_q[d])
    return out


def sens_job(a):
    p, names = a; o, tr = load(p); base = mse(run_onnx(o), tr); return {n: mse(run_onnx(fault(o, n)), tr) / max(base, 1e-12) for n in names}


def cmd_sens(n):
    rng = np.random.default_rng(20261002); calls = [f for d in DIRS for f in rng.choice(sorted(glob.glob(f"{SCEN}/{d}/*.json")), n, replace=False)]
    with ProcessPoolExecutor(40) as ex: rs = list(ex.map(sens_job, [(p, CAND_TEST) for p in calls]))
    out = {k: float(np.median([r[k] for r in rs])) for k in CAND_TEST}; os.makedirs(OUT, exist_ok=True); json.dump({"median_ratio": out, "n": len(rs), "calls": list(map(str, calls))}, open(f"{OUT}/sens.json", "w")); print(out)


def cmd_groups():
    reg = json.load(open(f"{OUT}/registered_faults.json")); test_faults = reg["test_faults"]; os.makedirs(OUT, exist_ok=True)
    sens_calls = set(json.load(open(f"{OUT}/sens.json"))["calls"]); used = set(sens_calls); groups = []
    def pick(files, k, seed):
        files = [f for f in files if f not in used]; sel = list(np.random.default_rng(seed).choice(files, k, replace=False)); used.update(sel); return [str(x) for x in sel]
    for di, d in enumerate(DIRS):
        files = sorted(glob.glob(f"{SCEN}/{d}/*.json"))
        dev = pick(files, 13, 20261003 + di)
        for fa in DEV_FAULTS + ["CLEAN"]: groups.append({"phase": "dev", "scen": d, "fault": fa, "draw": 0, "ev": dev[:EV_CALLS], "test": dev[EV_CALLS:]})
        for dr in range(2):
            t = pick(files, 13, 20261103 + 10 * di + dr)
            for fa in test_faults + ["CLEAN"]: groups.append({"phase": "test", "scen": d, "fault": fa, "draw": dr, "ev": t[:EV_CALLS], "test": t[EV_CALLS:]})
    for li, d in enumerate(LEGIT):
        files = sorted(glob.glob(f"{NEW}/{d}/*.json"))
        for dr in range(2):
            t = pick(files, 13, 20261203 + 10 * li + dr); groups.append({"phase": "test", "scen": d, "fault": "LEGIT", "draw": dr, "ev": t[:EV_CALLS], "test": t[EV_CALLS:]})
    ref_calls = pick([f for d in DIRS for f in sorted(glob.glob(f"{SCEN}/{d}/*.json"))], 120, 20261303)
    ref = stats([load(p)[0] for p in ref_calls])
    ev = {}
    for gi, g in enumerate(groups):
        g["id"] = gi; ev[str(gi)] = stats([fault(load(p)[0], g["fault"] if g["fault"] not in ("LEGIT",) else "CLEAN") for p in g["ev"]])
    json.dump({"groups": groups, "ref_calls": ref_calls, "test_faults": test_faults}, open(f"{OUT}/groups.json", "w")); json.dump({"ref": ref, "groups": ev}, open(f"{OUT}/evidence.json", "w"))
    print({ph: sum(g["phase"] == ph for g in groups) for ph in ("dev", "test")})


def eval_job(a):
    g, methods, refq = a; fa = g["fault"] if g["fault"] != "LEGIT" else "CLEAN"; res = {}
    evq = np.percentile(np.concatenate([fault(load(p)[0], fa)[: int(EV_SECONDS / STEP_S)] for p in g["ev"]]), np.linspace(1, 99, 21), axis=0).T
    for p in g["test"]:
        o, tr = load(p); clean = mse(run_onnx(o), tr); of = fault(o, fa); r = {}
        for m, ops in methods.items(): r[m] = mse(run_onnx(apply_ops(of, ops)), tr) / max(clean, 1e-12)
        r["QN"] = mse(run_onnx(qn_apply(of, evq, refq)), tr) / max(clean, 1e-12); res[os.path.basename(p)] = r
    return g["id"], res


def cmd_eval(tpath, phase, tag=""):
    G = json.load(open(f"{OUT}/groups.json")); E = json.load(open(f"{OUT}/evidence.json")); T = json.load(open(tpath)); ref = E["ref"]
    refq = np.percentile(np.concatenate([load(p)[0][: int(EV_SECONDS / STEP_S)] for p in G["ref_calls"]]), np.linspace(1, 99, 21), axis=0).T
    jobs = []
    for g in G["groups"]:
        if g["phase"] != phase: continue
        ev = E["groups"][str(g["id"])]
        m = {"NONE": [], "SNAP1000": snap(ev, ref, SNAP_1000), "SNAPALL": snap(ev, ref, SNAP_ALL), "HAND": hand(ev, ref), "LLM": T.get(str(g["id"]), {}).get("ops", [])}
        jobs.append((g, m, refq))
    with ProcessPoolExecutor(40) as ex: rs = dict(ex.map(eval_job, jobs))
    ops_used = {str(g["id"]): {k: v for k, v in m.items()} for g, m, _ in jobs}
    json.dump({"results": {str(k): v for k, v in rs.items()}, "ops": ops_used}, open(f"{OUT}/eval_{phase}{tag}.json", "w")); print("evaluated groups:", len(rs), "group")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "sens": cmd_sens(int(sys.argv[2]))
    elif c == "groups": cmd_groups()
    elif c == "eval": cmd_eval(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
