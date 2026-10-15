#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Post hoc rescoring of realtel-adapter-v1 and realtel-baseline-strength-v1 with the third version of the ground truth.
Two independent LLM checks, blind to every method output, found mislabelled cells in the first version and rules applied inconsistently (direction, combination of several fields, the official feature definitions).
Version 2 changed 20 cells; version 3 changes 16 more: 14 that both checks proposed (features 6 and 7 of the six sources with round-trip fields, feature 8 of iperf3 and tcp_info) and two groups that one check proposed, labelled different definition because disputed (Chrome 12 and 13, tcp_info 2).
Every change turns a scored cell into an unscored one; scoring rules, thresholds and criteria are unchanged.
Also reports a sensitivity analysis that scores the different-definition cells as features to be declared missing.
Writes truth_v3.json and revise_v3.json in experiments/results/realtel_adapter_v1.
Usage: python3 realtel_revise_v1.py [--register]
"""
import json, random, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_baselines_v2 as V  # noqa: E402
RTT_SRC = ["w3c_webrtc_stats", "chrome_webrtc_internals", "rfc3550_rfc3611", "quic_qlog", "linux_tcp_info", "gstreamer_rtpmanager"]


def truth_v3():
    T = json.load(open(M.OUT / "truth_v2.json"))["truth"]; T = {n: [list(x) for x in t] for n, t in T.items()}; chg = []
    def to_kind(n, k, why):
        assert T[n][k][0] != "kind", (n, k); chg.append([n, k, T[n][k][0], "kind", why]); T[n][k] = ["kind"]
    for n in RTT_SRC:
        for k in (6, 7): to_kind(n, k, "the round-trip field can likewise yield a ratio and a difference, same basis as features 3 and 5 (checker A and checker B agree)")
    for n in ("iperf3_udp_json", "linux_tcp_info"): to_kind(n, 8, "The inter-arrival time can be obtained by dividing the window length by the packet count, the same quantity as feature 0 for the rate (checker A and checker B agree)")
    for k in (12, 13): to_kind("chrome_webrtc_internals", k, "One can use the frame interval field that only video streams have to distinguish streams and then combine the proportions; checker A leans toward changing it, checker B leans toward keeping it, disputed, labelled a different definition.")
    to_kind("linux_tcp_info", 2, "tcpi_bytes_received counts only new bytes delivered in order; under loss and reordering it is not equal to the official \"bytes received within the window\"; checker A is unsure, disputed cases are labelled a different definition")
    return T, chg


def rows_full(T, maps):
    """maps: {(source, field order): mapping}; full scoring of field, differencing and scale."""
    out = []
    for (n, k), mp in maps.items():
        f, _ = M.present(M.TEST[n], k); r = M.score(T[n], f, mp); r.update({"source": n, "pres": k}); out.append(r)
    return out


def rows_id(T, decs):
    """decs: {(source, field order): chosen field index or None per feature}; scores the chosen field only."""
    out = []
    for (n, k), dec in decs.items():
        f, _ = M.present(M.TEST[n], k); r = V.score_id(T[n], f, dec); r["source"] = n; out.append(r)
    return out


def kind_as_none(T): return {n: [x if x[0] != "kind" else ["none"] for x in t] for n, t in T.items()}


def llm_maps(path):
    L = {}
    for l in open(path):
        j = json.loads(l)
        if "source" in j: L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
        else:
            _, n, k = j["id"].split("|")
            try: L[(n, int(k))] = M.parse(j["text"], len(M.TEST[n]["fields"]))
            except Exception: L[(n, int(k))] = None
    for n in M.TEST:
        for k in range(M.NPRES): L.setdefault((n, k), None)
    return L


def dec_of(mp): return [None if (mp is None or m is None) else m["source"] for m in (mp or [None] * 15)]


def run(T):
    res = {}
    L = llm_maps(M.OUT / "llm_test_deepseek.jsonl")
    # 1. realtel-adapter-v1: full scoring against NAME and TFIDF as in v1 (mappings at the development thresholds, field order 0).
    Bj = json.load(open(M.OUT / "baselines.json"))
    R_llm = rows_full(T, L); R_base = {b: rows_full(T, {(n, 0): Bj[b]["maps"][n] for n in M.TEST}) for b in Bj}
    v, m = M.judge(R_llm, R_base); res["adapter_v1"] = {"verdict": v, **m}
    # 2. realtel-baseline-strength-v1: chosen field only, seven baselines at their development thresholds.
    S = V.classic_scores(); S.update(json.load(open(V.OUT / "scores_valentine.json"))); S.update(json.load(open(V.OUT / "scores_embed.json")))
    taus = json.load(open(V.OUT / "judge.json"))["baselines"]
    Rb = {b: rows_id(T, {(n, 0): V.decide(sc["test"][n], taus[b]["tau"]) for n in M.TEST}) for b, sc in S.items()}
    Rl = rows_id(T, {key: dec_of(mp) for key, mp in L.items()}); v2, m2 = V.judge(Rl, Rb); res["strength_v1"] = {"verdict": v2, **m2}
    res["open_id"] = {t: V.ba(rows_id(T, {key: dec_of(mp) for key, mp in llm_maps(M.OUT / f"out_open_{t}.jsonl").items()})) for t in ("r1_32b", "r1_14b")}
    res["open_full"] = {t: M.ba(rows_full(T, llm_maps(M.OUT / f"out_open_{t}.jsonl"))) for t in ("r1_32b", "r1_14b")}
    res["counts"] = {c: sum(x[0] == c for t in T.values() for x in t) for c in ("same", "none", "kind")}
    return res


def fmt(r):
    a, s = r["adapter_v1"], r["strength_v1"]
    return (f"label count {r['counts']}. adapter: DeepSeek full scoring BA {a['ba_llm']:.3f}, NAME {a['ba_base']['NAME']:.3f}, TFIDF {a['ba_base']['TFIDF']:.3f}, Δ {a['delta']:+.3f} [{a['ci90'][0]:+.3f}, {a['ci90'][1]:+.3f}], mis-mapping {a['false_map_rate']:.3f}, criterion {a['verdict']}. strength (fields only): DeepSeek {s['ba_llm']:.3f}, control " + ",".join(f"{b} {x:.3f}" for b, x in s["ba_base"].items()) + f", best {s['best_base']}, Δ {s['delta']:+.3f} [{s['ci90'][0]:+.3f}, {s['ci90'][1]:+.3f}], verdict {s['verdict']}. Open models, fields only {json.dumps({k: round(x, 3) for k, x in r['open_id'].items()})}, full scoring {json.dumps({k: round(x, 3) for k, x in r['open_full'].items()})}.")


def main():
    T, chg = truth_v3(); json.dump({"truth": T, "changes_over_v2": chg}, open(M.OUT / "truth_v3.json", "w"), ensure_ascii=False, indent=1)
    main_r = run(T); sens = run(kind_as_none(T))
    json.dump({"v3": main_r, "sensitivity_kind_as_missing": sens}, open(M.OUT / "revise_v3.json", "w"), ensure_ascii=False, indent=1)
    print("Version 3:", fmt(main_r)); print("Sensitivity (different-definition cells scored as missing):", fmt(sens))
    if "--register" in sys.argv:
        reason = ("Two independent LLM checks (neither saw any method output; A compared line by line with the original text, B first derived the labels blind and then compared, two rounds) found errors in the first ground truth, and found that the relation rules fixed before the runs (sender-side counts as same kind, multi-field combinations and event aggregation count as same kind) were applied inconsistently with the official feature definition (data/audit_bench_v1/official_feature_spec.txt; jitter is the standard deviation of arrival intervals in the window). The third version changes 36 cells, all from scored to unscored, a direction unfavorable to the LLM; changes both checks agreed on were adopted directly, and those raised by only one were adopted under the rule that disputed cells count as same kind. Check records: experiments/results/realtel_adapter_v1/gt_review/, labels truth_v3.json.")
        for eid, key in (("realtel-adapter-v1", "adapter_v1"), ("realtel-baseline-strength-v1", "strength_v1")):
            r = main_r[key]
            subprocess.run(["python3", str(ROOT / "scripts/exp.py"), "revise", "--id", eid, "--reason", reason,
                            "--criteria", "The scoring rules, thresholds, safety line, resampling and controls are all unchanged; only the ground truth is replaced with version 3 (same quantity 11, none 24, different definition 70 not scored); the sensitivity analysis separately reports the different-definition cells scored as missing.",
                            "--verdict", r["verdict"], "--basis", fmt(main_r) + " Sensitivity (different-definition cells scored as features to be declared missing):" + fmt(sens)], check=True)


if __name__ == "__main__":
    main()
