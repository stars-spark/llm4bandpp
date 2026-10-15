#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Server side of obsschema-llm-v1 (adapting the interface to a new client; criteria in its pre-registration).
Setting: a new client reports per-window telemetry with the meaning of the estimator interface but its own field names, units and order (a foreign schema); the fields must be mapped back to the 15 interface features (choose a source field, multiply by a factor).
The foreign schemas are generated here deterministically: each schema names its 15 fields (two development and four test schemas, with different naming styles and units), the field order is shuffled by a per-schema seed, and the unit factors are in SCHEMAS.
Methods: the LLM (field names, evidence percentiles, interface definitions, reference percentiles); the LLM on the same schema with names replaced by field_01 and so on (ablation); distribution matching (per feature, the source field and candidate factor with the smallest log-percentile distance, Hungarian assignment); name matching (literal similarity of field and feature names plus unit snapping); the true mapping as upper bound.
Commands: groups (build groups and evidence), eval TRANSFORMS.json PHASE (evaluate every method). Calls come from the same data as obsrepair_v1, drawn with other seeds.
"""
import glob, json, math, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsrepair_v1 as R
OUT = os.path.expanduser("~/work/outputs/obsschema_v1")
TARGET = ["receiving rate (bit/s)", "packets received", "bytes received", "queuing delay (ms)", "mean one-way delay (ms, clock offset)", "minimum one-way delay (ms, clock offset)",
          "delay ratio", "mean minus minimum delay (ms)", "packet inter-arrival time (ms)", "jitter (ms)", "loss ratio (fraction)", "mean lost packets per loss event",
          "video packet share (fraction)", "audio packet share (fraction)", "probing packet share (fraction)"]
SCHEMAS = {
    "dev_a": [("recvRateKbps", 1e-3), ("packetsRecv", 1), ("bytesRecv", 1), ("queueDelaySec", 1e-3), ("oneWayDelaySec", 1e-3), ("minOneWayDelaySec", 1e-3), ("delayRatio", 1),
              ("delayAboveMinSec", 1e-3), ("interArrivalMs", 1), ("jitterMs", 1), ("lossPercent", 100), ("avgLostPerEvent", 1), ("videoPct", 100), ("audioPct", 100), ("probePct", 100)],
    "dev_b": [("rx_rate_bps", 1), ("rx_pkt_count", 1), ("rx_bits", 8), ("qdelay_ms", 1), ("owd_ms", 1), ("owd_min_ms", 1), ("owd_ratio", 1), ("owd_excess_ms", 1),
              ("iat_ms", 1), ("jitter_ms", 1), ("loss_frac", 1), ("lost_burst_avg", 1), ("frac_video", 1), ("frac_audio", 1), ("frac_probe", 1)],
    "test_c": [("goodput_mbps", 1e-6), ("pkts", 1), ("octets", 1), ("queuing_us", 1e3), ("latency_ms", 1), ("base_latency_ms", 1), ("latency_inflation", 1), ("latency_minus_base_us", 1e3),
               ("ia_gap_us", 1e3), ("ipdv_us", 1e3), ("plr_pct", 100), ("mean_burst_loss", 1), ("vid_share_pct", 100), ("aud_share_pct", 100), ("fec_probe_share_pct", 100)],
    "test_d": [("throughput_kibps", 1 / 1024), ("n_packets", 1), ("payload_kB", 1e-3), ("standing_queue_ms", 1), ("delay_ms", 1), ("delay_floor_ms", 1), ("delay_vs_floor", 1),
               ("delay_over_floor_ms", 1), ("arrival_spacing_ms", 1), ("delay_variation_ms", 1), ("drop_rate", 1), ("drops_per_episode", 1), ("media_video_ratio", 1), ("media_audio_ratio", 1), ("bwe_probe_ratio", 1)],
    "test_e": [("bitrate_in", 1), ("pkt_rx", 1), ("bytes_rx", 1), ("buffer_delay_s", 1e-3), ("ow_lat_s", 1e-3), ("ow_lat_min_s", 1e-3), ("lat_ratio", 1), ("lat_spread_s", 1e-3),
               ("gap_s", 1e-3), ("jit_s", 1e-3), ("lost_ratio", 1), ("lost_mean", 1), ("v_frac", 1), ("a_frac", 1), ("p_frac", 1)],
    "test_f": [("recv_kbit_per_s", 1e-3), ("count_pkts", 1), ("count_bits", 8), ("qdel_ms", 1), ("t_owd_ms", 1), ("t_owd_floor_ms", 1), ("owd_norm", 1), ("owd_minus_floor_ms", 1),
               ("pkt_interval_ms", 1), ("pdv_ms", 1), ("loss_permille", 1000), ("loss_run_mean", 1), ("share_video_pct", 100), ("share_audio_pct", 100), ("share_probe_pct", 100)],
    "test_g": [("recvBitrateKbps", 1e-3), ("packetCount", 1), ("payloadKiB", 1 / 1024), ("queueDelayUs", 1e3), ("oneWayDelayMs", 1), ("minOneWayDelayMs", 1), ("delayRatio", 1),
               ("delayAboveMinUs", 1e3), ("interArrivalUs", 1e3), ("jitterUs", 1e3), ("lossPercent", 100), ("avgLossBurst", 1), ("videoShare", 1), ("audioShare", 1), ("probeShare", 1)],
    "test_h": [("rtc_recv_bits_per_second", 1), ("rtc_recv_packets_total", 1), ("rtc_recv_bytes_total", 1), ("rtc_queue_delay_seconds", 1e-3), ("rtc_owd_milliseconds", 1),
               ("rtc_owd_min_milliseconds", 1), ("rtc_owd_ratio", 1), ("rtc_owd_excess_seconds", 1e-3), ("rtc_iat_seconds", 1e-3), ("rtc_jitter_seconds", 1e-3), ("rtc_loss_ratio", 1),
               ("rtc_loss_burst_mean", 1), ("rtc_video_fraction", 1), ("rtc_audio_fraction", 1), ("rtc_probe_fraction", 1)],
    "test_i": [("rcv_kbps", 1e-3), ("npk", 1), ("nbit", 8), ("qd_ms", 1), ("d_ms", 1), ("dmin_ms", 1), ("dr", 1), ("dx_ms", 1), ("iat_ms", 1), ("jit_ms", 1), ("plr_pm", 1000), ("lpe", 1),
               ("pv_pct", 100), ("pa_pct", 100), ("pp_pct", 100)],
    "test_j": [("Receive Throughput (Mbit/s)", 1e-6), ("Packets Received", 1), ("Data Received (kB)", 1e-3), ("Queueing Delay (s)", 1e-3), ("Latency (ms)", 1), ("Base Latency (ms)", 1),
               ("Latency Ratio", 1), ("Latency Above Base (ms)", 1), ("Mean Packet Gap (ms)", 1), ("Packet Gap Std Dev (ms)", 1), ("Packet Loss (%)", 100), ("Mean Packets Lost per Event", 1),
               ("Video Packets (%)", 100), ("Audio Packets (%)", 100), ("Probe Packets (%)", 100)],
}
PHASE = {"dev_a": "dev", "dev_b": "dev", "test_c": "test", "test_d": "test", "test_e": "test", "test_f": "test", "test_g": "test2", "test_h": "test2", "test_i": "test2", "test_j": "test2"}
FACTORS = [1, 1e3, 1e-3, 1e6, 1e-6, 8, 1 / 8, 100, 1 / 100, 1000 / 8, 8 / 1000, 1024, 1 / 1024]


def order(schema): return [int(x) for x in np.random.default_rng(sum(map(ord, schema))).permutation(15)]


def to_foreign(o, schema):
    """Interface observation (T, 150) to the foreign field matrix (T, 15, 10), fields in schema order."""
    sc = SCHEMAS[schema]; perm = order(schema); X = o.reshape(len(o), 15, 10)
    return np.stack([X[:, k, :] * sc[k][1] for k in perm], axis=1)


def from_mapping(F, mapping):
    """mapping: list of 15 entries, entry k is {"source": source field index, "scale": a} (interface value = source value x a); missing entries are set to 0."""
    T = F.shape[0]; X = np.zeros((T, 15, 10))
    for k, m in enumerate(mapping):
        if m is None or m.get("source") is None or not 0 <= int(m["source"]) < F.shape[1]: continue
        X[:, k, :] = F[:, int(m["source"]), :] * float(m.get("scale", 1.0))
    return X.reshape(T, 150)


def oracle(schema):
    perm = order(schema); sc = SCHEMAS[schema]; inv = {k: i for i, k in enumerate(perm)}
    return [{"source": inv[k], "scale": 1.0 / sc[k][1]} for k in range(15)]


def fstats(F_list):
    n = int(R.EV_SECONDS / R.STEP_S); X = np.concatenate([f[:n] for f in F_list]); out = []
    for j in range(X.shape[1]): out.append({"short": np.percentile(X[:, j, :5], [5, 25, 50, 75, 95]).round(6).tolist(), "long": np.percentile(X[:, j, 5:], [5, 25, 50, 75, 95]).round(6).tolist()})
    return out


def assign_min(C):
    """Minimum-cost assignment on a square matrix (Hungarian algorithm, plain numpy, O(n^3)), returns (rows, columns); checked against SciPy's linear_sum_assignment on random matrices, since the server environment has no SciPy."""
    C = np.asarray(C, float); n = C.shape[0]; INF = float("inf")
    u = np.zeros(n + 1); v = np.zeros(n + 1); p = np.zeros(n + 1, int); way = np.zeros(n + 1, int)
    for i in range(1, n + 1):
        p[0] = i; j0 = 0; minv = np.full(n + 1, INF); used = np.zeros(n + 1, bool)
        while True:
            used[j0] = True; i0 = p[j0]; delta = INF; j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = C[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]: minv[j] = cur; way[j] = j0
                    if minv[j] < delta: delta = minv[j]; j1 = j
            for j in range(n + 1):
                if used[j]: u[p[j]] += delta; v[j] -= delta
                else: minv[j] -= delta
            j0 = j1
            if p[j0] == 0: break
        while True:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
            if j0 == 0: break
    col_of_row = np.zeros(n, int)
    for j in range(1, n + 1): col_of_row[p[j] - 1] = j - 1
    return np.arange(n), col_of_row


def dist_match(ev, ref):
    """Distribution matching: cost = sum of absolute differences of log percentiles (short-window median, long-window median, long-window 95th percentile), minimised over source fields and candidate factors; Hungarian assignment."""
    sig = lambda q: np.array([q["short"][2], q["long"][2], q["long"][4]], float)
    lg = lambda v: np.sign(v) * np.log10(1 + np.abs(v))
    C = np.zeros((15, 15)); best_f = np.ones((15, 15))
    for k in range(15):
        t = lg(sig(ref[str(k)]))
        for j in range(15):
            costs = [np.abs(lg(sig(ev[j]) * f) - t).sum() for f in FACTORS]; i = int(np.argmin(costs)); C[k, j] = costs[i]; best_f[k, j] = FACTORS[i]
    rows, cols = assign_min(C); return [{"source": int(cols[list(rows).index(k)]), "scale": float(best_f[k, cols[list(rows).index(k)]])} for k in range(15)]


def name_match(names, ev, ref):
    """Name matching: Hungarian assignment on the literal similarity (difflib) of field and feature names; factors by unit snapping (the candidate factors of distribution matching, closest in log median)."""
    import difflib
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    S = np.array([[difflib.SequenceMatcher(None, norm(TARGET[k]), norm(n)).ratio() for n in names] for k in range(15)])
    rows, cols = assign_min(-S); out = []
    for k in range(15):
        j = int(cols[list(rows).index(k)]); a = np.median([ev[j]["short"][2], ev[j]["long"][2]]); b = np.median([ref[str(k)]["short"][2], ref[str(k)]["long"][2]])
        f = 1.0 if a <= 0 or b <= 0 else min(FACTORS, key=lambda c: abs(math.log10(a * c / b))); out.append({"source": j, "scale": float(f)})
    return out


def cmd_groups():
    """Per scenario three sets of 13 calls (one development, two test), shared by all schemas of a phase; only the calls used for the sensitivity test are excluded, overlap with the obsrepair groups is allowed (another experiment)."""
    os.makedirs(OUT, exist_ok=True); used = set(json.load(open(os.path.expanduser("~/work/outputs/obsrepair_v1/sens.json")))["calls"]); groups = []
    for di, d in enumerate(R.DIRS):
        files = [f for f in sorted(glob.glob(f"{R.SCEN}/{d}/*.json")) if f not in used]
        sets = {}
        for k, (ph, dr) in enumerate((("dev", 0), ("test", 0), ("test", 1))):
            sel = [str(x) for x in np.random.default_rng(20261402 + 100 * di + k).choice(files, 13, replace=False)]; files = [f for f in files if f not in sel]; sets[(ph, dr)] = sel
        for s in SCHEMAS:
            for dr in range(1 if PHASE[s] == "dev" else 2):
                sel = sets[(PHASE[s], dr)]; groups.append({"id": len(groups), "phase": PHASE[s], "scen": d, "schema": s, "draw": dr, "ev": sel[:3], "test": sel[3:]})
    ref = json.load(open(os.path.expanduser("~/work/outputs/obsrepair_v1/evidence.json")))["ref"]; ev = {}
    for g in groups:
        perm = order(g["schema"]); ev[str(g["id"])] = {"names": [SCHEMAS[g["schema"]][k][0] for k in perm], "stats": fstats([to_foreign(R.load(p)[0], g["schema"]) for p in g["ev"]])}
    json.dump({"groups": groups}, open(f"{OUT}/groups.json", "w")); json.dump({"ref": ref, "groups": ev}, open(f"{OUT}/evidence.json", "w")); print({p: sum(g["phase"] == p for g in groups) for p in ("dev", "test")})


def eval_job(a):
    g, maps = a; res = {}
    for p in g["test"]:
        o, tr = R.load(p); clean = R.mse(R.run_onnx(o), tr); F = to_foreign(o, g["schema"]); r = {}
        for m, mp in maps.items(): r[m] = R.mse(R.run_onnx(from_mapping(F, mp)), tr) / max(clean, 1e-12) if mp else float("nan")
        res[os.path.basename(p)] = r
    return g["id"], res


def cmd_eval(tpath, phase, tag=""):
    G = json.load(open(f"{OUT}/groups.json")); E = json.load(open(f"{OUT}/evidence.json")); T = json.load(open(tpath)); ref = E["ref"]; jobs = []
    for g in G["groups"]:
        if g["phase"] != phase: continue
        e = E["groups"][str(g["id"])]
        maps = {"ORACLE": oracle(g["schema"]), "DIST": dist_match(e["stats"], ref), "NAME": name_match(e["names"], e["stats"], ref)}
        for k, v in T.get(str(g["id"]), {}).items(): maps[k] = v
        jobs.append((g, maps))
    with ProcessPoolExecutor(40) as ex: rs = dict(ex.map(eval_job, jobs))
    json.dump({"results": {str(k): v for k, v in rs.items()}, "maps": {str(g["id"]): m for g, m in jobs}}, open(f"{OUT}/eval_{phase}{tag}.json", "w")); print("evaluated groups:", len(rs))


if __name__ == "__main__":
    {"groups": lambda: cmd_groups(), "eval": lambda: cmd_eval(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")}[sys.argv[1]]()
