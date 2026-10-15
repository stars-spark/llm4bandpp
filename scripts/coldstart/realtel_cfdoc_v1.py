#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Counterfactual documentation test (registered experiment realtel-cfdoc-v1): does the designer follow the given text or recall the public specification?
In 11 mapped fields of 6 of the 7 realtel-adapter-v1 specifications, one unit or counting rule in the text is rewritten and the ground truth changes with it:
cumulative versus reset-per-read counters, bytes to kilobytes or bits, bit/s to kbit/s, percent to fraction, 8-bit fixed point to parts per ten thousand. Field names are masked as in realtel_namehide_v1.hide.
Prompt: frozen realtel-adapter-v1 template (hash checked), deepseek-flash at temperature 0, three field orders per source.
Primary endpoint: delta = S - Mm over the 33 rewritten cells, where S is the share matching the rewritten ground truth and Mm the share matching the original; source-block bootstrap, 90% interval.
Holds if the lower bound > 0 and S >= 0.80; direction only if delta > 0; does not hold if delta <= 0. Report only: full-table BA under the rewritten ground truth and parse failures.
Usage: realtel_cfdoc_v1.py build | llm | judge [--selftest]
"""
import copy, json, random, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_namehide_v1 as NH  # noqa: E402
OUT = M.OUT / "cfdoc_v1"; ID = "realtel-cfdoc-v1"; SEED = 20261008; B = 5000; S_MIN = 0.80

# Rewrite table: (source, field) -> (new text, new diff, new scale); only the unit or counting rule changes.
CF = {
 ("w3c_webrtc_stats", "packetsReceived"): ("Number of RTP packets received for this SSRC since the previous call to getStats(); the counter is reset after each call. This includes retransmissions.", False, 1.0),
 ("w3c_webrtc_stats", "bytesReceived"): ("Total number of kilobytes (units of 1000 bytes) received for this SSRC. This includes retransmissions. Calculated as defined in [RFC3550] section 6.4.1.", True, 1000.0),
 ("chrome_webrtc_internals", "[bytesReceived_in_bits/s]"): ("Page source: \"in chrome://webrtc-internals/ we also want graphs for the average rate over the last second\"; \"bytesReceived: new RateCalculator('bytesReceived', 'timestamp', CalculatorModifier.kBytesToKilobits)\"; the series is plotted in kilobits per second.", False, 1000.0),
 ("chrome_webrtc_internals", "bytesReceived"): ("Raw getStats() member plotted as a series. Definition in this build: \"Number of bytes received for this SSRC since the previous sample; the counter is reset after each sample. This includes retransmissions.\"", False, 1.0),
 ("rfc3550_rfc3611", "fraction lost"): ("fraction lost: 16 bits. The fraction of RTP data packets from source SSRC_n lost since the previous SR or RR packet was sent, expressed in parts per ten thousand (0 to 10000).", False, 1e-4),
 ("iperf3_udp_json", "bits_per_second"): ("Source: \"bandwidth = (double) irp->bytes_transferred / (double) irp->interval_duration;\" ... \"bits_per_second\": bandwidth * 8 / 1000, that is, kilobits per second.", False, 1000.0),
 ("iperf3_udp_json", "bytes"): ("Source: \"sp->result->bytes_received_total += r;\"; \"temp.bytes_transferred = sp->sender ? rp->bytes_sent_total : rp->bytes_received_total;\"; a running total since the test started.", True, 1.0),
 ("iperf3_udp_json", "lost_percent"): ("Source: \"lost_percent = (double) irp->interval_cnt_error / irp->interval_packet_count;\"; a fraction between 0 and 1.", False, 1.0),
 ("linux_tcp_info", "tcpi_data_segs_in"): ("Header: \"__u32 tcpi_data_segs_in; /* data segments received since the previous TCP_INFO read; reset on each read */\".", False, 1.0),
 ("gstreamer_rtpmanager", "packets-received"): ("\"packets-received\" G_TYPE_UINT64 number of packets received since the previous stats emission; reset on each emission", False, 1.0),
 ("gstreamer_rtpmanager", "bytes-received"): ("\"bytes-received\" G_TYPE_UINT64 total number of bits received including lower level headers overhead", True, 0.125),
}


def truth3(): return json.load(open(M.OUT / "truth_v3.json"))["truth"]


def build():
    """Return the rewritten sources, the rewritten ground truth and the altered cells {(source, feature): (original answer, new answer)}."""
    T0 = truth3(); src = {}; T1 = copy.deepcopy(T0); alt = {}
    for n, s in M.TEST.items():
        fs = []
        for (name, w, d) in s["fields"]:
            if (n, name) in CF: d = CF[(n, name)][0]
            fs.append((name, w, d))
        src[n] = {"header": s["header"], "fields": fs}
        for k, t in enumerate(T0[n]):
            if t[0] == "same" and (n, t[1]) in CF:
                _, dd, sc = CF[(n, t[1])]; T1[n][k] = ["same", t[1], dd, sc]; alt[(n, k)] = (t, T1[n][k])
    assert len(alt) == len(CF) == 11, (len(alt), len(CF))
    return src, T1, alt


def hidden():
    src, _, _ = build(); return {n: NH.hide(s) for n, s in src.items()}


def cmd_build():
    OUT.mkdir(parents=True, exist_ok=True); H = hidden(); src, T1, alt = build()
    json.dump({"sources_hidden": H, "truth_cf": T1, "altered": {f"{n}|{k}": v for (n, k), v in alt.items()}}, open(OUT / "build.json", "w"), ensure_ascii=False, indent=1)
    leak = [(n, o) for n, s in src.items() for (o, _, _), (h, w, d) in zip(s["fields"], H[n]["fields"]) if (NH.ident_like(o) and o in d) or (not NH.ident_like(o) and f'"{o}"' in d)]
    print("fields whose own name remains in their text:", leak); print(M.build_prompt(H["iperf3_udp_json"], 0).split("The fields it exposes")[1][:1200])


def cmd_llm():
    import coldstart_rule_v1 as CR
    assert M.tmpl_hash() == (M.OUT / "prompt_hash_frozen.txt").read_text().strip(), "prompt template differs from the frozen version"
    H = hidden(); OUT.mkdir(parents=True, exist_ok=True); cache = OUT / "llm_cf_deepseek.jsonl"; done = {}
    if cache.exists(): done = {(j["source"], j["pres"]): j for j in map(json.loads, open(cache)) if j.get("ok")}
    jobs = [(n, k) for n in H for k in range(M.NPRES) if (n, k) not in done]; lock = threading.Lock(); print("to run", len(jobs), flush=True)
    def work(job):
        n, k = job; r = CR.ask(M.build_prompt(H[n], k), 48000); txt = r["choices"][0]["message"].get("content") or ""
        try: mp = M.parse(txt, len(H[n]["fields"])); ok = True
        except Exception: mp, ok = None, False
        rec = {"source": n, "pres": k, "mapping": mp, "ok": ok, "tail": txt[-400:], "usage": r.get("usage", {})}
        with lock: cache.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n"); print(n, k, "parsed" if ok else "parse failure", flush=True)
    if not CR.AR.ok_to_send() or CR.AR.balance(CR.AR.KEY.read_text().strip()) < CR.AR.MIN_BALANCE: print("peak hours or balance below MIN_BALANCE; stopping"); sys.exit(2)
    with ThreadPoolExecutor(5) as ex: list(ex.map(work, jobs))
    print("balance", CR.AR.balance(CR.AR.KEY.read_text().strip()))


def cell_ok(t, fields, m):
    """Check one feature's answer against ground truth t: same field, same diff and scale within 2%."""
    return m is not None and fields[m["source"]][0] == t[1] and bool(m["diff"]) == bool(t[2]) and abs(m["scale"] - t[3]) <= 0.02 * abs(t[3])


def judge_cells(C, seed=SEED, B_=B):
    """Compute delta = S - Mm over the cells with a source-block bootstrap and return the verdict and metrics."""
    srcs = sorted({c["source"] for c in C})
    def stat(sel):
        rows = [c for s in sel for c in C if c["source"] == s]; S = sum(c["follow_doc"] for c in rows) / len(rows); Mm = sum(c["follow_memory"] for c in rows) / len(rows); return S - Mm, S, Mm
    D, S, Mm = stat(srcs); rng = random.Random(seed); bs = sorted(stat([rng.choice(srcs) for _ in srcs])[0] for _ in range(B_))
    lo, hi = bs[int(0.05 * B_)], bs[int(0.95 * B_) - 1]
    v = "does not hold" if not D > 0 else ("holds" if lo > 0 and S >= S_MIN else "direction only")
    return v, {"delta": D, "ci90": [lo, hi], "S": S, "Mm": Mm, "n_cells": len(C)}


def selftest():
    src, T1, alt = build(); T0 = truth3()
    for (n, k), (o, c) in alt.items():
        assert o[1] == c[1] and (o[2] != c[2] or abs(o[3] - c[3]) > 0.02 * abs(o[3])), (n, k, o, c)
    H = hidden(); assert all(len(H[n]["fields"]) == len(M.TEST[n]["fields"]) for n in H)
    f, _ = M.present(src["w3c_webrtc_stats"], 0); j = [x[0] for x in f].index("bytesReceived")
    assert cell_ok(T1["w3c_webrtc_stats"][2], f, {"source": j, "diff": True, "scale": 1000.0}) and not cell_ok(T1["w3c_webrtc_stats"][2], f, {"source": j, "diff": True, "scale": 1.0})
    mk = lambda pd, pm: [{"source": s, "follow_doc": int(random.Random(i * 7 + s.__hash__() % 97).random() < pd), "follow_memory": int(random.Random(i * 11 + 3).random() < pm)} for s in ("a", "b", "c", "d", "e", "f") for i in range(6)]
    assert judge_cells([{"source": s, "follow_doc": 1, "follow_memory": 0} for s in "abcdef" for _ in range(5)], B_=500)[0] == "holds"
    assert judge_cells([{"source": s, "follow_doc": int(i < 3), "follow_memory": int(i >= 3)} for s in "abcdef" for i in range(5)], B_=500)[0] in ("direction only",)
    assert judge_cells([{"source": s, "follow_doc": 0, "follow_memory": 1} for s in "abcdef" for _ in range(5)], B_=500)[0] == "does not hold"
    print("Self-test passed: all 11 rewrites changed the correct answer, field count unchanged after name masking, scoring and decision functions, holds, direction only, does not hold")


def cmd_judge():
    src, T1, alt = build(); T0 = truth3(); L = {}
    for j in map(json.loads, open(OUT / "llm_cf_deepseek.jsonl")): L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    C = []; detail = []
    for (n, k), (o, c) in alt.items():
        for p in range(M.NPRES):
            f, _ = M.present(src[n], p); mp = L.get((n, p)); m = mp[k] if mp else None
            fd, fm = int(cell_ok(c, f, m)), int(cell_ok(o, f, m)); C.append({"source": n, "follow_doc": fd, "follow_memory": fm})
            detail.append({"source": n, "feature": k, "pres": p, "answer": m, "cf_truth": c, "orig_truth": o, "follow_doc": fd, "follow_memory": fm})
    v, m = judge_cells(C)
    rows = []
    for n in M.TEST:
        for p in range(M.NPRES):
            f, _ = M.present(src[n], p); r = M.score(T1[n], f, L.get((n, p))); r.update({"source": n, "pres": p}); rows.append(r)
    ba = M.ba(rows); nfail = sum(1 for n in M.TEST for p in range(M.NPRES) if L.get((n, p)) is None)
    OUT.mkdir(parents=True, exist_ok=True); json.dump({"verdict": v, **m, "ba_cf": ba, "parse_fail": nfail, "detail": detail}, open(OUT / "judge.json", "w"), ensure_ascii=False, indent=1, default=str)
    b = (f"11 rewritten fields times 3 orders, {m['n_cells']} cells in total: against the rewritten document S {m['S']:.3f}, against the public specification Mm {m['Mm']:.3f}; Δ {m['delta']:+.3f}, 90% interval [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]. Report only: whole-table BA under the rewritten ground truth {ba:.3f} (1.000 for the original with field names masked); parse failures {nfail}/21.")
    print(v, b)
    ex = lambda *a: subprocess.run(["python3", str(ROOT / "scripts/exp.py"), *a], check=True)
    ex("data", "--id", ID, "--metrics", json.dumps({**m, "ba_cf": ba, "parse_fail": nfail}, ensure_ascii=False), "--artifact", str(OUT / "judge.json"), "--artifact", str(OUT / "llm_cf_deepseek.jsonl"))
    ex("conclude", "--id", ID, "--verdict", v, "--vs-criteria", "Criterion as pre-registered (Delta = S - Mm, lower bound > 0 and S >= 0.80 holds, Delta <= 0 does not hold)." + b, "--basis", b,
       "--limitations", "11 rewritten fields, 6 specifications, 3 orders per source; the rewrite changes only one unit or counting rule, the rest of the text is the public original; same hosted model, temperature 0; field names masked.",
       "--next", "")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "build": cmd_build()
    elif c == "llm": cmd_llm()
    elif c == "judge": selftest() if "--selftest" in sys.argv else cmd_judge()
