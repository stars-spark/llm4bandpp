#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-closedloop-ch-v1 and its companion claim against the no-LLM multi-scale estimator: 720p closed loop, 6 conditions x 2 sequences, 3 runs per arm and cell.
Arms: Python GCC called every 200 ms, deployed estimator with probing envelope v6, no-LLM multi-scale estimator with envelope v6. Main endpoint: mean VMAF difference over 12 equally weighted cells with a stratified bootstrap 90% interval; holds if the lower bound is above -6 with no safety-line hit (a cell 10 points worse, or all its runs invalid).
Usage: hd720_ch_eval_v1.py jobs | prepare | judge [--selftest]
"""
import csv, hashlib, json, random, shutil, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy"))
ID = "hd720-closedloop-ch-v1"; ID2 = "hd720-ch-vs-nl-v1"; K = Path("/path/to/testbed/results/hd720-closedloop-ch-v1"); MAIN = K / "main"; LOCAL = ROOT / "experiments/results/hd720_closedloop_ch_v1"
K_XB = Path("/path/to/testbed/results/hd720-closedloop-nl-v1")
K_V1 = Path("/path/to/testbed/results/hd720-closedloop-v1")
P = ROOT / "scripts/alphartc/deploy/profiles/hd720"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v18.sh"
CONDS = ["hd_c1", "hd_c2", "hd_c3", "hd_c8", "hd_r1", "hd_r2"]
ARMS = {"gcc200": "gcc_pt125_c200", "ch": "arm_ch_x", "nl": "arm_llm4bandpp_nl_x"}
PP, GCC, LLM = ARMS["ch"], ARMS["gcc200"], ARMS["nl"]; REPS = 3; NI, SAFE, SEED, B = -6.0, 10.0, 20261003, 10000
COMMON_ENV = {"STALENESS_POLICY": "v3", "STALENESS_OBS_TRACE": "1", "STALENESS_CONTROL_SLACK_S": "80", "STALENESS_CAPTURE_MEDIA": "1", "STALENESS_SOURCE_FPS": "30",
              "STALENESS_SOURCE_WIDTH": "1280", "STALENESS_SOURCE_HEIGHT": "720", "STALENESS_SENDER_LOGGING": "1", "STALENESS_REQUIRE_GSO_SEGS": "1",
              "STALENESS_ADAPT_MODEL": "/app/model/adapt_v2/adapt_mlp.npz"}
X_ENV = {"STALENESS_COLLECTOR": "v6", "STALENESS_ENVELOPE": "6"}
QUALITY = {"width": 1280, "height": 720, "ref_frames": 300, "step": 8, "ocr_jobs": 4, "vmaf_threads": 4, "ocr_scale": 0.5, "tmpdir": "/path/to/storage/hd720_scoring_tmp"}


def arm_env(arm): return {} if arm == GCC else dict(X_ENV)


def source_of(content, layout): return f"testmedia/hd720_{content}_30f300_{layout}.yuv"


def queue_of(prof):
    pv = json.load(open(P / "provenance.json"))["profiles"]; return pv[prof]["queue_packets"]


def spec(name, Kdir, jobs, log, layout_y, pairs=(1, 2)):
    return {"name": name, "K": str(Kdir), "log": str(log), "runner": str(RUNNER), "media": True, "vmaf_workers": 1, "max_pending": 4, "stagger_s": 7, "gso_segs": 1,
            "min_free_gb_home": 8, "min_free_gb_storage": 1.5, "common_env": COMMON_ENV, "quality": dict(QUALITY, label_y=layout_y),
            "phases": [{"name": name, "pairs": list(pairs), "vmaf": "async"}], "jobs": [dict(j, phase=name) for j in jobs]}


def prepare():
    """Copy contents.json and ceilings.json from the hd720-closedloop-v1 batch into K, or check that existing copies match."""
    K.mkdir(parents=True, exist_ok=True)
    for n in ("contents.json", "ceilings.json", "layout.json"):
        src, dst = K_V1 / n, K / n
        if not src.is_file(): continue
        if dst.is_file(): assert dst.read_bytes() == src.read_bytes(), f"{dst} inconsistent with v1"
        else: shutil.copy(src, dst)


def env6_check(d, tag):
    """Probing envelope v6 check on one run: version 6 on every step, zero shadow GCC errors and shadow GCC readings on at least 90% of steps after 10 s; returns env6_* readings and env6_ok."""
    import hd720_run_metrics_v1 as RM
    p = RM.first(d, f"obs_{tag}.jsonl*")
    if p is None: return {"env6_ok": False, "env6_reasons": ["Missing observation trace"]}
    O = [o for o in RM.jl(p) if "est_bps" in o]
    if not O: return {"env6_ok": False, "env6_reasons": ["Observed trace is empty"]}
    t0 = O[0]["t_ms"]; late = [o for o in O if o["t_ms"] - t0 >= 10000.0]; E = [(o.get("envelope") or {}) for o in O]
    vers = sorted({str(o.get("envelope_version")) for o in O}); err = max(int(e.get("gcc_err") or 0) for e in E)
    have = sum(1 for o in late if (o.get("envelope") or {}).get("gcc_bps") is not None) / max(len(late), 1)
    reasons = []
    if vers != ["6"]: reasons.append(f"probing envelope version is not 6: {vers}")
    if err > 0: reasons.append(f"shadow GCC errored {err} times")
    if have < 0.9: reasons.append(f"After shaping, the step where a shadow GCC reading exists 10 seconds later accounts for only {have:.2f}")
    n = len(O); st_ = {}
    for e in E: st_[e.get("state", "none")] = st_.get(e.get("state", "none"), 0) + 1
    return {"env6_ok": not reasons, "env6_reasons": reasons, "env6_gcc_err": err, "env6_gcc_seen_frac": have, "env6_ceiling_frac": sum(1 for e in E if e.get("ceiling")) / n,
            "env6_capped_frac": sum(1 for e in E if e.get("capped")) / n, "env6_overuse_frac": sum(1 for e in E if e.get("gcc_flag") == "OVERUSE") / n,
            "env6_state_share": {k: v / n for k, v in sorted(st_.items(), key=lambda x: str(x[0]))}}


def build_jobs():
    prepare(); C = json.load(open(K / "contents.json")); contents, layout, ly = C["main_contents"], C["layout"], C["label_y"]
    J = []; order = list(ARMS); blk = 0
    for rep in range(1, REPS + 1):
        for cond in CONDS:
            for content in contents:
                rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
                for a in rot:
                    J.append({"cond": f"{cond}__{content}__{a}__r{rep}", "arm": ARMS[a], "profile": str(P / f"{cond}.profile"), "rep": rep, "video_id": content,
                              "queue": queue_of(cond), "source": source_of(content, layout), "env": arm_env(ARMS[a])})
    MAIN.mkdir(parents=True, exist_ok=True); s = spec(ID, MAIN, J, ROOT / "logs/hd720_ch_sched.log", ly); (MAIN / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
    print("main batch job", len(J)); return s


def cell_means(V, cells, arm):
    return {c: (st.mean(V[(c, arm)]) if V.get((c, arm)) else None) for c in cells}


def judge(V, cells, arm=PP, ref=GCC, seed=SEED, B=B):
    """Return (verdict, metrics) for arm against ref; V maps (cell, arm) to valid-run VMAF lists and cells lists the cells."""
    all_invalid = [c for c in cells if not V.get((c, arm))]
    usable = [c for c in cells if V.get((c, arm)) and V.get((c, ref))]
    dropped = [c for c in cells if V.get((c, arm)) and not V.get((c, ref))]
    diff = {c: st.mean(V[(c, arm)]) - st.mean(V[(c, ref)]) for c in usable}
    D = st.mean(diff.values()) if diff else float("nan")
    rng = random.Random(seed); boots = []
    for _ in range(B if usable else 0):
        tot = 0.0
        for c in usable:
            a, b = V[(c, arm)], V[(c, ref)]
            tot += sum(rng.choice(a) for _ in a) / len(a) - sum(rng.choice(b) for _ in b) / len(b)
        boots.append(tot / len(usable))
    boots.sort(); lo = boots[int(0.05 * (len(boots) - 1))] if boots else float("nan"); hi = boots[int(0.95 * (len(boots) - 1))] if boots else float("nan")
    severe = [c for c, x in diff.items() if x < -SAFE]; safety = bool(severe or all_invalid)
    if len(usable) < 6 and not safety: v = "inconclusive"
    elif safety or not (D > NI): v = "does not hold"
    elif lo > NI: v = "holds"
    else: v = "direction only"
    sup = bool(usable) and lo > 0 and D >= 6
    return v, {"D": D, "ci90": [lo, hi], "cell_diff": diff, "severe_cells": severe, "all_invalid_cells": all_invalid, "dropped_cells_no_ref": dropped, "n_cells_used": len(usable),
               "safety_hit": safety, "superiority_report_only": sup}


def selftest():
    cells = [f"{c}__{v}" for c in CONDS for v in ("johnny", "fourpeople")]
    def mk(delta, sd=1.0, sev=None, kill=None, kill_ref=None, seed=1):
        r = random.Random(seed); V = {}
        for c in cells:
            base = 70 + r.gauss(0, 5); V[(c, GCC)] = [base + r.gauss(0, sd) for _ in range(3)]; V[(c, PP)] = [base + delta + r.gauss(0, sd) for _ in range(3)]
        if sev: V[(sev, PP)] = [x - 13 for x in V[(sev, GCC)]]
        if kill: V[(kill, PP)] = []
        if kill_ref: V[(kill_ref, GCC)] = []
        return V
    assert judge(mk(0.5), cells, B=2000)[0] == "holds"
    Vw = {}
    for i, c in enumerate(cells):
        Vw[(c, GCC)] = [70 + i - 6, 70 + i, 70 + i + 6]; Vw[(c, PP)] = [65 + i - 6, 65 + i, 65 + i + 6]
    v, m = judge(Vw, cells, B=2000); assert v == "direction only" and not m["severe_cells"], (v, m["D"], m["ci90"])
    assert judge(mk(-7.5), cells, B=2000)[0] == "does not hold"
    assert judge(mk(1.0, sev=cells[3]), cells, B=2000)[0] == "does not hold"
    v, m = judge(mk(1.0, kill=cells[5]), cells, B=2000); assert v == "does not hold" and m["all_invalid_cells"] == [cells[5]], m
    v, m = judge(mk(1.0, kill_ref=cells[0]), cells, B=2000); assert v == "holds" and m["dropped_cells_no_ref"] == [cells[0]] and m["n_cells_used"] == 11, m
    v, m = judge(mk(8.0), cells, B=2000); assert v == "holds" and m["superiority_report_only"], m
    print("Verdict self-test passed (7 cases)")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def collect():
    import hd720_run_metrics_v1 as RM
    s = json.load(open(MAIN / "jobs.json")); ceil = json.load(open(K / "ceilings.json"))["ceiling_kbps"]; runs = []
    for j in s["jobs"]:
        d = MAIN / j["cond"]; tag = f"{j['arm']}__{Path(j['profile']).stem}__d0__r{j['rep']}__v{j['video_id']}"; cond = Path(j["profile"]).stem
        if not d.is_dir(): runs.append({"tag": tag, "arm": j["arm"], "cond": cond, "video_id": j["video_id"], "rep": j["rep"], "valid": False, "invalid_reasons": ["Missing run directory"], "job": j["cond"]}); continue
        r = RM.run_metrics(d, tag, j["arm"], cond, ceil[j["video_id"]], light_fps_gate=(cond == "hd_c8")); r["video_id"] = j["video_id"]; r["rep"] = j["rep"]; r["job"] = j["cond"]
        if j["arm"] != GCC:
            r.update(env6_check(d, tag))
            if not r["env6_ok"]: r["valid"] = False; r["invalid_reasons"] = list(r.get("invalid_reasons", [])) + ["probing envelope v6 check did not pass:" + ";".join(r["env6_reasons"])]
        runs.append(r)
    bad = RM.code_audit(runs); return runs, bad


def main():
    runs, bad_hash = collect(); C = json.load(open(K / "contents.json")); cells = [f"{c}__{v}" for c in CONDS for v in C["main_contents"]]
    if len(bad_hash) > 0.1 * len(runs):
        (K / "AUDIT_FAILED").write_text(json.dumps(bad_hash, ensure_ascii=False))
        subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, f"Runs with code hash mismatch: {len(bad_hash)}, more than one tenth, no conclusion recorded: {bad_hash[:6]}"], check=True); return
    V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["arm"]), []).append(r["vmaf"])
    v, m = judge(V, cells)
    others = {a: judge(V, cells, arm=ARMS[a])[1] for a in ("nl",)}
    v2, m2 = judge(V, cells, arm=PP, ref=LLM)
    def agg(key, arm, cond=None):
        xs = [r[key] for r in runs if r.get("valid") and r["arm"] == arm and r.get(key) is not None and (cond is None or r["cond"] == cond)]; return st.mean(xs) if xs else None
    keys = ["env6_ceiling_frac", "env6_capped_frac", "env6_overuse_frac", "vmaf", "utility", "ssim", "psnr", "file_freeze_per_min", "webrtc_NumberFreezesPerMinute", "webrtc_MeanFreezeDurationMs", "webrtc_HarmonicFrameRate", "proxy_freeze_per_min", "loss_rate",
            "queue_delay_mean_ms", "queue_delay_p95_ms", "envelope_rewrite_frac", "decision_gap_p50_ms", "decision_gap_p95_ms", "compute_p50_ms", "obs_compute_p50_ms", "webrtc_TimeInHdPercentage", "time_to_ceiling_s", "video_kbps", "rendered_fps", "decoded_fps"]
    by_arm = {a: {k: agg(k, arm) for k in keys} for a, arm in ARMS.items()}
    by_cond = {a: {c: {k: agg(k, arm, c) for k in ("vmaf", "utility", "video_kbps", "file_freeze_per_min", "webrtc_NumberFreezesPerMinute")} for c in CONDS} for a, arm in ARMS.items()}
    n_valid = {a: sum(1 for r in runs if r["arm"] == arm and r.get("valid")) for a, arm in ARMS.items()}
    try:
        r1 = json.load(open(K_XB / "result_v1.json")); v1nl = {c: d_["vmaf"] for c, d_ in r1["by_cond"]["nl"].items()}
        cross = {"nl_minus_nlbatch_nl_vmaf_by_cond_xbatch": {c: ((by_cond["nl"][c]["vmaf"] - v1nl[c]) if (by_cond["nl"][c]["vmaf"] is not None and v1nl.get(c) is not None) else None) for c in CONDS},
                 "nlbatch_D_nl": r1["D"], "nlbatch_freeze_per_min_nl": r1["by_arm"]["nl"]["file_freeze_per_min"], "nlbatch_freeze_per_min_gcc": r1["by_arm"]["gcc200"]["file_freeze_per_min"]}
    except Exception as e: cross = {"error": repr(e)}
    gcc_c2 = {v_: st.mean([r["video_kbps"] for r in runs if r["arm"] == GCC and r["cond"] == "hd_c2" and r.get("video_id") == v_ and r.get("valid") and r.get("video_kbps") is not None] or [float("nan")]) for v_ in C["main_contents"]}
    res = {"verdict": v, **m, "other_arms_vs_gcc": {a: {k: o[k] for k in ("D", "ci90", "severe_cells", "all_invalid_cells")} for a, o in others.items()},
           "claim2_ch_vs_nl": {"verdict": v2, **m2}, "by_arm": by_arm, "by_cond": by_cond, "n_valid": n_valid, "n_runs": len(runs), "bad_hash": bad_hash,
           "gcc_c2_video_kbps_by_content": gcc_c2, "ceilings": json.load(open(K / "ceilings.json")), "contents": C,
           "invalid_runs": {r["tag"]: r["invalid_reasons"] for r in runs if not r.get("valid")}, "cross_batch_nl_report_only": cross}
    (K / "result_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    export(runs, res)
    f1 = lambda x: "none" if x is None else f"{x:.1f}"
    pc = lambda a, k: f1((by_arm[a][k] or 0) * 100)
    basis = (f"Primary endpoint D (C-H with probing envelope v6 minus Python GCC called every 200 ms, {m['n_cells_used']} cells equally weighted){m['D']:+.2f} VMAF, 90% interval [{m['ci90'][0]:+.2f}, {m['ci90'][1]:+.2f}]; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all deployed-arm runs invalid: {m['all_invalid_cells'] or 'none'}; cells excluded because all reference-arm runs of the cell were invalid {m['dropped_cells_no_ref'] or 'none'}. Report only: superiority {'reached' if m['superiority_report_only'] else 'not reached'}; D of the no-LLM multi-scale estimator with envelope v6 against GCC {others['nl']['D']:+.2f}; fraction of steps under the cap, C-H {pc('ch', 'env6_ceiling_frac')}%, multi-scale estimator {pc('nl', 'env6_ceiling_frac')}%, steps where the shadow GCC lowered the output, C-H {pc('ch', 'env6_capped_frac')}%, multi-scale estimator {pc('nl', 'env6_capped_frac')}%; cross-batch reference (multi-scale estimator with envelope v6 in hd720-closedloop-nl-v1) D {cross.get('nlbatch_D_nl', float('nan')):+.2f}, per-condition VMAF of the multi-scale estimator in this batch minus that in hd720-closedloop-nl-v1 {json.dumps({k: (round(x, 1) if x is not None else None) for k, x in (cross.get('nl_minus_nlbatch_nl_vmaf_by_cond_xbatch') or {}).items()}, ensure_ascii=False)}; mean VMAF {json.dumps({a: (round(x['vmaf'], 1) if x['vmaf'] is not None else None) for a, x in by_arm.items()}, ensure_ascii=False)}; freezes per minute of the decoded file {json.dumps({a: (round(x['file_freeze_per_min'], 2) if x['file_freeze_per_min'] is not None else None) for a, x in by_arm.items()}, ensure_ascii=False)}; inference time p50 milliseconds {json.dumps({a: (round(x['obs_compute_p50_ms'], 2) if x['obs_compute_p50_ms'] is not None else None) for a, x in by_arm.items()}, ensure_ascii=False)}; valid runs {json.dumps(n_valid, ensure_ascii=False)}/total {len(runs)}; GCC video rate at 2 Mbps {json.dumps({k: round(x, 0) for k, x in gcc_c2.items()}, ensure_ascii=False)} kbps.")
    basis2 = (f"Primary endpoint D2 (C-H with envelope v6 minus the no-LLM multi-scale estimator with envelope v6, {m2['n_cells_used']} cells equally weighted) {m2['D']:+.2f} VMAF, 90% interval [{m2['ci90'][0]:+.2f}, {m2['ci90'][1]:+.2f}]; safety line (cells worse by more than 10 points): {m2['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m2['all_invalid_cells'] or 'none'}; cells excluded because all multi-scale estimator runs of the cell were invalid {m2['dropped_cells_no_ref'] or 'none'}. Same batch and runs as claim one; for the readings see hd720-closedloop-ch-v1.")
    print(v, basis); print(v2, basis2)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    lim = ("The system under test is C-H: the conference encoder (Linear(150,1024), LayerNorm, LeakyReLU) with HCQ (λ 0.4), capacity anchoring, 50k steps, no LLM, C-H cell seed 1 of ablation-nl-enc-hcq-2x2-v1 (the middle of three seeds by offline macro MSE); the no-LLM multi-scale estimator (seed 1), the deployed arm when this batch ran, differs from C-H only in the encoder; the envelope is version 6; sequences and rate ceilings follow hd720-closedloop-v1; libwebrtc default maximum bitrate 2.5 Mbps for 960x540 and above, at 4 to 8 Mbit/s the source rate is the limit; only low-motion talking-head sequences are used; sender egress shaping, one-way delay 50 ms; 3 runs per cell; receiver inference is asynchronous (when it takes longer than 40 ms, the previous estimate is returned).")
    for cid, vv, mm, bb, crit in ((ID, v, m, basis, "Criterion as pre-registered, claim one (C-H versus GCC, non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid, verbatim the same as hd720-closedloop-nl-v1)."),
                                  (ID2, v2, m2, basis2, "Criterion as pre-registered, claim two (C-H versus the multi-scale estimator, the deployed arm when this batch ran, non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid).")):
        ex("data", "--id", cid, "--metrics", json.dumps({k: mm[k] for k in ("D", "ci90", "severe_cells", "all_invalid_cells", "n_cells_used", "superiority_report_only")} | {"n_valid": n_valid}, ensure_ascii=False, default=str),
           "--artifact", str(K / "result_v1.json"), "--artifact", str(LOCAL / "runs_tidy.csv"), "--log", str(ROOT / "logs/hd720_ch_sched.log"))
        if vv == "inconclusive":
            ex("note", "--id", cid, "Fewer than 6 usable cells; under the boundary rule fixed before the run, no conclusion is recorded." + bb); continue
        ex("conclude", "--id", cid, "--verdict", vv, "--vs-criteria", crit + bb, "--basis", bb, "--limitations", lim,
           "--next", "")


def export(runs, res):
    LOCAL.mkdir(parents=True, exist_ok=True)
    cols = ["tag", "job", "arm", "cond", "video_id", "rep", "pair", "valid", "invalid_reasons", "vmaf", "ssim", "psnr", "utility", "rate_score", "delay_score", "video_kbps", "video_kbps_after6s_median", "loss_rate",
            "queue_delay_mean_ms", "queue_delay_p95_ms", "file_freeze_per_min", "file_freeze_time_share", "decoded_fps", "webrtc_NumberFreezesPerMinute", "webrtc_MeanFreezeDurationMs", "webrtc_HarmonicFrameRate",
            "webrtc_TimeInHdPercentage", "webrtc_ReceivedWidthInPixels", "webrtc_ReceivedHeightInPixels", "proxy_freeze_per_min", "proxy_arrival_fps", "envelope_rewrite_frac", "decision_gap_p50_ms", "decision_gap_p95_ms",
            "env6_ok", "env6_gcc_err", "env6_gcc_seen_frac", "env6_ceiling_frac", "env6_capped_frac", "env6_overuse_frac", "compute_p50_ms", "compute_p95_ms", "obs_compute_p50_ms", "obs_compute_p95_ms", "time_to_ceiling_s", "ocr_in_range_fraction", "paired_frames", "rendered_fps", "sender_scale_down_events", "sender_scale_up_events", "host_busy_pct_median",
            "mem_avail_mb_min", "cpu_temp_start", "cpu_temp_end", "platform_profile", "start", "end"]
    with open(LOCAL / "runs_tidy.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in runs: w.writerow({**{k: r.get(k) for k in cols}, "invalid_reasons": ";".join(r.get("invalid_reasons", []))})
    with open(LOCAL / "runs_full.jsonl", "w", encoding="utf-8") as f:
        for r in runs: f.write(json.dumps({k: v for k, v in r.items() if k != "code_hash"}, ensure_ascii=False, default=str) + "\n")
    (LOCAL / "data_dictionary.json").write_text(json.dumps({
        "runs_tidy.csv": "One row per run; invalid_reasons lists the failed validity gates (see TESTBED.md)",
        "vmaf": "vmaf 3.2.0 v0.6.1 model, computed on the rows above label_y (contents.json), upscaled to 1920x1080, mean over every 8th frame", "ssim": "ffmpeg ssim, mean of the per-frame All value", "psnr": "ffmpeg psnr_avg per-frame mean (dB)",
        "utility": "100×(0.4R+0.4D+0.2(1−L)); R is normalized by the smaller of the capacity and the sequence rate ceiling (ceilings.json); the first 6 seconds are excluded", "video_kbps": "Primary video stream payload rate (kbit/s, from 6 seconds after shaping starts to the last packet)",
        "file_freeze_per_min": "W3C-style freezes (gap >= max(3x mean of last 30 gaps, mean+150 ms)) per minute, from the complete per-frame timestamps of the decoded file, starting 6 seconds after shaping", "decoded_fps": "Frame rate of the decoded file in the same window",
        "webrtc_*": "Statistics the receiver prints at the end of the WebRTC call", "proxy_*": "Network-side freeze proxy from frame arrival gaps (frame_gap_proxy_v1; packets are grouped into frames by a 20 ms send-time gap, so large 720p frames may be split; report only)",
        "envelope_rewrite_frac": "Fraction of decision steps where the probing envelope output differs from the raw model output by more than 1 bit/s", "time_to_ceiling_s": "seconds after shaping starts until the 5 s moving average first reaches 0.9 of min(capacity, ceiling)",
        "env6_*": "probing envelope v6 check and readings: ceiling is the fraction of steps where the cap is in place, capped is the fraction of steps where the output is lowered by the shadow GCC, overuse is the fraction of steps where the shadow GCC reports overuse, gcc_err is the shadow GCC error count", "decision_gap_*": "Wall-clock interval between adjacent decisions (milliseconds)", "compute_*": "Time spent answering each native request in the decision trace (milliseconds; from run script v13 on, inference runs on a background thread, so this value stays small even when inference is slow)", "obs_compute_*": "time per inference step (milliseconds, taken from the estimator observation trace)", "cpu_temp_*": "CPU package temperature at the start and end of the run (°C)"}, ensure_ascii=False, indent=1))
    shutil.copy(K / "result_v1.json", LOCAL / "result_v1.json")
    for extra in ("ceilings.json", "contents.json", "layout.json"):
        if (K / extra).is_file(): shutil.copy(K / extra, LOCAL / extra)
    shutil.copy(Path(__file__), LOCAL / Path(__file__).name)
    with open(LOCAL / "SHA256SUMS", "w") as f:
        for p in sorted(LOCAL.iterdir()):
            if p.name != "SHA256SUMS": f.write(f"{sha(p)}  {p.name}\n")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "jobs": build_jobs()
    elif c == "prepare": prepare()
    elif c == "judge": selftest() if "--selftest" in sys.argv else main()
