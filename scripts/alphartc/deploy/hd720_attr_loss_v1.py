#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batches hd720-echo-attr-ch-v1 and hd720-randloss-ch-v1, both on the 720p deployed system (deployed estimator, 5 kbps floor, probing envelope v6).
Echo attribution: deployed minus echo-arm VMAF over 12 cells, holds if the 90% lower bound is above 0 with no safety-line hit; random loss (1% and 5% at 2 and 8 Mbit/s): deployed minus Python GCC called every 200 ms with the hd720-closedloop-ch-v1 criterion, plus a loss check on every run.
Usage: hd720_attr_loss_v1.py jobs | smoke-jobs | smoke-gate | judge-attr | judge-loss | selftest
"""
import csv, json, re, shutil, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_run_metrics_v1 as RM  # noqa: E402
T = Path("/path/to/testbed/results"); KA = T / "hd720-echo-attr-ch-v1"; KL = T / "hd720-randloss-ch-v1"; KS = T / "hd720-randloss-smoke-v1"
IDA, IDL = "hd720-echo-attr-ch-v1", "hd720-randloss-ch-v1"
RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v20.sh"
GCC, CH, ECHO = H.GCC, "arm_ch_x", "echo_x"
ENV = {GCC: {}, CH: {"STALENESS_COLLECTOR": "v6", "STALENESS_ENVELOPE": "6", "STALENESS_MIN_BPS_FLOOR": "1"}, ECHO: {"STALENESS_COLLECTOR": "v6", "STALENESS_ENVELOPE": "6"}}
ARMS_A = {"gcc200": GCC, "ch": CH, "echo": ECHO}; ARMS_L = {"gcc200": GCC, "ch": CH}
CONDS_A = list(H.CONDS); CONDS_L = ["hd_l2p1", "hd_l2p5", "hd_l8p1", "hd_l8p5"]
PL = D_ / "profiles/hd720_loss"; PROV_L = json.load(open(PL / "provenance.json"))["profiles"]
REPS = 3


def prepare(K):
    """Copy the sequence list, rate ceilings and label layout from the hd720-closedloop-ch-v1 batch directory into K, or check that existing copies match."""
    K.mkdir(parents=True, exist_ok=True)
    for n in ("contents.json", "ceilings.json", "layout.json"):
        src, dst = H.K / n, K / n
        if not src.is_file(): continue
        if dst.is_file(): assert dst.read_bytes() == src.read_bytes(), f"{dst} inconsistent with {src}"
        else: shutil.copy(src, dst)


def prof(cond): return (PL if cond in PROV_L else H.P) / f"{cond}.profile"
def queue(cond): return PROV_L[cond]["queue_packets"] if cond in PROV_L else H.queue_of(cond)


def build(K, name, conds, arms, contents, reps, log):
    C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []; order = list(arms); blk = 0
    for rep in range(1, reps + 1):
        for cond in conds:
            for content in contents:
                rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
                for a in rot:
                    J.append({"cond": f"{cond}__{content}__{a}__r{rep}", "arm": arms[a], "profile": str(prof(cond)), "rep": rep, "video_id": content,
                              "queue": queue(cond), "source": H.source_of(content, layout), "env": dict(ENV[arms[a]])})
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(name, K / "main", J, log, ly); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print(name, "jobs:", len(J)); return s


def jobs():
    for K in (KA, KL): prepare(K)
    ca = json.load(open(KA / "contents.json"))["main_contents"]
    build(KA, IDA, CONDS_A, ARMS_A, ca, REPS, ROOT / "logs/hd720_echo_attr_sched.log")
    build(KL, IDL, CONDS_L, ARMS_L, ca, REPS, ROOT / "logs/hd720_randloss_sched.log")


def smoke_jobs():
    prepare(KS); build(KS, "hd720-randloss-smoke-v1", ["hd_l8p5"], ARMS_L, ["kristenandsara"], 1, ROOT / "logs/hd720_randloss_smoke_sched.log")


def loss_check(d, tag, want):
    """Check that every applied loss_pct in the control log equals the profile and that netem in the shape log carries the same loss; return (ok, reason, readings)."""
    ctl = RM.first(d, f"control_{tag}.log"); shp = RM.first(d, f"shape_{tag}.log")
    if ctl is None or shp is None: return False, "Missing control or shaping log", {}
    ap = [json.loads(l) for l in open(ctl, errors="ignore") if l.startswith('{"event":"apply"')]
    got = sorted({float(str(a.get("loss_pct", "0")).rstrip("%")) for a in ap})
    net = re.findall(r"qdisc netem 100:.*?loss (\d+(?:\.\d+)?)%", open(shp, errors="ignore").read())
    ok = bool(ap) and got == [float(want)] and bool(net) and all(float(x) == float(want) for x in net)
    return ok, ("" if ok else f"packet loss not applied as configured: control log {got}, netem {net}, configured {want}"), {"loss_applied": got, "netem_loss": net}


def collect(K, conds_loss):
    s = json.load(open(K / "main" / "jobs.json")); ceil = json.load(open(K / "ceilings.json"))["ceiling_kbps"]; runs = []
    for j in s["jobs"]:
        d = K / "main" / j["cond"]; cond = Path(j["profile"]).stem; tag = f"{j['arm']}__{cond}__d0__r{j['rep']}__v{j['video_id']}"
        if not d.is_dir(): runs.append({"tag": tag, "arm": j["arm"], "cond": cond, "video_id": j["video_id"], "rep": j["rep"], "valid": False, "invalid_reasons": ["Missing run directory"], "job": j["cond"]}); continue
        r = RM.run_metrics(d, tag, j["arm"], cond, ceil[j["video_id"]], light_fps_gate=(cond == "hd_c8")); r["video_id"] = j["video_id"]; r["rep"] = j["rep"]; r["job"] = j["cond"]
        if j["arm"] != GCC:
            r.update(H.env6_check(d, tag))
            if not r["env6_ok"]: r["valid"] = False; r["invalid_reasons"] = list(r.get("invalid_reasons", [])) + ["probing envelope v6 check did not pass:" + ";".join(r["env6_reasons"])]
        if cond in conds_loss:
            ok, why, x = loss_check(d, tag, PROV_L[cond]["loss_pct"]); r.update(x); r["loss_ok"] = ok
            if not ok: r["valid"] = False; r["invalid_reasons"] = list(r.get("invalid_reasons", [])) + [why]
        runs.append(r)
    return runs, RM.code_audit(runs)


def attr_verdict(m):
    """Echo-attribution verdict from the H.judge readings (arm deployed, ref echo) with the margin moved from -6 to 0."""
    safety = bool(m["severe_cells"] or m["all_invalid_cells"])
    if m["n_cells_used"] < 6 and not safety: return "inconclusive"
    if safety or not (m["D"] > 0): return "does not hold"
    return "holds" if m["ci90"][0] > 0 else "direction only"


def selftest():
    import random
    cells = [f"{c}__{v}" for c in CONDS_A for v in ("johnny", "fourpeople")]
    def mk(delta, sd=1.0, sev=None, kill=None, seed=1):
        r = random.Random(seed); V = {}
        for c in cells:
            base = 75 + r.gauss(0, 5); V[(c, ECHO)] = [base + r.gauss(0, sd) for _ in range(3)]; V[(c, CH)] = [base + delta + r.gauss(0, sd) for _ in range(3)]
        if sev: V[(sev, CH)] = [x - 12 for x in V[(sev, ECHO)]]
        if kill: V[(kill, CH)] = []
        return V
    J = lambda V: attr_verdict(H.judge(V, cells, arm=CH, ref=ECHO, B=2000)[1])
    assert J(mk(2.5)) == "holds"
    Vw = {}
    for i, c in enumerate(cells): Vw[(c, ECHO)] = [70 + i - 8, 70 + i, 70 + i + 8]; Vw[(c, CH)] = [70.5 + i - 8, 70.5 + i, 70.5 + i + 8]
    assert J(Vw) == "direction only", J(Vw)
    assert J(mk(-1.0)) == "does not hold"
    assert J(mk(3.0, sev=cells[2])) == "does not hold"
    assert J(mk(3.0, kill=cells[4])) == "does not hold"
    H.selftest()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td); tag = "x"
        (d / f"control_{tag}.log").write_text('{"event":"apply","mode":"build","wall_time_ms":1,"rate_kbps":2000,"latency_ms":50,"loss_pct":"0"}\n')
        (d / f"shape_{tag}.log").write_text("qdisc netem 100: parent 10:10 limit 53 delay 50.0ms rate 2Mbit\n")
        assert not loss_check(d, tag, 5)[0]
        (d / f"control_{tag}.log").write_text('{"event":"apply","mode":"build","wall_time_ms":1,"rate_kbps":2000,"latency_ms":50,"loss_pct":"5"}\n')
        (d / f"shape_{tag}.log").write_text("qdisc netem 100: parent 10:10 limit 53 delay 50.0ms loss 5% rate 2Mbit\n")
        assert loss_check(d, tag, 5)[0]
    print("Self-test passed: echo-attribution verdicts, hd720_ch_eval_v1 judge, loss check")


def smoke_gate():
    import time
    runs, _ = collect(KS, set(CONDS_L)); bad = []
    for r in runs:
        if not r.get("valid"): bad.append(f"{r['tag']} invalid: {r.get('invalid_reasons')}")
        if not r.get("loss_ok"): bad.append(f"{r['tag']} packet loss check did not pass")
        lr = r.get("loss_rate")
        if lr is None or not (0.02 <= lr <= 0.10): bad.append(f"{r['tag']} measured packet loss rate {lr} not in 2% to 10%")
    (KS / "smoke.json").write_text(json.dumps({"runs": [{k: r.get(k) for k in ("tag", "valid", "invalid_reasons", "loss_ok", "loss_applied", "netem_loss", "loss_rate", "vmaf", "video_kbps", "decoded_fps", "env6_ok")} for r in runs], "bad": bad}, ensure_ascii=False, indent=1, default=str))
    if bad: (KS / "SMOKE_FAILED").write_text(";".join(bad)); print("smoke test not passed", bad); sys.exit(1)
    (KS / "SMOKE_OK").write_text(f"Automatic check (hd720_attr_loss_v1.py smoke-gate): two valid runs, packet loss applied as configured, measured packet loss rate between 2% and 10%, probing envelope v6 check passed; {time.strftime('%Y-%m-%d %H:%M:%S')}"); print("smoke test passed")


def by_arm_cond(runs, arms, conds):
    agg = lambda key, arm, cond=None: (lambda xs: st.mean(xs) if xs else None)([r[key] for r in runs if r.get("valid") and r["arm"] == arm and r.get(key) is not None and (cond is None or r["cond"] == cond)])
    keys = ["vmaf", "ssim", "psnr", "utility", "video_kbps", "loss_rate", "queue_delay_mean_ms", "file_freeze_per_min", "decoded_fps", "env6_ceiling_frac", "env6_capped_frac", "envelope_rewrite_frac"]
    return ({a: {k: agg(k, arm) for k in keys} for a, arm in arms.items()},
            {a: {c: {k: agg(k, arm, c) for k in ("vmaf", "utility", "video_kbps", "loss_rate", "file_freeze_per_min", "decoded_fps")} for c in conds} for a, arm in arms.items()})


def export(K, local, runs, res):
    local.mkdir(parents=True, exist_ok=True); (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    old_k, old_l = H.K, H.LOCAL; H.K, H.LOCAL = K, local
    try: H.export(runs, res)
    finally: H.K, H.LOCAL = old_k, old_l
    shutil.copy(Path(__file__), local / Path(__file__).name)
    with open(local / "SHA256SUMS", "w") as f:
        for p in sorted(local.iterdir()):
            if p.name != "SHA256SUMS": f.write(f"{H.sha(p)}  {p.name}\n")


def register(cid, v, m, basis, crit, lim, nxt, K, local, n_valid, log):
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", cid, "--metrics", json.dumps({k: m[k] for k in ("D", "ci90", "severe_cells", "all_invalid_cells", "n_cells_used")} | {"n_valid": n_valid}, ensure_ascii=False, default=str),
       "--artifact", str(K / "result_v1.json"), "--artifact", str(local / "runs_tidy.csv"), "--log", str(log))
    if v == "inconclusive": ex("note", "--id", cid, "Fewer than 6 usable cells, no conclusion is recorded." + basis); return
    ex("conclude", "--id", cid, "--verdict", v, "--vs-criteria", crit + basis, "--basis", basis, "--limitations", lim, "--next", nxt)


def fmt(m): return f"{m['D']:+.2f} VMAF, 90% interval [{m['ci90'][0]:+.2f}, {m['ci90'][1]:+.2f}]"


def audit_ok(K, cid, runs, bad):
    if len(bad) > 0.1 * len(runs):
        (K / "AUDIT_FAILED").write_text(json.dumps(bad, ensure_ascii=False))
        subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", cid, f"Runs with code hash mismatch: {len(bad)}, more than one tenth, no conclusion: {bad[:6]}"], check=True); return False
    return True


def judge_attr():
    runs, bad = collect(KA, set())
    if not audit_ok(KA, IDA, runs, bad): return
    cells = [f"{c}__{v}" for c in CONDS_A for v in json.load(open(KA / "contents.json"))["main_contents"]]; V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["arm"]), []).append(r["vmaf"])
    m = H.judge(V, cells, arm=CH, ref=ECHO)[1]; v = attr_verdict(m)
    me = H.judge(V, cells, arm=ECHO, ref=GCC)[1]; mc = H.judge(V, cells, arm=CH, ref=GCC)[1]
    ba, bc = by_arm_cond(runs, ARMS_A, CONDS_A); nv = {a: sum(1 for r in runs if r["arm"] == arm and r.get("valid")) for a, arm in ARMS_A.items()}
    res = {"verdict": v, **m, "reaches_6": bool(m["D"] >= 6), "echo_vs_gcc_report_only": me, "ch_vs_gcc_report_only": mc, "by_arm": ba, "by_cond": bc, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad,
           "invalid_runs": {r["tag"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_echo_attr_ch_v1"; export(KA, local, runs, res)
    r1 = lambda x: None if x is None else round(x, 1)
    basis = (f"Primary endpoint D_E (deployed system C-H minus the echo arm with envelope v6, {m['n_cells_used']} cells equally weighted) {fmt(m)}; {'reached' if m['D'] >= 6 else 'not reached'} 6 points; per-cell {json.dumps({c: round(x, 2) for c, x in m['cell_diff'].items()}, ensure_ascii=False)}; safety line: cells where C-H is more than 10 points below the echo arm {m['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m['all_invalid_cells'] or 'none'}, cells excluded because all echo runs were invalid: {m['dropped_cells_no_ref'] or 'none'}. Report only (decomposition): echo arm with envelope v6 against GCC {fmt(me)}; C-H versus GCC {fmt(mc)} (readings of this batch, not a recheck of hd720-closedloop-ch-v1); average VMAF {json.dumps({a: r1(x['vmaf']) for a, x in ba.items()}, ensure_ascii=False)}; video rate {json.dumps({a: r1(x['video_kbps']) for a, x in ba.items()}, ensure_ascii=False)}; freezes per minute in the decoded file {json.dumps({a: (round(x['file_freeze_per_min'], 2) if x['file_freeze_per_min'] is not None else None) for a, x in ba.items()}, ensure_ascii=False)}; probing envelope rewrite fraction {json.dumps({a: (round(x['envelope_rewrite_frac'], 3) if x['envelope_rewrite_frac'] is not None else None) for a, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    lim = ("The system under test is C-H with the 5 kbps floor and probing envelope v6, and the echo arm is the receiving-rate echo behind the same envelope (echo_x_v2); conditions and sequences are those of hd720-closedloop-ch-v1 (two 720p talking-head sequences (Johnny, FourPeople), four constant capacities from 1 to 8 Mbit/s and two cellular trace windows), libwebrtc default maximum bitrate 2.5 Mbps for 960x540 and above; single-machine testbed, sender egress shaping, one-way delay 50 ms, no random packet loss; 3 runs per cell; run script v20.")
    register(IDA, v, m, basis, "Criterion as pre-registered, part one (holds if the D_E lower bound is greater than 0, safety line 10 points and all runs of a cell invalid, interval the same as hd720-closedloop-ch-v1).", lim,
             "", KA, local, nv, ROOT / "logs/hd720_echo_attr_sched.log")


def judge_loss():
    runs, bad = collect(KL, set(CONDS_L))
    if not audit_ok(KL, IDL, runs, bad): return
    cells = [f"{c}__{v}" for c in CONDS_L for v in json.load(open(KL / "contents.json"))["main_contents"]]; V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["arm"]), []).append(r["vmaf"])
    v, m = H.judge(V, cells, arm=CH, ref=GCC)
    ba, bc = by_arm_cond(runs, ARMS_L, CONDS_L); nv = {a: sum(1 for r in runs if r["arm"] == arm and r.get("valid")) for a, arm in ARMS_L.items()}
    res = {"verdict": v, **m, "by_arm": ba, "by_cond": bc, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad, "invalid_runs": {r["tag"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_randloss_ch_v1"; export(KL, local, runs, res)
    r1 = lambda x: None if x is None else round(x, 1)
    basis = (f"Primary endpoint D_L (deployed system C-H minus Python GCC called every 200 ms, {m['n_cells_used']} cells equally weighted) {fmt(m)}; per-cell {json.dumps({c: round(x, 2) for c, x in m['cell_diff'].items()}, ensure_ascii=False)}; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m['all_invalid_cells'] or 'none'}, cells excluded because all GCC runs were invalid: {m['dropped_cells_no_ref'] or 'none'}. Report only: superiority {'reached' if m['superiority_report_only'] else 'not reached'}; per-condition VMAF {json.dumps({a: {c: r1(x['vmaf']) for c, x in d.items()} for a, d in bc.items()}, ensure_ascii=False)}; per-condition video rate {json.dumps({a: {c: r1(x['video_kbps']) for c, x in d.items()} for a, d in bc.items()}, ensure_ascii=False)}; measured packet loss rate {json.dumps({a: (round(x['loss_rate'], 4) if x['loss_rate'] is not None else None) for a, x in ba.items()}, ensure_ascii=False)}; decoded frame rate {json.dumps({a: r1(x['decoded_fps']) for a, x in ba.items()}, ensure_ascii=False)}; freezes per minute {json.dumps({a: (round(x['file_freeze_per_min'], 2) if x['file_freeze_per_min'] is not None else None) for a, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    lim = ("The system under test is C-H with the 5 kbps floor and probing envelope v6; random loss is applied with netem loss random to all UDP traffic at the sender egress (including RTCP and STUN), two loss rates, 1% and 5%, capacities 2 and 8 Mbit/s, delay 50 ms; two 720p talking-head sequences (Johnny, FourPeople), libwebrtc default maximum bitrate 2.5 Mbps for 960x540 and above; single-machine testbed; 3 runs per cell; the 8 Mbit/s cells do not apply the decoded-frame-rate gate; run script v20.")
    register(IDL, v, m, basis, "Criterion as pre-registered, part two (verbatim the same as hd720-closedloop-ch-v1: non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid).", lim,
             "", KL, local, nv, ROOT / "logs/hd720_randloss_sched.log")


if __name__ == "__main__":
    {"jobs": jobs, "smoke-jobs": smoke_jobs, "smoke-gate": smoke_gate, "judge-attr": judge_attr, "judge-loss": judge_loss, "selftest": selftest}[sys.argv[1]]()
