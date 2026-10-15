#!/usr/bin/env python3
"""Rescore the designer runs on synthetic schemas, and the small-model designer runs, from the files of this package.

The registered scoring of these runs fetched the answers and the replay results from the GPU servers before it judged.
This script repeats every step that does not need the challenge calls: it parses the saved answers with the registered
parser, checks the parsed mappings against the saved transforms and against the mappings stored in the replay results,
rebuilds the per-group rows from the saved per-call error ratios, applies the registered judge function and compares
every recorded field. It writes nothing; any difference is printed and the exit status is 1.

Modes (default: all):
  new             obsschema-openreason-newschema-v1: R1 distillations into Qwen 32B (4-bit) and 14B on the 40 groups
                  of five new schemas, real against masked field names (36 and 27 of 40 against 1).
  old             the 32 held-out groups of obsschema-llm-v1: the hosted designer (32 against 24 of 32 with names
                  masked; its full answers were not stored, so its saved mappings are checked instead of reparsed),
                  the open Qwen2.5-32B and the R1 32B and 14B (24 and 17 of 32; with the 36 above, 60 of 72 for 32B).
  designer-scale  realtel-designer-scale-v1: Qwen1.5-0.5B-Chat and Qwen2.5-7B-Instruct as designer, on the same 40
                  synthetic groups and on the 12 client stacks with real and masked field names.
The replay itself (each mapping applied to the evaluation calls, error relative to the true mapping) needs the
challenge data and runs on a server with scripts/arb/obsschema_rt_offline_v1.py eval; its outputs are the eval_*.json
files read here.

Usage: python3 scripts/coldstart/obsschema_rt_openreason_judge_offline_v1.py [new|old|designer-scale|all]
"""
import json, math, sys, warnings
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
for p in ("scripts/coldstart", "scripts/arb"): sys.path.insert(0, str(ROOT / p))
import obsschema_llm_v1 as L  # noqa: E402
import obsschema_rt_openreason_v1 as X  # noqa: E402
import obsschema_judge_v1 as OJ  # noqa: E402
R = ROOT / "experiments/results"
NEW, OLD, OPEN1, DS = R / "obsschema_rt_openreason_v1", R / "obsschema_v1", R / "openreason_v1", R / "realtel_designer_scale_v1"
ARMS = ("LLM", "LLM_OBF", "DIST", "NAME", "ORACLE")
PROBLEMS = []


def norm(x):
    """JSON round trip, so that tuples, int keys and NaN compare the way the recorded files store them."""
    return json.loads(json.dumps(x))


def same_value(a, b, rel=1e-12):
    if isinstance(a, dict) and isinstance(b, dict): return a.keys() == b.keys() and all(same_value(a[k], b[k], rel) for k in a)
    if isinstance(a, list) and isinstance(b, list): return len(a) == len(b) and all(same_value(x, y, rel) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        if isinstance(a, bool) or isinstance(b, bool): return a == b
        try: fa, fb = float(a), float(b)
        except (TypeError, ValueError): return False
        if math.isnan(fa) or math.isnan(fb): return math.isnan(fa) and math.isnan(fb)
        return math.isclose(fa, fb, rel_tol=rel, abs_tol=1e-12)
    return a == b


def check(label, mine, recorded):
    ok = same_value(norm(mine), norm(recorded))
    if not ok: PROBLEMS.append(label); print(f"  MISMATCH {label}: computed {json.dumps(norm(mine))[:200]} recorded {json.dumps(norm(recorded))[:200]}")
    return ok


def answer_part(text):
    """Reasoning models: the answer is what follows the last </think>."""
    return text.split("</think>")[-1]


def parse_synthetic(path, prefix=None, groups=None):
    """Parse every saved answer of a synthetic-schema run; returns ({group: {arm: mapping}}, [answers, parsed, hit_limit]).
    prefix keeps only ids that start with that task name; groups keeps only those group ids."""
    T, st = {}, [0, 0, 0]
    for r in map(json.loads, open(path)):
        parts = r["id"].split("|")
        if prefix is not None and parts[0] != prefix: continue
        gid, arm = parts[-2], parts[-1]
        if groups is not None and gid not in groups: continue
        st[0] += 1; st[2] += r.get("finish_reason") == "length"
        try: T.setdefault(gid, {})[arm] = L.parse(answer_part(r["text"])); st[1] += 1
        except Exception: pass   # an unparsable answer gives no mapping and counts as a failure, as registered
    return T, st


def check_eval_maps(label, T, E):
    """The replay results store the mapping each arm was replayed with; the parsed mappings must be exactly those."""
    bad = [(g, a) for g, arms in T.items() for a, mp in arms.items() if norm(E["maps"].get(g, {}).get(a)) != norm(mp)]
    extra = [(g, a) for g, m in E["maps"].items() for a in m if a.startswith("LLM") and a not in T.get(g, {})]
    if bad or extra: PROBLEMS.append(label); print(f"  MISMATCH {label}: replayed mappings differ for {bad[:5]}, replayed without a parsed answer {extra[:5]}")


def group_medians(res, arms=ARMS):
    """Median over the evaluation calls of a group of mapped error divided by true-interface error, per arm (NaN if the arm was not replayed)."""
    return {m: float(np.nanmedian([x.get(m, np.nan) for x in res.values()])) if any(m in x for x in res.values()) else float("nan") for m in arms}


def mode_new():
    print("== new: obsschema-openreason-newschema-v1 (40 groups, five new schemas)")
    G = {g["id"]: g for g in json.load(open(NEW / "groups.json"))["groups"]}
    for tag in ("rt_r1_32b", "rt_r1_14b"):
        T, st = parse_synthetic(NEW / f"out_{tag}.jsonl")
        check(f"{tag} parsed answers = transforms_{tag}.json", T, json.load(open(NEW / f"transforms_{tag}.json")))
        E = json.load(open(NEW / f"eval_{tag}.json")); check_eval_maps(f"{tag} replayed mappings", T, E)
        rows = []
        for gid, res in E["results"].items():
            g = G[int(gid)]; med = group_medians(res)
            rows.append({"id": int(gid), "cs": f"{g['scen']}|{g['draw']}", "schema": g["schema"], **{m: int(med[m] <= 1.2) for m in med}, **{"med_" + m: med[m] for m in med}})
        v, info = X.judge(rows); J = json.load(open(NEW / f"judge_{tag}.json"))
        check(f"{tag} verdict", v if len(rows) == 40 else None, J["verdict"])
        for k in ("n", "success", "best_nonllm", "delta", "ci90", "severe", "safe", "mechanism_names_matter", "per_schema"): check(f"{tag} {k}", info[k], J[k])
        check(f"{tag} parse", {"n": st[0], "parsed": st[1], "hit_limit": st[2]}, J["parse"]); check(f"{tag} rows", rows, J["rows"])
        s = info["success"]
        print(f"  {tag}: real names {s['LLM']}/{info['n']}, masked {s['LLM_OBF']}/{info['n']}, distribution {s['DIST']}, name {s['NAME']}; "
              f"delta {info['delta']:+.3f} [{info['ci90'][0]:+.3f}, {info['ci90'][1]:+.3f}]; answers parsed {st[1]}/{st[0]}, at the token limit {st[2]}; verdict {v}")


def old_rows_and_success(E, G):
    """Same computation as obsschema_judge_v1.main, without writing the judge file."""
    succ = {m: 0 for m in ("DIST", "NAME", "LLM", "LLM_OBF", "ORACLE")}; per = {}; rows = []
    for gid, res in E["results"].items():
        med = {m: float(np.nanmedian([r.get(m, np.nan) for r in res.values()])) for m in succ}; g = G[int(gid)]
        for m in succ:
            ok = bool(med[m] <= 1.2); succ[m] += ok; per.setdefault(g["schema"], {k: 0 for k in succ}); per[g["schema"]][m] += ok
        rows.append({"id": int(gid), "schema": g["schema"], "scen": g["scen"], **med})
    return succ, per, rows


def mode_old():
    print("== old: obsschema-llm-v1 held-out groups (32 groups, four schemas)")
    G = {g["id"]: g for g in json.load(open(OLD / "groups.json"))["groups"]}
    for tag, label in (("", "hosted designer"), ("_open", "Qwen2.5-32B-Instruct 4-bit, non-reasoning"), ("_r1_32b", "R1 distillation into Qwen 32B, 4-bit"), ("_r1_14b", "R1 distillation into Qwen 14B")):
        if tag == "":   # hosted: the saved record holds the parsed mapping (null when the answer did not parse)
            T = {}
            for r in map(json.loads, open(OLD / "llm_test.jsonl")): T.setdefault(str(r["id"]), {})[r["arm"]] = r["mapping"] if r.get("ok") else None
            st = None
        elif tag == "_open":   # the open non-reasoning run answered the development and the held-out groups in one file
            T, st = parse_synthetic(OLD / "open_qwen32b.jsonl", groups={str(g) for g, x in G.items() if x["phase"] == "test"})
        else:
            T, st = parse_synthetic(OPEN1 / f"out{tag}.jsonl", prefix="obsschema")
            check(f"old{tag} parse counts", st, json.load(open(OPEN1 / f"parse{tag}.json"))["obsschema"])
        check(f"old{tag} mappings = transforms_test{tag}.json", T, json.load(open(OLD / f"transforms_test{tag}.json")))
        E = json.load(open(OLD / f"eval_test{tag}.json")); check_eval_maps(f"old{tag} replayed mappings", T, E)
        with warnings.catch_warnings():   # an arm with no replayed call has an all-NaN median, as in the registered judge
            warnings.simplefilter("ignore", RuntimeWarning); succ, per, rows = old_rows_and_success(E, G)
        n = len(E["results"]); v, info = OJ.judge(succ, n); J = json.load(open(OLD / f"judge_test{tag}.json"))
        check(f"old{tag} verdict", v if n == 32 else None, J["verdict"])
        for k, x in (("n", n), ("success", succ), ("per_schema", per), ("best_nonllm", info["best_nonllm"]), ("mechanism_names_matter", info["mechanism_names_matter"]), ("rows", rows)): check(f"old{tag} {k}", x, J[k])
        ptxt = "" if st is None else f"; answers parsed {st[1]}/{st[0]}, at the token limit {st[2]}"
        print(f"  {label}: real names {succ['LLM']}/{n}, masked {succ['LLM_OBF']}/{n}, distribution {succ['DIST']}, name {succ['NAME']}{ptxt}; verdict {v}")


def mode_designer_scale():
    print("== designer-scale: realtel-designer-scale-v1")
    import realtel_adapter_v1 as M
    import realtel_scale_v1 as RS
    import realtel_designer_scale_v1 as RD
    S = RS.load_sources(); H = RD.hidden(); J = json.load(open(DS / "judge.json"))
    B = RS.base_maps(S); R_base = {b: RS.rows(S, {(n, 0): B[b][n] for n in S}) for b in B}
    for tag in ("ds_q15_05b", "ds_q25_7b"):
        T, Lr, Lh, st = {}, {}, {}, {"n": 0, "length": 0, "syn_parsed": 0, "real_parsed": 0, "hid_parsed": 0}
        for r in map(json.loads, open(DS / f"out_{tag}.jsonl")):
            st["n"] += 1; st["length"] += r.get("finish_reason") == "length"; a = answer_part(r["text"]); kind, x, y = r["id"].split("|")
            if kind == "obsschema":
                try: T.setdefault(x, {})[y] = L.parse(a); st["syn_parsed"] += 1
                except Exception: pass
            else:
                src = S if kind == "real" else H; D = Lr if kind == "real" else Lh
                try: D[(x, int(y))] = M.parse(a, len(src[x]["fields"])); st[f"{kind}_parsed"] += 1
                except Exception: D[(x, int(y))] = None
        for D, SRC in ((Lr, S), (Lh, H)):
            for n in SRC:
                for k in range(M.NPRES): D.setdefault((n, k), None)
        check(f"{tag} parsed answers = transforms_{tag}.json", T, json.load(open(DS / f"transforms_{tag}.json")))
        E = json.load(open(DS / f"eval_{tag}.json")); check_eval_maps(f"{tag} replayed mappings", T, E)
        succ = {"LLM": 0, "LLM_OBF": 0}
        for res in E["results"].values():
            for m in succ:
                vals = [x.get(m, np.nan) for x in res.values()]
                succ[m] += int(any(m in x for x in res.values()) and float(np.nanmedian(vals)) <= 1.2)
        v, m = M.judge(RS.rows(S, Lr), R_base)
        mine = {"synthetic_success": succ, "n_groups": len(E["results"]), "ba_real": m["ba_llm"], "ba_hidden": M.ba(RS.rows(H, Lh)), "delta_vs_best": m["delta"], "ci90": m["ci90"],
                "best_base": m["best_base"], "best_base_ba": m["ba_base"][m["best_base"]], "false_map_rate": m["false_map_rate"], "verdict_rule": v, "parse": st}
        for k, x in mine.items(): check(f"{tag} {k}", x, J[tag][k])
        print(f"  {tag}: 12 stacks BA {mine['ba_real']:.3f} with names, {mine['ba_hidden']:.3f} masked (best baseline {mine['best_base']} {mine['best_base_ba']:.3f}, "
              f"delta {mine['delta_vs_best']:+.3f} [{m['ci90'][0]:+.3f}, {m['ci90'][1]:+.3f}]); synthetic groups {succ['LLM']}/{mine['n_groups']} with names, {succ['LLM_OBF']} masked; parse {st}")
    print("  ds_q25_15b (Qwen2.5-1.5B-Instruct) did not run: its download was incomplete; the judge file records it as failed.")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, f in (("new", mode_new), ("old", mode_old), ("designer-scale", mode_designer_scale)):
        if mode in (name, "all"): f()
    print(f"{len(PROBLEMS)} mismatches with the recorded files" + (": " + "; ".join(PROBLEMS) if PROBLEMS else ""))
    sys.exit(1 if PROBLEMS else 0)


if __name__ == "__main__":
    main()
