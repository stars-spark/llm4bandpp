#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Judge for registered batch hd720-highbw-ch-v1: 720p closed loop with the sender's 720p cap raised from 2.5 to 20 Mbit/s by a patched binary, at constant 3, 6, 10, 15 Mbit/s and two 4G windows, Johnny and FourPeople.
Deployed system against Python GCC called every 200 ms, 3 runs per arm and cell; criterion via hd720_ch_eval_v1.judge (non-inferiority margin 6 VMAF); a cell where both arms have all runs invalid is dropped.
Usage: hd720_highbw_v1.py jobs | judge | selftest
"""
import json, shutil, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); D_ = ROOT / "scripts/alphartc/deploy"; sys.path.insert(0, str(D_))
import hd720_ch_eval_v1 as H  # noqa: E402
import hd720_attr_loss_v1 as AL  # noqa: E402
K = Path("/path/to/testbed/results/hd720-highbw-ch-v1"); ID = "hd720-highbw-ch-v1"; RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v22.sh"
PB = D_ / "profiles/hd720_hb"; PROV = json.load(open(PB / "provenance.json"))["profiles"]; CONDS = ["hb_c3", "hb_c6", "hb_c10", "hb_c15", "hb_t1", "hb_t2"]
GCC, CH = AL.GCC, AL.CH; ARMS = {"gcc200": GCC, "ch": CH}; HB = {"STALENESS_HIGH_BITRATE": "1"}
CEIL = {"johnny": 12124.2, "fourpeople": 16058.4}


def prepare():
    K.mkdir(parents=True, exist_ok=True)
    for n in ("contents.json", "layout.json"):
        src, dst = H.K / n, K / n
        if dst.is_file(): assert dst.read_bytes() == src.read_bytes()
        else: shutil.copy(src, dst)
    (K / "ceilings.json").write_text(json.dumps({"ceiling_kbps": CEIL, "definition": "Calibration hb-calib-explore-v2 with the patched sender (720p default maximum bitrate 20000 kbps): fixed 18 Mbit/s estimate, 20 Mbit/s link, two runs per sequence; median of the per-second payload rate of the main video stream over both runs, from 6 seconds after shaping begins",
                                                 "source": "experiments/results/hb_calib_v2/summary.json"}, ensure_ascii=False, indent=1))


def jobs():
    prepare(); C = json.load(open(K / "contents.json")); layout, ly = C["layout"], C["label_y"]; J = []; order = list(ARMS); blk = 0
    for rep in range(1, AL.REPS + 1):
        for cond in CONDS:
            for content in C["main_contents"]:
                rot = order[blk % len(order):] + order[:blk % len(order)]; blk += 1
                for a in rot:
                    J.append({"cond": f"{cond}__{content}__{a}__r{rep}", "arm": ARMS[a], "profile": str(PB / f"{cond}.profile"), "rep": rep, "video_id": content,
                              "queue": PROV[cond]["queue_packets"], "source": H.source_of(content, layout), "env": dict(AL.ENV[ARMS[a]], **HB)})
    (K / "main").mkdir(parents=True, exist_ok=True); s = H.spec(ID, K / "main", J, ROOT / "logs/hd720_highbw_sched.log", ly, pairs=(1,)); s["runner"] = str(RUNNER)
    (K / "main" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("jobs:", len(J))


def judge():
    runs, bad = AL.collect(K, set())
    if not AL.audit_ok(K, ID, runs, bad): return
    hb_ok = [r["tag"] for r in runs if r.get("valid") and not any("hb/peerconnection_serverless.origin" in l for l in open(next((K / "main" / r["job"]).glob("code_*.sha256")), errors="ignore"))]
    if hb_ok:
        AL.subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "note", "--id", ID, f"Valid runs whose code hashes do not include the patched sender binary: {len(hb_ok)} (the patched sender was not in use), not judged: {hb_ok[:6]}"], check=True); return
    cells = [f"{c}__{v}" for c in CONDS for v in json.load(open(K / "contents.json"))["main_contents"]]; V = {}
    for r in runs:
        if r.get("valid") and r.get("vmaf") is not None: V.setdefault((f"{r['cond']}__{r['video_id']}", r["arm"]), []).append(r["vmaf"])
    both = [c for c in cells if not V.get((c, CH)) and not V.get((c, GCC))]
    v, m = H.judge(V, [c for c in cells if c not in both], arm=CH, ref=GCC); m["both_invalid_cells_dropped"] = both
    ba, bc = AL.by_arm_cond(runs, ARMS, CONDS); nv = {a: sum(1 for r in runs if r["arm"] == arm and r.get("valid")) for a, arm in ARMS.items()}
    res = {"verdict": v, **m, "by_arm": ba, "by_cond": bc, "n_valid": nv, "n_runs": len(runs), "bad_hash": bad, "profiles": PROV, "ceilings": CEIL, "invalid_runs": {r["tag"]: r["invalid_reasons"] for r in runs if not r.get("valid")}}
    local = ROOT / "experiments/results/hd720_highbw_ch_v1"; AL.export(K, local, runs, res)
    r1 = lambda x: None if x is None else round(x, 1)
    basis = (f"Primary endpoint D_H (deployed system C-H minus Python GCC called every 200 ms, 720p default maximum bitrate patched to 20 Mbit/s, {m['n_cells_used']} cells equally weighted) {AL.fmt(m)}; per-cell {json.dumps({c: round(x, 2) for c, x in m['cell_diff'].items()}, ensure_ascii=False)}; safety line (cells worse by more than 10 points): {m['severe_cells'] or 'none'}, cells with all C-H runs invalid: {m['all_invalid_cells'] or 'none'}, cells excluded because all GCC runs were invalid: {m['dropped_cells_no_ref'] or 'none'}, cells excluded because all runs of both arms were invalid {m['both_invalid_cells_dropped'] or 'none'}. Report only: superiority {'reached' if m['superiority_report_only'] else 'not reached'}; per-condition VMAF {json.dumps({a: {c: r1(x['vmaf']) for c, x in d.items()} for a, d in bc.items()}, ensure_ascii=False)}; per-condition video rate {json.dumps({a: {c: r1(x['video_kbps']) for c, x in d.items()} for a, d in bc.items()}, ensure_ascii=False)}; freezes per minute {json.dumps({a: (round(x['file_freeze_per_min'], 2) if x['file_freeze_per_min'] is not None else None) for a, x in ba.items()}, ensure_ascii=False)}; decoded frame rate {json.dumps({a: r1(x['decoded_fps']) for a, x in ba.items()}, ensure_ascii=False)}; probing envelope rewrite fraction {json.dumps({a: (round(x['envelope_rewrite_frac'], 3) if x['envelope_rewrite_frac'] is not None else None) for a, x in ba.items()}, ensure_ascii=False)}; valid runs {json.dumps(nv, ensure_ascii=False)}/total {len(runs)}.")
    print(v, basis)
    lim = ("The sender is a patched libwebrtc (720p default maximum bitrate changed from 2.5 to 20 Mbit/s, equivalent to the application raising maxBitrate), identical in both arms; the source is two 720p talking-head sequences (Johnny, FourPeople), with rate ceilings of about 12 and 16 Mbit/s; constant 3 to 15 Mbit/s and two UCC 4G trace windows (train, bus); single-machine testbed, sender egress shaping, one-way delay 50 milliseconds, no random packet loss; one container pair; 3 runs per cell; estimator output capped at 20 Mbit/s; run script v22.")
    AL.register(ID, v, m, basis, "Criterion as pre-registered (verbatim the same as hd720-closedloop-ch-v1: non-inferiority margin 6 VMAF, safety line 10 points and all runs of a cell invalid).", lim,
                "", K, local, nv, ROOT / "logs/hd720_highbw_sched.log")


def selftest():
    H.selftest(); assert all((PB / f"{c}.profile").is_file() for c in CONDS) and set(CEIL) == {"johnny", "fourpeople"}; print("Self-test passed: judge; 6 profiles and both sequence ceilings present")


if __name__ == "__main__":
    {"jobs": jobs, "judge": judge, "selftest": selftest}[sys.argv[1]]()
