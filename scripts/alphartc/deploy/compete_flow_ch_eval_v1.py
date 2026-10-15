#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for batch compete-flow-ch-v1: the deployed system (deployed estimator with probing envelope v6) shares a bottleneck with one TCP CUBIC flow (2 and 3 Mbps) or one GCC call (2 Mbps), against Python GCC called every 200 ms.
Main endpoint: the main call's share of the bottleneck, deployed minus GCC, averaged over the three conditions; non-inferiority margin 0.10 with a safety line against squeezing the competitor; the no-LLM multi-scale estimator with envelope v6 is report-only.
Usage: compete_flow_ch_eval_v1.py jobs | caljobs LABEL | calcheck LABEL | judge [--selftest]
"""
import csv, gzip, hashlib, json, random, re, shutil, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); sys.path.insert(0, str(ROOT / "scripts/alphartc"))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_run_metrics_v1 as RM  # noqa: E402
import eval_staleness_run as E  # noqa: E402
ID = "compete-flow-ch-v1"; K = Path("/path/to/testbed/results/compete-flow-ch-v1"); MAINK = K / "main"; LOCAL = ROOT / "experiments/results/compete_flow_ch_v1"
K_V1 = Path("/path/to/testbed/results/compete-flow-nl-v1")
COND = {"T2": ("hd_c2", "tcp"), "T3": ("hd_c3", "tcp"), "G2": ("hd_c2", "gcc")}; WIN = (40.0, 90.0); NI, SAFE = -0.10, 0.15
NET_REASONS_ONLY_QUALITY = ("Missing quality score", "OCR in-range fraction below 0.9", "VMAF not computed")
V11 = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v11.sh"


def comp_env(kind, layout):
    e = {"STALENESS_COMPETITOR": kind, "STALENESS_COMP_START_S": "30", "STALENESS_COMP_STOP_S": "90"}
    if kind == "gcc": e.update({"STALENESS_COMP_ESTIMATOR": "gcc_pt125_c200", "STALENESS_COMP_SOURCE_FILE": H.source_of("kristenandsara", layout)})
    return e


def build_jobs():
    C = json.load(open(H.K / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []; order = list(H.ARMS); blk = 0
    for rep in range(1, 4):
        for c, (prof, kind) in COND.items():
            rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
            for a in rot:
                arm = H.ARMS[a]
                J.append({"cond": f"{c}__johnny__{a}__r{rep}", "arm": arm, "profile": str(H.P / f"{prof}.profile"), "rep": rep, "video_id": "johnny", "queue": H.queue_of(prof),
                          "source": H.source_of("johnny", layout), "env": {**H.arm_env(arm), **comp_env(kind, layout)}, **({"pin_pair": 1} if arm in RM.LLM_ARMS else {})})
    MAINK.mkdir(parents=True, exist_ok=True); s = H.spec(ID, MAINK, J, ROOT / "logs/compete_ch_sched.log", ly); (MAINK / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
    print("competing primary batch job", len(J)); return s


def build_caljobs(label):
    """Write calibration jobs K1 to K5; LABEL is tool (tool check before the batch) or formal (calibration between main and competition batches)."""
    C = json.load(open(H.K / "contents.json")); layout, ly = C["layout"], C["label_y"]; src = H.source_of("johnny", layout); D = K / f"calib_{label}"
    fx = lambda bps: {"BWE_RECEIVER_FIXED_BPS": str(bps)}
    J = [{"cond": "K1", "arm": "fixed_env", "profile": str(H.P / "hd_c2.profile"), "rep": 1, "video_id": "johnny", "queue": 53, "source": src, "env": {**fx(300000), **comp_env("tcp", layout)}},
         {"cond": "K2", "arm": "fixed_env", "profile": str(H.P / "hd_c2.profile"), "rep": 1, "video_id": "johnny", "queue": 53, "source": src, "env": {**fx(1500000), **comp_env("tcp", layout)}},
         {"cond": "K3", "arm": H.GCC, "profile": str(H.P / "hd_c2.profile"), "rep": 1, "video_id": "johnny", "queue": 53, "source": src, "env": comp_env("gcc", layout)},
         {"cond": "K4", "arm": H.PP, "profile": str(H.P / "hd_c2.profile"), "rep": 1, "video_id": "johnny", "queue": 53, "source": src, "env": {**H.X_ENV, **comp_env("tcp", layout)}},
         {"cond": "K5_v12", "arm": "fixed_env", "profile": str(H.P / "hd_c2.profile"), "rep": 1, "video_id": "johnny", "queue": 53, "source": src, "env": {**fx(1500000), "STALENESS_CAPTURE_MEDIA": "0"},
          "pin_pair": 2}]
    s = H.spec(f"{ID}-calib-{label}", D, J, ROOT / f"logs/compete_calib_{label}_sched.log", ly, pairs=(1, 2))
    s5 = H.spec(f"{ID}-calib-{label}-v11", D, [{"cond": "K5_v11", "arm": "fixed_env", "profile": str(H.P / "hd_c2.profile"), "rep": 1, "video_id": "johnny", "queue": 53, "source": src,
                                                 "env": {**fx(1500000), "STALENESS_CAPTURE_MEDIA": "0", "STALENESS_POLICY": "v2", "STALENESS_REQUIRE_GSO_SEGS": ""}}], ROOT / f"logs/compete_calib_{label}_sched.log", ly, pairs=(2,))
    s5["runner"] = str(V11); s5["media"] = False
    D.mkdir(parents=True, exist_ok=True); (D / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); (D / "jobs_v11.json").write_text(json.dumps(s5, ensure_ascii=False, indent=1))
    print("calibration job", len(J) + 1, D)


def window_ms(t0): return t0 + WIN[0] * 1000.0, t0 + WIN[1] * 1000.0


def video_in_window(netlog, t0, a=WIN[0], b=WIN[1]):
    pk = E.load_packets(str(netlog)); fid = E.load_fid_groups(str(netlog)); prim = {p for p, _ in fid}; rtx = {r for _, r in fid}
    lo, hi = t0 + a * 1000.0, t0 + b * 1000.0
    pv = [p for p in pk if p["ssrc"] in prim and lo <= p["arrival_ms"] < hi]; px = [p for p in pk if p["ssrc"] in rtx and lo <= p["arrival_ms"] < hi]
    dur = (hi - lo) / 1000.0; raw_min = {}
    for p in pk: raw_min[p["ssrc"]] = min(raw_min.get(p["ssrc"], 1e18), p["arrival_ms"] - p["send_ms"])
    qd = [max(0.0, p["arrival_ms"] - p["send_ms"] - raw_min[p["ssrc"]]) for p in pv]
    return {"kbps": sum(p["payload_bytes"] for p in pv) * 8 / dur / 1000.0, "rtx_kbps": sum(p["payload_bytes"] for p in px) * 8 / dur / 1000.0, "n": len(pv),
            "loss_rate": E.count_loss(pv)["loss_rate"] if len(pv) > 1 else None, "qdelay_mean_ms": st.mean(qd) if qd else None, "qdelay_p95_ms": E.percentile(qd, 95) if qd else None}


def tcp_in_window(recv_path, send_path, t0):
    lo, hi = window_ms(t0); R = [r for r in RM.jl(recv_path) if "recv_bytes" in r and "t_ms" in r]; S = RM.jl(send_path)
    out = {"tcp_connected": any(x.get("event") == "connected" for x in S), "tcp_cc": next((x.get("cc") for x in S if x.get("event") == "connected"), None)}
    sel = [i for i, r in enumerate(R) if lo < r["t_ms"] <= hi]
    if not sel or sel[0] == 0: out["tcp_kbps"] = 0.0 if out["tcp_connected"] else None; return out
    span = (R[sel[-1]]["t_ms"] - R[sel[0] - 1]["t_ms"]) / 1000.0; out["tcp_kbps"] = sum(R[i]["recv_bytes"] for i in sel) * 8 / span / 1000.0
    ti = [x for x in S if "tcp_info" in x and "t_ms" in x and lo <= x["t_ms"] <= hi]
    if ti: out.update({"tcp_retrans_in_window": ti[-1]["tcp_info"].get("total_retrans", 0) - ti[0]["tcp_info"].get("total_retrans", 0), "tcp_rtt_ms_median": st.median(x["tcp_info"].get("rtt_us", 0) / 1000 for x in ti),
                       "tcp_cwnd_median": st.median(x["tcp_info"].get("snd_cwnd", 0) for x in ti),
                       "tcp_cwr_or_loss_samples": sum(1 for x in ti if x["tcp_info"].get("ca_state") in (2, 3, 4))})
    return out


def shape_tcp(comp_shape):
    """Parse the shaping snapshot at the end of the competition window: port-5201 TCP and UDP rule counters, netem drops and class 10:10 sent counts."""
    out = {}
    if comp_shape is None or not Path(comp_shape).is_file(): return out
    txt = Path(comp_shape).read_text(errors="replace")
    for l in txt.splitlines():
        x = l.split()
        if "dpt:5201" in l and len(x) > 2 and x[0].isdigit(): out["tcp_rule_pkts"] = int(x[0]); out["tcp_rule_bytes"] = int(x[1])
        if "CLASSIFY" in l and " udp " in f" {l} " and len(x) > 2 and x[0].isdigit(): out["udp_rule_pkts"] = int(x[0]); out["udp_rule_bytes"] = int(x[1])
    q = re.search(r"qdisc netem 100: .*?\n\s*Sent \d+ bytes \d+ pkt \(dropped (\d+)", txt)
    if q: out["netem_dropped"] = int(q.group(1))
    m = re.search(r"class htb 10:10 .*?\n\s*Sent (\d+) bytes (\d+) pkt", txt)
    if m: out["class1010_bytes"] = int(m.group(1)); out["class1010_pkts"] = int(m.group(2))
    if out.get("tcp_rule_pkts"): out["tcp_avg_pkt_bytes"] = out["tcp_rule_bytes"] / out["tcp_rule_pkts"]
    return out


def file_window_vmaf(d, tag, t0, step=8):
    q = d / f"quality_{tag}.json"; dts = RM.first(d, f"decoded_timestamps_{tag}.csv*")
    if not q.is_file() or dts is None: return {}
    Q = json.load(open(q)); pf = Q.get("per_frame")
    if not pf: return {}
    times = []; prev = 0
    with RM.opn(dts) as f:
        for r in csv.DictReader(f):
            c = int(r["complete_frames"]); t = int(r["wall_time_ns"]) / 1e6
            if c > prev: times += [t] * (c - prev); prev = c
    lo, hi = window_ms(t0); xs = [v for i, lab, v in pf if i * step < len(times) and lo <= times[i * step] < hi]
    return {"vmaf_window": st.mean(xs) if xs else None, "vmaf_window_frames": len(xs)}


def recovery_s(rate, a=20, b=30, after=90, frac=0.9, win=5):
    if len(rate) < after + win: return None
    ref = st.mean(rate[a:b]);
    for s in range(after + win - 1, len(rate)):
        if st.mean(rate[s - win + 1:s + 1]) >= frac * ref: return s + 1 - after
    return None


def comp_metrics(d, tag, arm, cond, kind, ceiling):
    r = RM.run_metrics(d, tag, arm, COND.get(cond, ("hd_c2",))[0] if cond in COND else cond, ceiling)
    net_bad = [x for x in r["invalid_reasons"] if x not in NET_REASONS_ONLY_QUALITY]
    t0 = r.get("shape_t0_ms"); net = RM.first(d, f"network_{tag}.log*")
    if t0 is None or net is None: r["share_valid"] = False; r["share_invalid_reasons"] = net_bad + ["Missing shaping start or network log"]; return r
    r.update({"win_" + k: v for k, v in video_in_window(net, t0).items()})
    if kind == "tcp":
        r.update(tcp_in_window(RM.first(d, f"bg_tcp_recv_{tag}.jsonl"), RM.first(d, f"bg_tcp_send_{tag}.jsonl"), t0)); c = r.get("tcp_kbps")
        if not r.get("tcp_connected") or not c: net_bad.append("competitor TCP not connected or no bytes in window")
    elif kind == "gcc":
        cn = RM.first(d, f"comp_network_{tag}.log*"); c = None
        if cn is not None:
            try: cw = video_in_window(cn, t0); c = cw["kbps"]; r.update({"comp_" + k: v for k, v in cw.items()})
            except Exception as e: r["comp_error"] = repr(e)[:120]
            try:
                cr = RM.per_second_video(cn, t0); r["comp_kbps_per_s"] = [round(x, 1) for x in cr]
                r["comp_first5_kbps"] = st.mean(cr[31:36]) if len(cr) > 36 else None; r["comp_last20_kbps"] = st.mean(cr[70:90]) if len(cr) >= 90 else None
            except Exception: pass
        if not c: net_bad.append("no video within the competition call window")
    else: c = None
    r["competitor_kbps"] = c
    v = r.get("win_kbps")
    if v is not None and c is not None and v + c > 0: r["share"] = v / (v + c); r["jain"] = (v + c) ** 2 / (2 * (v * v + c * c)) if (v or c) else None
    else: net_bad.append("share cannot be computed")
    r.update(shape_tcp(RM.first(d, f"comp_shape_{tag}.log"))); r.update(file_window_vmaf(Path(d), tag, t0))
    if arm != H.GCC:
        r.update(H.env6_check(d, tag))
        if not r["env6_ok"]: net_bad.append("probing envelope v6 check did not pass:" + ";".join(r["env6_reasons"]))
    if r.get("video_kbps_per_s"): r["recovery_s"] = recovery_s(r["video_kbps_per_s"])
    r["share_valid"] = not net_bad; r["share_invalid_reasons"] = net_bad
    return r


def judge(Sh, conds=tuple(COND), arm=H.PP, ref=H.GCC, seed=H.SEED, B=H.B):
    all_invalid = [c for c in conds if not Sh.get((c, arm))]
    usable = [c for c in conds if Sh.get((c, arm)) and Sh.get((c, ref))]; dropped = [c for c in conds if Sh.get((c, arm)) and not Sh.get((c, ref))]
    diff = {c: st.mean(Sh[(c, arm)]) - st.mean(Sh[(c, ref)]) for c in usable}; S = st.mean(diff.values()) if diff else float("nan")
    rng = random.Random(seed); boots = []
    for _ in range(B if usable else 0):
        tot = 0.0
        for c in usable:
            a, b = Sh[(c, arm)], Sh[(c, ref)]; tot += sum(rng.choice(a) for _ in a) / len(a) - sum(rng.choice(b) for _ in b) / len(b)
        boots.append(tot / len(usable))
    boots.sort(); lo = boots[int(0.05 * (len(boots) - 1))] if boots else float("nan"); hi = boots[int(0.95 * (len(boots) - 1))] if boots else float("nan")
    squeeze = [c for c, x in diff.items() if x > SAFE]; safety = bool(squeeze or all_invalid)
    if len(usable) < 2 and not safety: v = "inconclusive"
    elif safety or not (S > NI): v = "does not hold"
    elif lo > NI: v = "holds"
    else: v = "direction only"
    return v, {"S": S, "ci90": [lo, hi], "cond_diff": diff, "squeeze_conds": squeeze, "all_invalid_conds": all_invalid, "dropped_conds_no_ref": dropped, "n_conds_used": len(usable), "safety_hit": safety}


def selftest():
    def mk(dl, sd=0.01, sq=None, kill=None, seed=3):
        r = random.Random(seed); Sh = {}
        for c in COND:
            base = 0.4 + r.uniform(-0.1, 0.1); Sh[(c, H.GCC)] = [base + r.gauss(0, sd) for _ in range(3)]; Sh[(c, H.PP)] = [base + dl + r.gauss(0, sd) for _ in range(3)]
        if sq: Sh[(sq, H.PP)] = [x + 0.2 for x in Sh[(sq, H.GCC)]]
        if kill: Sh[(kill, H.PP)] = []
        return Sh
    assert judge(mk(0.0), B=2000)[0] == "holds"
    Sw = {}
    for i, c in enumerate(COND): Sw[(c, H.GCC)] = [0.40 - 0.12, 0.40, 0.40 + 0.12]; Sw[(c, H.PP)] = [0.32 - 0.12, 0.32, 0.32 + 0.12]
    v, m = judge(Sw, B=2000); assert v == "direction only" and not m["squeeze_conds"], (v, m)
    assert judge(mk(-0.14), B=2000)[0] == "does not hold"
    v, m = judge(mk(0.02, sq="G2"), B=2000); assert v == "does not hold" and m["squeeze_conds"] == ["G2"], m
    v, m = judge(mk(0.0, kill="T3"), B=2000); assert v == "does not hold" and m["all_invalid_conds"] == ["T3"], m
    assert abs((lambda v, c: v / (v + c))(1000.0, 1000.0) - 0.5) < 1e-9
    import tempfile
    t = Path(tempfile.mkdtemp()) / "s.log"; t.write_text("Chain POSTROUTING (policy ACCEPT)\n    pkts      bytes target\n    1000   1450000 CLASSIFY   tcp  --  *  *  0.0.0.0/0  0.0.0.0/0  tcp dpt:5201 CLASSIFY set 10:10\n")
    assert abs(shape_tcp(t)["tcp_avg_pkt_bytes"] - 1450.0) < 1e-9
    t.write_text("    10   650000 CLASSIFY   tcp  --  *  *  0.0.0.0/0  0.0.0.0/0  tcp dpt:5201 CLASSIFY set 10:10\n"); assert shape_tcp(t)["tcp_avg_pkt_bytes"] > 1600
    t.write_text("qdisc netem 100: parent 10:10 limit 53 delay 50.0ms rate 2Mbit\n Sent 20598437 bytes 22585 pkt (dropped 1380, overlimits 0 requeues 0) \n"); assert shape_tcp(t)["netem_dropped"] == 1380
    print("Competition verdict self-test passed (5 verdict cases; oversized TCP packets rejected)")


def calcheck(label):
    D = K / f"calib_{label}"; ceil = json.load(open(H.K / "ceilings.json"))["ceiling_kbps"]["johnny"]; out = {}
    def tag(cond, arm): return f"{arm}__hd_c2__d0__r1__vjohnny"
    k1 = comp_metrics(D / "K1", tag("K1", "fixed_env"), "fixed_env", "T2", "tcp", ceil); k2 = comp_metrics(D / "K2", tag("K2", "fixed_env"), "fixed_env", "T2", "tcp", ceil)
    k3 = comp_metrics(D / "K3", tag("K3", H.GCC), H.GCC, "G2", "gcc", ceil); k4 = comp_metrics(D / "K4", tag("K4", H.PP), H.PP, "T2", "tcp", ceil)
    pick = lambda r, ks: {k: r.get(k) for k in ks}
    out["K1"] = pick(k1, ("share_valid", "share_invalid_reasons", "tcp_kbps", "tcp_avg_pkt_bytes", "tcp_rule_pkts", "class1010_bytes", "win_kbps", "tcp_cc"))
    out["K1"]["pass"] = bool(k1.get("share_valid") and (k1.get("tcp_kbps") or 0) >= 1500 and (k1.get("tcp_avg_pkt_bytes") or 1e9) <= 1600 and (k1.get("tcp_rule_pkts") or 0) > 0)
    tot2 = (k2.get("win_kbps") or 0) + (k2.get("win_rtx_kbps") or 0) + (k2.get("tcp_kbps") or 0)
    out["K2"] = pick(k2, ("share_valid", "share_invalid_reasons", "win_kbps", "win_rtx_kbps", "tcp_kbps", "win_loss_rate", "tcp_retrans_in_window", "tcp_cwr_or_loss_samples", "netem_dropped", "measure_duration_s")); out["K2"]["sum_kbps"] = tot2
    out["K2"]["pass"] = bool(k2.get("valid") and k2.get("share_valid") and tot2 <= 1.05 * 2000 and ((k2.get("win_loss_rate") or 0) > 0 or (k2.get("win_rtx_kbps") or 0) > 0)
                             and (k2.get("netem_dropped") or 0) > 0 and ((k2.get("tcp_retrans_in_window") or 0) > 0 or (k2.get("tcp_cwr_or_loss_samples") or 0) > 0))
    out["K3"] = pick(k3, ("valid", "share_valid", "share_invalid_reasons", "win_kbps", "competitor_kbps", "comp_first5_kbps", "comp_last20_kbps", "share"))
    out["K3"]["pass"] = bool(k3.get("valid") and k3.get("share_valid") and k3.get("comp_first5_kbps") is not None and (k3.get("comp_last20_kbps") or 0) >= 1.5 * max(k3["comp_first5_kbps"], 1.0))
    out["K4"] = pick(k4, ("valid", "invalid_reasons", "share_valid", "share_invalid_reasons", "share", "win_kbps", "tcp_kbps", "vmaf", "vmaf_window"))
    out["K4"]["pass"] = bool(k4.get("valid") and k4.get("share_valid") and k4.get("share") is not None)
    a, b = D / "K5_v11", D / "K5_v12"; t5 = tag("K5", "fixed_env")
    def norm(x):
        if isinstance(x, dict): return {k: norm(v) for k, v in x.items()}
        if isinstance(x, list): return [norm(v) for v in x]
        return x.rsplit("/", 1)[-1] if isinstance(x, str) and x.startswith("/app/result/") else x
    def cfg(dd, kind):
        p = dd / f"config_{kind}_{t5}.json"; return norm(json.load(open(p))) if p.is_file() else {}
    def shape(dd):
        p = dd / f"shape_{t5}.log"
        if not p.is_file(): return None
        t = p.read_text(); return {"qdisc": re.findall(r"qdisc netem 100: .*", t), "class": re.findall(r"class htb 10:10 .*", t), "mangle": [re.sub(r"^\s*\d+\s+\S+\s+", "", l) for l in t.splitlines() if "CLASSIFY" in l]}
    def rate(dd):
        s = dd / f"{t5}.json"; return json.load(open(s))["network"]["primary_video_payload_rate_kbps"] if s.is_file() else None
    ra, rb = rate(a), rate(b)
    out["K5"] = {"config_sender_same": cfg(a, "sender") == cfg(b, "sender") and bool(cfg(a, "sender")), "config_receiver_same": cfg(a, "receiver") == cfg(b, "receiver") and bool(cfg(a, "receiver")),
                 "shape_same": shape(a) == shape(b) and shape(a) is not None, "rate_v11": ra, "rate_v12": rb, "shape_v11": shape(a), "shape_v12": shape(b)}
    out["K5"]["pass"] = bool(out["K5"]["config_sender_same"] and out["K5"]["config_receiver_same"] and out["K5"]["shape_same"] and ra and rb and abs(ra - rb) / ra < 0.05)
    out["pass"] = all(out[k]["pass"] for k in ("K1", "K2", "K3", "K4", "K5"))
    (D / "calcheck.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str)); print(json.dumps({k: (v["pass"] if isinstance(v, dict) else v) for k, v in out.items()}, ensure_ascii=False))
    (D / ("CALIB_PASS" if out["pass"] else "CALIB_FAILED")).write_text(json.dumps({k: out[k]["pass"] for k in ("K1", "K2", "K3", "K4", "K5")}, ensure_ascii=False))
    return out


def main():
    s = json.load(open(MAINK / "jobs.json")); ceil = json.load(open(H.K / "ceilings.json"))["ceiling_kbps"]["johnny"]; runs = []
    for j in s["jobs"]:
        c = j["cond"].split("__")[0]; kind = COND[c][1]; d = MAINK / j["cond"]; tag = f"{j['arm']}__{Path(j['profile']).stem}__d0__r{j['rep']}__vjohnny"
        if not d.is_dir(): runs.append({"tag": tag, "arm": j["arm"], "ccond": c, "rep": j["rep"], "valid": False, "share_valid": False, "share_invalid_reasons": ["Missing run directory"], "invalid_reasons": ["Missing run directory"], "job": j["cond"]}); continue
        r = comp_metrics(d, tag, j["arm"], c, kind, ceil); r["ccond"] = c; r["rep"] = j["rep"]; r["job"] = j["cond"]; runs.append(r)
    bad = RM.code_audit(runs)
    for r in runs:
        if r["tag"] in bad and "code hash mismatch" not in r.get("share_invalid_reasons", []): r["share_valid"] = False; r.setdefault("share_invalid_reasons", []).append("code hash mismatch")
    if len(bad) > 0.1 * len(runs):
        (K / "AUDIT_FAILED").write_text(json.dumps(bad, ensure_ascii=False)); subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, f"Runs with code hash mismatch: {len(bad)}, more than one tenth, no conclusion: {bad[:6]}"], check=True); return
    Sh = {}
    for r in runs:
        if r.get("share_valid") and r.get("share") is not None: Sh.setdefault((r["ccond"], r["arm"]), []).append(r["share"])
    v, m = judge(Sh); others = {a: judge(Sh, arm=H.ARMS[a])[1] for a in ("nl",)}
    base = {}
    try:
        HR = [json.loads(l) for l in open(H.LOCAL / "runs_full.jsonl")]
        for c, (prof, _) in COND.items():
            for a, arm in H.ARMS.items():
                xs = [x["vmaf"] for x in HR if x.get("valid") and x["arm"] == arm and x["cond"] == prof and x.get("video_id") == "johnny" and x.get("vmaf") is not None]
                base[(c, a)] = st.mean(xs) if xs else None
    except Exception as e: base = {"error": repr(e)}
    def agg(key, arm, c=None):
        xs = [r[key] for r in runs if r.get("share_valid") and r["arm"] == arm and r.get(key) is not None and (c is None or r["ccond"] == c)]; return st.mean(xs) if xs else None
    keys = ["env6_ceiling_frac", "env6_capped_frac", "env6_overuse_frac", "share", "competitor_kbps", "win_kbps", "jain", "win_qdelay_mean_ms", "win_qdelay_p95_ms", "win_loss_rate", "vmaf", "vmaf_window", "file_freeze_per_min", "webrtc_NumberFreezesPerMinute", "recovery_s", "envelope_rewrite_frac"]
    by = {a: {c: {k: agg(k, arm, c) for k in keys} for c in COND} for a, arm in H.ARMS.items()}
    for a in H.ARMS:
        for c in COND:
            b0 = base.get((c, a)) if isinstance(base, dict) else None; by[a][c]["vmaf_minus_nocomp_baseline"] = (by[a][c]["vmaf"] - b0) if (b0 is not None and by[a][c]["vmaf"] is not None) else None
    n_valid = {a: sum(1 for r in runs if r["arm"] == arm and r.get("share_valid")) for a, arm in H.ARMS.items()}
    try:
        r1 = json.load(open(K_V1 / "result_v1.json")); cross = {"nlbatch_share_by_arm_cond": {a: {c: r1["by_arm_cond"][a][c]["share"] for c in COND} for a in ("nl", "gcc200")}, "nlbatch_S_nl": r1["S"]}
    except Exception as e: cross = {"error": repr(e)}
    res = {"verdict": v, **m, "other_arms_vs_gcc": {a: {k: o[k] for k in ("S", "ci90", "squeeze_conds", "all_invalid_conds")} for a, o in others.items()}, "by_arm_cond": by, "n_valid": n_valid,
           "n_runs": len(runs), "bad_hash": bad, "invalid_runs": {r["tag"] + "|" + r.get("job", ""): r.get("share_invalid_reasons") for r in runs if not r.get("share_valid")}, "cross_batch_nl_report_only": cross}
    (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    LOCAL.mkdir(parents=True, exist_ok=True)
    cols = ["tag", "job", "arm", "ccond", "rep", "pair", "share_valid", "share_invalid_reasons", "valid", "invalid_reasons", "share", "jain", "win_kbps", "win_rtx_kbps", "competitor_kbps", "tcp_kbps", "tcp_retrans_in_window",
            "tcp_rtt_ms_median", "tcp_avg_pkt_bytes", "comp_first5_kbps", "comp_last20_kbps", "win_qdelay_mean_ms", "win_qdelay_p95_ms", "win_loss_rate", "vmaf", "vmaf_window", "file_freeze_per_min",
            "webrtc_NumberFreezesPerMinute", "recovery_s", "envelope_rewrite_frac", "env6_ok", "env6_gcc_err", "env6_ceiling_frac", "env6_capped_frac", "env6_overuse_frac", "decision_gap_p95_ms", "cpu_temp_start", "cpu_temp_end", "start", "end"]
    with open(LOCAL / "runs_tidy.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in runs: w.writerow({**{k: r.get(k) for k in cols}, "share_invalid_reasons": ";".join(r.get("share_invalid_reasons", [])), "invalid_reasons": ";".join(r.get("invalid_reasons", []))})
    with open(LOCAL / "runs_full.jsonl", "w", encoding="utf-8") as f:
        for r in runs: f.write(json.dumps({k: x for k, x in r.items() if k != "code_hash"}, ensure_ascii=False, default=str) + "\n")
    (LOCAL / "data_dictionary.json").write_text(json.dumps({"share": "within the competition window (40 to 90 seconds after shaping), video payload rate of the main call / (that rate + competitor goodput)", "competitor_kbps": "for TCP, bytes per second at the receiver; for the GCC call, the payload rate of its main video stream",
        "jain": "(v+c)²/(2(v²+c²))", "win_*": "readings of the main call within the competition window", "vmaf_window": "mean VMAF of frames within the competition window (located with the complete per-frame timestamps of the decoded file)", "recovery_s": "seconds, after the competitor leaves at 90 s, until the 5 s moving average is back at 90% of its mean over 20 to 30 s",
        "share_valid": "validity gate of the share endpoint (comp_metrics in this script)", "the rest": "As in the data dictionary of hd720-closedloop-v1"}, ensure_ascii=False, indent=1))
    shutil.copy(K / "result_v1.json", LOCAL / "result_v1.json")
    for lab in ("tool", "formal"):
        p = K / f"calib_{lab}" / "calcheck.json"
        if p.is_file(): shutil.copy(p, LOCAL / f"calcheck_{lab}.json")
    shutil.copy(Path(__file__), LOCAL / Path(__file__).name)
    with open(LOCAL / "SHA256SUMS", "w") as f:
        for p in sorted(LOCAL.iterdir()):
            if p.name != "SHA256SUMS": f.write(f"{H.sha(p)}  {p.name}\n")
    fmt = lambda x: "none" if x is None else f"{x:.3f}"
    basis = (f"Primary endpoint S (bottleneck share in the competition window, C-H with probing envelope v6 minus Python GCC called every 200 ms, {m['n_conds_used']} conditions equally weighted){m['S']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]; per condition difference {json.dumps({k: round(x, 3) for k, x in m['cond_diff'].items()}, ensure_ascii=False)}; safety line: conditions in which the competitor is squeezed too much {m['squeeze_conds'] or 'none'}, cells with all deployed-arm runs invalid: {m['all_invalid_conds'] or 'none'}. Report only: share of each arm {json.dumps({a: {c: (round(x['share'], 3) if x['share'] is not None else None) for c, x in d_.items()} for a, d_ in by.items()}, ensure_ascii=False)}; S of the no-LLM multi-scale estimator with envelope v6 against GCC {others['nl']['S']:+.3f}; fraction of steps under the cap, C-H {json.dumps({c: (round(x['env6_ceiling_frac'], 2) if x['env6_ceiling_frac'] is not None else None) for c, x in by['ch'].items()}, ensure_ascii=False)}, multi-scale estimator {json.dumps({c: (round(x['env6_ceiling_frac'], 2) if x['env6_ceiling_frac'] is not None else None) for c, x in by['nl'].items()}, ensure_ascii=False)}; cross-batch reference (compete-flow-nl-v1, multi-scale estimator with envelope v6) S {cross.get('nlbatch_S_nl', float('nan')):+.3f}; valid runs {json.dumps(n_valid, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({k: res[k] for k in ("S", "ci90", "cond_diff", "squeeze_conds", "all_invalid_conds", "n_valid")}, ensure_ascii=False, default=str),
       "--artifact", str(K / "result_v1.json"), "--artifact", str(LOCAL / "runs_tidy.csv"), "--log", str(ROOT / "logs/compete_ch_sched.log"))
    if v == "inconclusive":
        ex("note", "--id", ID, "Fewer than 2 usable conditions; under the boundary rule fixed before the run, no conclusion is recorded." + basis); return
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered, claim two (non-inferiority margin 0.10, safety line 0.15 and all runs of a cell invalid)." + basis, "--basis", basis,
       "--limitations", "The system under test is C-H (conference encoder with HCQ, no LLM, seed 1 of cell C-H of ablation-nl-enc-hcq-2x2-v1) with probing envelope v6; conditions are the same as compete-flow-v1 and v2, run fresh; the competitor settings come from the v1 calibration. Sender egress shaping, the TCP sender and the bottleneck queue are in the same network namespace (local drop signal); one queue length (200 ms); one sequence (Johnny); 3 runs per cell; receiver inference is asynchronous (when it takes longer than 40 ms, the previous estimate is returned).",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "jobs": build_jobs()
    elif c == "caljobs": build_caljobs(sys.argv[2])
    elif c == "calcheck": calcheck(sys.argv[2])
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
