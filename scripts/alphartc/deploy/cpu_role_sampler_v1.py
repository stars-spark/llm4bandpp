#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-role CPU and memory sampler for one testbed run (report-only).
Each second it scans host /proc for processes whose command line contains MARK and groups them by role: main or competing call, sender or receiver, Python shell (runs the estimator) or native process; it also logs host busy ratio and free memory, and exits on TERM.
Usage: cpu_role_sampler_v1.py MARK OUT.jsonl MAX_SECONDS | --selftest
"""
import json, os, signal, sys, time
HZ = os.sysconf("SC_CLK_TCK"); PAGE = os.sysconf("SC_PAGE_SIZE"); RUN = [True]


def role_of(cmd):
    comp = "comp_" if "config_comp_" in cmd else ""
    side = "sender" if "config_sender" in cmd or "config_comp_sender" in cmd else ("receiver" if "config_receiver" in cmd or "config_comp_receiver" in cmd else "other")
    kind = "native" if ".origin" in cmd else ("wrapper" if "peerconnection_serverless" in cmd else "other")
    return f"{comp}{side}_{kind}"


def scan(mark):
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit(): continue
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode("utf8", "ignore")
            if mark not in cmd or "cpu_role_sampler" in cmd: continue
            st = open(f"/proc/{pid}/stat").read().rsplit(") ", 1)[1].split()
            out[pid] = {"role": role_of(cmd), "cpu_s": (int(st[11]) + int(st[12])) / HZ, "rss_mb": int(st[21]) * PAGE / 2 ** 20}
        except Exception: continue
    return out


def host():
    v = [int(x) for x in open("/proc/stat").readline().split()[1:9]]; return sum(v), v[3] + v[4]


def mem_avail_mb():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable:"): return int(l.split()[1]) / 1024
    return None


def main(mark, out, dur):
    signal.signal(signal.SIGTERM, lambda *_: RUN.__setitem__(0, False)); signal.signal(signal.SIGINT, lambda *_: RUN.__setitem__(0, False))
    t0 = time.time(); prev = scan(mark); ht, hi = host()
    with open(out, "w") as f:
        while RUN[0] and time.time() - t0 < dur:
            time.sleep(1.0); cur = scan(mark); nt, ni = host(); roles = {}
            for pid, c in cur.items():
                p = prev.get(pid)
                if p is None: continue
                r = roles.setdefault(c["role"], {"cpu_pct": 0.0, "rss_mb": 0.0, "n": 0})
                r["cpu_pct"] += (c["cpu_s"] - p["cpu_s"]) * 100.0; r["rss_mb"] += c["rss_mb"]; r["n"] += 1
            f.write(json.dumps({"t_ms": int(time.time() * 1000), "host_busy_pct": round(100.0 * (1 - (ni - hi) / max(nt - ht, 1)), 1), "mem_avail_mb": round(mem_avail_mb() or -1),
                                "roles": {k: {"cpu_pct": round(v["cpu_pct"], 1), "rss_mb": round(v["rss_mb"], 1), "n": v["n"]} for k, v in roles.items()}}) + "\n"); f.flush()
            prev, ht, hi = cur, nt, ni


def selftest():
    assert role_of("python3 peerconnection_serverless /app/x/config_receiver_t.json") == "receiver_wrapper"
    assert role_of("/usr/bin/peerconnection_serverless.origin /app/x/config_comp_sender_t.json") == "comp_sender_native"
    assert role_of("python3 /app/x/config_sender_t.json") == "sender_other"
    assert role_of("peerconnection_serverless /app/x/config_comp_receiver_t.json") != "receiver_wrapper"
    print("Role classification self-test passed")


if __name__ == "__main__":
    if sys.argv[1] == "--selftest": selftest()
    else: main(sys.argv[1], sys.argv[2], float(sys.argv[3]))
