#!/usr/bin/env python3
"""Per-stack results of the designer on the 12 held-out client stacks (realtel-scale-v1), the table the supplement refers to.

Reads the saved designer mappings (experiments/results/realtel_scale_v1/llm_deepseek.jsonl, three field orders per
stack), the seven baseline mappings rebuilt from the saved similarity scores, and the ground truth in sources.json, and
scores them with the registered functions (realtel_adapter_v1.score through realtel_scale_v1.rows). Writes
experiments/results/realtel_scale_v1/per_stack.csv with, per stack: the scored features with their labels, the
designer's correct decisions over the three orders and its errors, and each baseline's correct decisions (field order 0,
as in the registered comparison).

Checks against the recorded judge.json and the supplement: the designer's and every baseline's BA, the count of stacks
correct on every scored feature in all orders (8 of the 11 stacks that have scored features; the recorded judge.json
reports 9 because it was written before stacks without scored features were left out of that count, and LiveKit has
none), the 12 errors on three stacks, and the BA of 0.938 with the ns-3 minimum-delay cell left unscored.

Usage: python3 scripts/paper/make_designer_per_stack_v1.py
"""
import csv, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/coldstart"))
import realtel_adapter_v1 as M  # noqa: E402
import realtel_scale_v1 as RS  # noqa: E402
OUT = RS.OUT / "per_stack.csv"
BASES = ("CUPID", "COMA", "SF", "NAME", "TFIDF", "BGE", "MPNET")
PAPER = {"stacks_scored": 11, "stacks_all_correct": 8, "errors": 12, "error_stacks": 3, "ba_designer": 0.920, "ba_cupid": 0.560, "ba_ns3_unscored": 0.938}


def label(k, t):
    if t[0] == "same": return f"{k} {M.SHORT[k]}: same ({t[1]}, {'difference' if t[2] else 'value'}, x{t[3]:g})"
    return f"{k} {M.SHORT[k]}: none"


def decisions(S, n, mp, k_pres):
    """Per scored feature of stack n in field order k_pres: (feature, correct, what the method answered)."""
    f, _ = M.present(S[n], k_pres); out = []
    for k, t in enumerate(S[n]["truth"]):
        if t[0] not in ("same", "none"): continue
        m = mp[k] if mp else None
        if t[0] == "same":
            ok = m is not None and f[m["source"]][0] == t[1] and bool(m["diff"]) == bool(t[2]) and abs(m["scale"] - t[3]) <= 0.02 * abs(t[3])
        else:
            ok = m is None
        ans = "missing" if m is None else f"{f[m['source']][0]}, {'difference' if m['diff'] else 'value'}, x{m['scale']:g}"
        out.append((k, ok, ans))
    return out


def main():
    S = RS.load_sources(); L = {}
    for j in map(json.loads, open(RS.OUT / "llm_deepseek.jsonl")): L[(j["source"], j["pres"])] = j["mapping"] if j.get("ok") else None
    for n in S:
        for k in range(M.NPRES): L.setdefault((n, k), None)
    B = RS.base_maps(S)
    # consistency of the decision-level count with the registered scoring
    R_llm = RS.rows(S, L); R_base = {b: RS.rows(S, {(n, 0): B[b][n] for n in S}) for b in B}
    J = json.load(open(RS.OUT / "judge.json")); problems = []
    if abs(M.ba(R_llm) - J["ba_llm"]) > 1e-12: problems.append(f"designer BA {M.ba(R_llm)} vs recorded {J['ba_llm']}")
    for b in B:
        if abs(M.ba(R_base[b]) - J["ba_base"][b]) > 1e-12: problems.append(f"{b} BA {M.ba(R_base[b])} vs recorded {J['ba_base'][b]}")
    rows, n_all, errors = [], 0, []
    for n, s in S.items():
        scored = [(k, t) for k, t in enumerate(s["truth"]) if t[0] in ("same", "none")]
        n_same = sum(t[0] == "same" for _, t in scored); n_none = len(scored) - n_same
        dec = {p: decisions(S, n, L[(n, p)], p) for p in range(M.NPRES)}
        ok_same = sum(ok for p in dec for k, ok, _ in dec[p] if s["truth"][k][0] == "same"); ok_none = sum(ok for p in dec for k, ok, _ in dec[p] if s["truth"][k][0] == "none")
        err = [(p, k, a) for p in dec for k, ok, a in dec[p] if not ok]; errors += [(n, p, k, a) for p, k, a in err]
        all_ok = (not err) if scored else None; n_all += bool(all_ok)
        row = {"stack": n, "scored_features": len(scored), "mappable": n_same, "unmappable": n_none,
               "feature_labels": "; ".join(label(k, t) for k, t in scored) or "(no scored feature)",
               "designer_mappable_correct": f"{ok_same}/{3 * n_same}", "designer_unmappable_correct": f"{ok_none}/{3 * n_none}",
               "designer_all_correct_all_orders": "" if all_ok is None else ("yes" if all_ok else "no"),
               "designer_errors": "; ".join(f"order {p} feature {k} ({M.SHORT[k]}): answered {a}" for p, k, a in err)}
        for b in BASES:
            d = decisions(S, n, B[b][n], 0)
            row[f"{b}_mappable_correct"] = f"{sum(ok for k, ok, _ in d if s['truth'][k][0] == 'same')}/{n_same}"
            row[f"{b}_unmappable_correct"] = f"{sum(ok for k, ok, _ in d if s['truth'][k][0] == 'none')}/{n_none}"
            row[f"{b}_all_correct"] = "" if not scored else ("yes" if all(ok for _, ok, _ in d) else "no")
        rows.append(row)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    n_scored = sum(r["scored_features"] > 0 for r in rows); err_stacks = sorted({e[0] for e in errors})
    # the ns-3 minimum one-way delay cell left unscored
    S2 = {n: dict(s, truth=[["kind"] if (n.startswith("ns-3") and k == 5) else t for k, t in enumerate(s["truth"])]) for n, s in S.items()}
    ba_ns3 = M.ba(RS.rows(S2, L))
    rec9 = J["sources_all_correct_all_pres"]; rec_ok = {n: v for n, v in J["per_source_all_correct"].items()}
    mine_ok = {r["stack"]: r["designer_all_correct_all_orders"] == "yes" for r in rows if r["scored_features"]}
    if any(rec_ok[n] != v for n, v in mine_ok.items()): problems.append("per-stack all-correct flags differ from judge.json")
    got = {"stacks_scored": n_scored, "stacks_all_correct": n_all, "errors": len(errors), "error_stacks": len(err_stacks), "ba_designer": round(M.ba(R_llm), 3), "ba_cupid": round(M.ba(R_base["CUPID"]), 3), "ba_ns3_unscored": round(ba_ns3, 3)}
    for k, v in PAPER.items():
        if got[k] != v: problems.append(f"{k}: computed {got[k]}, paper {v}")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(rows)} stacks)")
    print(f"stacks with scored features: {n_scored}; designer correct on every scored feature in all three orders: {n_all}")
    print(f"recorded judge.json: {rec9} (it also counts LiveKit, which has no scored feature: {rec_ok.get('LiveKit protocol')})")
    print(f"designer errors: {len(errors)} on {', '.join(err_stacks)}")
    for e in errors: print(f"  {e[0]}, order {e[1]}, feature {e[2]} ({M.SHORT[e[2]]}): answered {e[3]}")
    print(f"BA designer {got['ba_designer']:.3f}, Cupid {got['ba_cupid']:.3f}; with the ns-3 minimum-delay cell unscored {got['ba_ns3_unscored']:.3f}")
    print(f"{len(problems)} problems" + (": " + "; ".join(problems) if problems else ""))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
