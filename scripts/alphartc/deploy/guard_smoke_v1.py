#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exploratory smoke test of the startup guard (ch-startup-guard-smoke-explore-v1; no criterion, not paper evidence).
Low-bandwidth part at 100 to 400 kbps: deployed estimator without envelope, collector v7, guard on (estimate capped at 300 kbps until all five long windows have packets), plus a guard-off split and a LLM4Band reference run; 720p part: deployed system with guard on, hd_c1 and hd_c8.
Usage: guard_smoke_v1.py jobs | summarize
"""
import glob, gzip, json, re, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path("/path/to/llm4bandpp"); K = Path("/path/to/testbed/results/ch-guard-smoke-v1"); ID = "ch-startup-guard-smoke-explore-v1"
RUNNER = ROOT / "scripts/alphartc/run_staleness_once_twocontainer_midsnap_v19.sh"
P = ROOT / "scripts/alphartc/deploy/profiles/lowbw_nl"
REF_LOW = Path("/path/to/testbed/results/lowbw-ch-vs-conf-v1"); REF_HD = Path("/path/to/testbed/results/hd720-closedloop-ch-v1")
ARMS = {"g1": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_COLLECTOR": "v7", "STALENESS_STARTUP_GUARD": "1"}),
        "v7": ("arm_ch_x", {"STALENESS_ENVELOPE": "0", "STALENESS_COLLECTOR": "v7"}),
        "cf0": ("arm_llm4band_conf_x", {"STALENESS_ENVELOPE": "0", "STALENESS_COLLECTOR": "v6"})}
LOW = [(100, "g1", 3), (200, "g1", 2), (300, "g1", 1), (400, "g1", 1), (100, "v7", 1), (100, "cf0", 1)]
HD = [("hd_c1", "johnny"), ("hd_c8", "johnny")]
sys.path.insert(0, str(ROOT / "scripts/alphartc/deploy")); import testbed_parallel_equiv_v1 as G  # noqa: E402


def low_spec(J):
    import power_profile_v1 as PW; pw = PW.ensure("balanced")
    env = dict(G.COMMON); env["STALENESS_CAPTURE_MEDIA"] = "1"
    return {"power_profile": pw, "name": "low", "K": str(K / "low"), "log": str(ROOT / "logs/guard_smoke_v1.log"), "runner": str(RUNNER),
            "quality_script": "scripts/alphartc/deploy/qoe_quality_once_v2.py", "quality_args": ["--ocr-jobs", "4", "--vmaf-threads", "4"],
            "source": "testmedia/qoe_labeled_medium_320x240.yuv", "media": True, "vmaf_workers": 1, "max_pending": 3, "stagger_s": 7, "common_env": env,
            "phases": [{"name": "low", "pairs": [1, 2], "vmaf": "async"}], "jobs": [dict(j, phase="low") for j in J]}


def jobs():
    import hd720_ch_eval_v1 as H
    J = []
    for rep in (1, 2, 3):
        for cap, a, n in LOW:
            if rep <= n:
                arm, env = ARMS[a]; J.append({"cond": f"c{cap}__{a}__r{rep}", "arm": arm, "profile": str(P / f"nlc_{cap}.profile"), "env": dict(env)})
    K.mkdir(parents=True, exist_ok=True); (K / "jobs_low.json").write_text(json.dumps(low_spec(J), ensure_ascii=False, indent=1)); print("low-bandwidth workload", len(J))
    C = json.load(open(REF_HD / "contents.json")); layout, ly = C["layout"], C["label_y"]; JH = []
    for cond, content in HD:
        JH.append({"cond": f"{cond}__{content}__g1__r1", "arm": H.PP, "profile": str(H.P / f"{cond}.profile"), "rep": 1, "video_id": content, "queue": H.queue_of(cond),
                   "source": H.source_of(content, layout), "env": dict(H.arm_env(H.PP), STALENESS_COLLECTOR="v7", STALENESS_STARTUP_GUARD="1")})
    (K / "hd").mkdir(parents=True, exist_ok=True)
    s = H.spec("hd", K / "hd", JH, ROOT / "logs/guard_smoke_v1_hd.log", ly); s["runner"] = str(RUNNER)
    assert s["jobs"][0]["env"] == {"STALENESS_COLLECTOR": "v7", "STALENESS_ENVELOPE": "6", "STALENESS_STARTUP_GUARD": "1"}, s["jobs"][0]["env"]
    for n in ("contents.json", "ceilings.json", "layout.json"):
        if (REF_HD / n).is_file(): (K / n).write_bytes((REF_HD / n).read_bytes())
    (K / "hd" / "jobs.json").write_text(json.dumps(s, ensure_ascii=False, indent=1)); print("720p job", len(JH))


def obs_rows(d):
    fs = glob.glob(str(d / "obs_*.jsonl*")) + glob.glob(str(d / "invalid_*obs_*.jsonl*"))
    if not fs: return []
    op = gzip.open if fs[0].endswith(".gz") else open
    with op(fs[0], "rt") as f: return [json.loads(l) for l in f if l.strip()]


def startup(d):
    """Return startup readings: guard release time (s), estimate at release and peak estimate in the first 6 s (kbps)."""
    O = [o for o in obs_rows(d) if "est_bps" in o]
    if not O: return None
    t0 = O[0]["t_ms"]; rel = next((o for o in O if o.get("guard_on") is False), None)
    head = [o["est_bps"] / 1000 for o in O if o["t_ms"] - t0 <= 6000]
    xs = sorted(o["est_bps"] / 1000 for o in O); q = lambda p: round(xs[int(p * (len(xs) - 1))], 1)
    return {"guard_seen": any("guard_on" in o for o in O), "release_s": round((rel["t_ms"] - t0) / 1000, 2) if rel and O[0].get("guard_on") else None,
            "est_at_release_kbps": round(rel["est_bps"] / 1000, 1) if rel and O[0].get("guard_on") else None, "head6s_max_kbps": round(max(head), 1) if head else None,
            "est_p50_kbps": q(.5), "est_p95_kbps": q(.95), "n": len(O)}


def boot_ok(d, arm):
    txt = "".join(l for f in glob.glob(str(d / "recv_*.log*")) + glob.glob(str(d / "invalid_*recv_*.log*"))
                  for l in (gzip.open(f, "rt", errors="ignore") if f.endswith(".gz") else open(f, errors="ignore")) if "[staleness]" in l)
    return f"loaded {arm}" in txt and "async_infer deadline_ms=40 enabled=True" in txt


def low_run(d, arm, cap):
    tag = f"{arm}__nlc_{cap}__d0__r1"; js = d / f"{tag}.json"; inv = [p.name for p in d.glob("invalid_*")]
    r = {"valid": js.is_file() and not inv, "boot_ok": boot_ok(d, arm), "startup": startup(d)}
    src = js if js.is_file() else next((q for q in d.glob("invalid_*.json") if re.fullmatch(r"invalid_\d+_" + re.escape(tag) + r"\.json", q.name)), None)
    if src:
        n = json.load(open(src))["network"]; r.update({"utility": n["utility"], "video_kbps": n.get("primary_video_payload_rate_kbps"), "queue_delay_mean_ms": n.get("queue_delay_mean_ms")})
    return r


def summarize():
    import hd720_run_metrics_v1 as RM
    out = {"low": [], "hd": [], "ref_low": {}, "ref_hd": {}}
    for j in json.load(open(K / "jobs_low.json"))["jobs"]:
        cap, a, rep = j["cond"].split("__"); cap = int(cap[1:]); d = K / "low" / j["cond"]
        out["low"].append({"cond": j["cond"], "cap": cap, "arm_key": a, **(low_run(d, j["arm"], cap) if d.is_dir() else {"valid": False, "missing": True})})
    for cap in (100, 200, 300, 400):
        for a in ("ch0", "cf0"):
            rs = [low_run(REF_LOW / "main" / f"c{cap}__{a}__r{rep}", "arm_ch_x" if a == "ch0" else "arm_llm4band_conf_x", cap) for rep in (1, 2, 3)]
            out["ref_low"][f"c{cap}__{a}"] = {"valid": sum(r["valid"] for r in rs), "utility": [round(r["utility"], 1) if r.get("utility") is not None else None for r in rs],
                                              "head6s_max_kbps": [(r["startup"] or {}).get("head6s_max_kbps") for r in rs]}
    ceil = json.load(open(K / "ceilings.json"))["ceiling_kbps"]
    for j in json.load(open(K / "hd" / "jobs.json"))["jobs"]:
        d = K / "hd" / j["cond"]; cond = Path(j["profile"]).stem; tag = f"{j['arm']}__{cond}__d0__r1__v{j['video_id']}"
        r = RM.run_metrics(d, tag, j["arm"], cond, ceil[j["video_id"]], light_fps_gate=(cond == "hd_c8")) if d.is_dir() else {"valid": False}
        out["hd"].append({"cond": j["cond"], **{k: r.get(k) for k in ("valid", "invalid_reasons", "vmaf", "ssim", "file_freeze_per_min", "video_kbps", "loss_rate")}, "startup": startup(d)})
        ref = []
        for rep in (1, 2, 3):
            dr = REF_HD / "main" / f"{cond}__{j['video_id']}__ch__r{rep}"; tr = f"{j['arm']}__{cond}__d0__r{rep}__v{j['video_id']}"
            x = RM.run_metrics(dr, tr, j["arm"], cond, ceil[j["video_id"]], light_fps_gate=(cond == "hd_c8")); ref.append({k: x.get(k) for k in ("valid", "vmaf", "file_freeze_per_min", "video_kbps")})
        out["ref_hd"][j["cond"]] = ref
    LOCAL = ROOT / "experiments/results/ch_guard_smoke_v1"; LOCAL.mkdir(parents=True, exist_ok=True)
    for p in (LOCAL / "summary.json", K / "summary.json"): p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    f = []
    for cap, a, _ in LOW:
        rs = [r for r in out["low"] if r["cap"] == cap and r["arm_key"] == a]
        f.append(f"{cap} kbps {a}: valid {sum(r['valid'] for r in rs)}/{len(rs)}, utility {[round(r['utility'], 1) if r.get('utility') is not None else None for r in rs]}, guard released at {[(r.get('startup') or {}).get('release_s') for r in rs]} s, maximum estimate {[(r.get('startup') or {}).get('head6s_max_kbps') for r in rs]} kbps in first 6 s")
    for h in out["hd"]:
        rf = out["ref_hd"][h["cond"]]
        f.append(f"720p {h['cond']}: valid {h['valid']}, VMAF {h.get('vmaf')}, freezes per minute {h.get('file_freeze_per_min')}; VMAF without the guard in an earlier batch {[x.get('vmaf') for x in rf]}")
    finding = ";".join(f) + f". Cross-batch reference lowbw-ch-vs-conf-v1: {json.dumps(out['ref_low'], ensure_ascii=False)}. Startup logs all correct: {all(r.get('boot_ok') for r in out['low'] if not r.get('missing'))}."
    print(finding)
    subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "explore", "--id", ID,
                    "--what", "Exploratory smoke test of a startup guard for C-H: collector v7 plus the guard (the estimate stays at or below 300 kbps until all five 600 ms windows have seen packets); low bandwidth at 100 kbps 3 times, 200 kbps 2 times, 300 and 400 kbps once each, plus a split arm (only the collector changed) and a LLM4Band reference run once each; 720p deployed system on hd_c1 and hd_c8 once each; run script v19.",
                    "--finding", finding, "--why", "lowbw-ch-vs-conf-v1 did not hold because C-H overestimates at the start of the call; this exploratory smoke test tries a startup guard before any confirmatory batch.",
                    "--parent", "lowbw-ch-vs-conf-v1", "--artifact", str(LOCAL / "summary.json"),
                    "--next", ""], check=True)


if __name__ == "__main__":
    {"jobs": jobs, "summarize": summarize}[sys.argv[1]]()
