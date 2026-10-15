#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Condition audit for parallel closed-loop batches.
Hard checks mark a run as a tool fault: applied condition equals the job, code and binary hashes agree across runs, and the run script left a result with no invalid marker; soft checks (decision interval, compute time, control points, package temperature, power mode, arm-to-pair balance) are only reported.
Usage: python3 cl_condition_audit_v1.py K_DIR JOBS.json [JOBS2.json ...], or import it and call audit().
"""
import gzip, hashlib, json, statistics as st, sys
from pathlib import Path
MON = Path("/path/to/llm4bandpp/logs/testbed_env_monitor.log")


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rows(p):
    op = gzip.open if str(p).endswith(".gz") else open
    with op(p, "rt") as f: return [json.loads(l) for l in f if l.strip()]


def first(d, pat): fs = sorted(d.glob(pat)); return fs[0] if fs else None


def load_mon():
    out = []
    if MON.exists():
        for l in MON.read_text().splitlines():
            x = l.split()
            if len(x) >= 6: out.append((int(x[0]), int(x[1]), float(x[2])))
    return out


def norm_code(lines, app_prefixes):
    """Parse code_*.sha256 lines into {relative path: hash}, replacing each pair's container directory prefix with APP so pairs compare."""
    m = {}
    for l in lines:
        if not l.strip(): continue
        h, p = l.split(None, 1); p = p.strip()
        for pre in app_prefixes:
            if p.startswith(pre): p = "APP" + p[len(pre):]; break
        m[p] = h
    return m


def audit(K, spec_files, use_monitor=True, ignore_code=(), ref_by_arm=False, ignore_injected=False):
    K = Path(K); jobs = {}; arms = set()
    for sf in spec_files:
        s = json.load(open(sf))
        for j in s["jobs"]: jobs[j["cond"]] = dict(j, env={**s.get("common_env", {}), **j.get("env", {})}); arms.add(j["arm"])
    prefixes = ["/path/to/alphartc/LLM4Band"] + [f"/path/to/testbed/p{i}" for i in range(1, 9)]
    mon = load_mon() if use_monitor else []; res, code_refs = {}, {}
    for cond, j in sorted(jobs.items()):
        d = K / cond; tag = f"{j['arm']}__{Path(j['profile']).stem}__d0__r1"; r = {"hard": [], "soft": [], "invalid": False}
        if not d.is_dir(): r["missing"] = True; res[cond] = r; continue
        summ = d / f"{tag}.json"
        if not summ.is_file() or list(d.glob("invalid_*")): r["invalid"] = True
        meta = json.load(open(d / "run_meta.json")) if (d / "run_meta.json").is_file() else {}; r["pair"] = meta.get("pair"); r["platform_profile"] = meta.get("platform_profile")
        env = j["env"]; inv0 = first(d, "invalid_*"); pre = "_".join(inv0.name.split("_")[:2]) + "_" if (r["invalid"] and inv0) else ""
        obs = first(d, f"{pre}obs_{tag}.jsonl*") or first(d, f"obs_{tag}.jsonl*"); recv = first(d, f"{pre}recv_{tag}.log*") or first(d, f"recv_{tag}.log*")
        boot = ""
        if recv:
            op = gzip.open if str(recv).endswith(".gz") else open
            with op(recv, "rt", errors="ignore") as f: boot = next((l for l in f if "[staleness] loaded" in l), "")
        if j["arm"] in ("arm_default_schema", "arm_llm4bandpp_schema"):
            es, em = env.get("STALENESS_OBS_SCHEMA", ""), env.get("STALENESS_OBS_MAP", ""); etag = "IDENTITY" if em == "IDENTITY" else ("JSON" if em else "")
            rs = [x for x in rows(obs) if "schema" in x] if obs else []
            if not rs: r["hard"].append("obs trace missing or no schema field")
            elif any(x["schema"] != es or x["map"] != etag for x in rs): r["hard"].append(f"obs trace does not match the job (expected {es}/{etag})")
            if f"schema={es} map={etag}" not in boot: r["hard"].append("receiver start-up log does not match the job")
        elif j["arm"] == "arm_default_repair":
            ef = env.get("STALENESS_OBS_FAULT", ""); er = env.get("STALENESS_OBS_REPAIR", ""); en = len(json.loads(er)) if er else 0
            rs = [x for x in rows(obs) if "fault" in x] if obs else []
            if not rs: r["hard"].append("obs trace missing or no fault field")
            elif any(x["fault"] != ef or x["n_ops"] != en for x in rs): r["hard"].append(f"obs trace does not match the job (expected {ef or 'no error'}, {en} corrections)")
            if f"fault={ef} n_ops={en}" not in boot: r["hard"].append("receiver start-up log does not match the job")
        inj = env.get("STALENESS_INJECT_DIR"); injf = first(d, "inject_*.sha256")
        if inj:
            if not injf: r["hard"].append("job requires an injection but none was recorded")
            else:
                got = {l.split(None, 1)[1].strip(): l.split()[0] for l in injf.read_text().splitlines() if l.strip()}
                want = {str(p.relative_to(inj)): sha(p) for p in Path(inj).rglob("*") if p.is_file()}
                if got != want: r["hard"].append("The injected file hash does not match the deployment directory")
        elif injf: r["hard"].append("injection record in a run without injection")
        cf = first(d, f"{pre}code_{tag}.sha256") or first(d, f"code_{tag}.sha256")
        if not cf: r["hard"].append("missing code hash") if not r["invalid"] else None
        else:
            m = norm_code(cf.read_text().splitlines(), prefixes); prof = f"APP/staleness_profiles/{Path(j['profile']).name}"
            if m.get(prof) != sha(j["profile"]): r["hard"].append("profile hash does not match the job's profile")
            core = {k: v for k, v in m.items() if not k.startswith("APP/staleness_profiles/") and "testmedia" not in k and k not in ignore_code}
            if ignore_injected and injf:
                core = {k: v for k, v in core.items() if k not in {"APP/" + l.split(None, 1)[1].strip() for l in injf.read_text().splitlines() if l.strip()}}
            rk = j["arm"] if ref_by_arm else ""; code_ref = code_refs.get(rk)
            if code_ref is None: code_refs[rk] = core
            elif ignore_injected and {k: v for k, v in core.items() if k in code_ref} != {k: v for k, v in code_ref.items() if k in core}:
                r["hard"].append(f"Code hash inconsistent with other runs of this experiment: {sorted(k for k in set(core) & set(code_ref) if core.get(k) != code_ref.get(k))[:4]}")
            elif not ignore_injected and core != code_ref: r["hard"].append(f"Code hash inconsistent with other runs of this experiment: {sorted(k for k in set(core) | set(code_ref) if core.get(k) != code_ref.get(k))[:4]}")
        if summ.is_file():
            s = json.load(open(summ)); r["gap_p95"] = s["decisions"]["decision_gap_p95_ms"]; r["cp95"] = s["decisions"]["compute_p95_ms"]; r["applies"] = s["controls"]["n_applies"]; r["dur"] = s["measurement"]["duration_s"]
        t0, t1 = meta.get("start"), meta.get("end")
        if t0 and t1:
            temps = [t for ts, t, _ in mon if t0 <= ts <= t1] + [x for x in (meta.get("cpu_temp_start"), meta.get("cpu_temp_end")) if x is not None]
            r["temp_max"] = max(temps) if temps else None
        res[cond] = r
    valid = [r for r in res.values() if "gap_p95" in r]; gmed = st.median([r["gap_p95"] for r in valid]) if valid else None
    expected_applies = {}
    for cond, r in res.items():
        if "gap_p95" in r:
            n = expected_applies.setdefault(jobs[cond]["profile"], sum(1 for l in open(jobs[cond]["profile"]) if l.startswith("wait")))
            if gmed and r["gap_p95"] > 1.5 * gmed: r["soft"].append("decision gap p95 above 1.5x the batch median")
            if r["cp95"] > 20: r["soft"].append("computation time exceeds 20 milliseconds")
            if r["applies"] != n: r["soft"].append(f"control point {r['applies']}/{n}")
            if r["dur"] < n - 8: r["soft"].append("run shorter than the profile")
        if (r.get("temp_max") or 0) >= 95: r["soft"].append(f"temperature during run {r['temp_max']}°C")
    alloc = {}
    for cond, r in res.items():
        meth = cond.split("__", 1)[1] if "__" in cond else cond; alloc.setdefault(meth, {}); alloc[meth][str(r.get("pair"))] = alloc[meth].get(str(r.get("pair")), 0) + 1
    hard = {c: r["hard"] for c, r in res.items() if r["hard"]}
    out = {"n_jobs": len(jobs), "n_present": sum(not r.get("missing") for r in res.values()), "n_invalid": sum(r["invalid"] for r in res.values()), "hard_fail": hard,
           "soft": {c: r["soft"] for c, r in res.items() if r["soft"]}, "gap_p95_median": gmed, "temp_max_overall": max((r.get("temp_max") or 0) for r in res.values()) if res else None,
           "platform_profiles": sorted({str(r.get("platform_profile")) for r in res.values() if not r.get("missing")}), "allocation_by_pair": alloc, "runs": res}
    (K / "condition_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def summary_text(a):
    return (f"Condition audit: jobs {a['n_jobs']}, run {a['n_present']}, invalid {a['n_invalid']}, hard check failures {len(a['hard_fail'])}, soft check warnings {len(a['soft'])}; power mode {a['platform_profiles']}; maximum package temperature during the run {a['temp_max_overall']}°C; median of the 95th percentile of decision interval {a['gap_p95_median']} ms.")


if __name__ == "__main__":
    a = audit(sys.argv[1], sys.argv[2:]); print(summary_text(a)); print(json.dumps(a["hard_fail"], ensure_ascii=False)[:1500])
