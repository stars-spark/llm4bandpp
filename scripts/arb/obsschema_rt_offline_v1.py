#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Server side of obsschema-openreason-newschema-v1 (criteria in its pre-registration).
Five new foreign schemas (test_g to test_j, plus rt_getstats on getStats conventions), 8 groups each: per scenario two new sets of 13 calls (3 evidence, 10 evaluation), excluding every call used by obsschema-llm-v1 and by the sensitivity test; the same calls are shared by the five schemas.
The evaluation is that of obsschema_v1.cmd_eval (error under the mapping divided by error under the true mapping, per call), reading and writing ~/work/outputs/obsschema_rt_v1.
Commands: groups (build groups and evidence, kept if they exist), eval TRANSFORMS.json TAG. Needs the challenge calls; its eval output is the eval_*.json read by the offline rescoring.
"""
import glob, json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsschema_v1 as S  # noqa: E402
import obsschema_rt_v1
R = S.R
OUT = os.path.expanduser("~/work/outputs/obsschema_rt_v1"); NEW = ["test_g", "test_h", "test_i", "test_j", "rt_getstats"]; PH = "test_rt"


def cmd_groups():
    if os.path.exists(f"{OUT}/groups.json"): print("groups.json exists; reusing it"); return
    os.makedirs(OUT, exist_ok=True)
    used = set(json.load(open(os.path.expanduser("~/work/outputs/obsrepair_v1/sens.json")))["calls"])
    for g in json.load(open(f"{S.OUT}/groups.json"))["groups"]: used |= set(g["ev"]) | set(g["test"])
    groups = []
    for di, d in enumerate(R.DIRS):
        files = [f for f in sorted(glob.glob(f"{R.SCEN}/{d}/*.json")) if f not in used]; sets = []
        for k in range(2):
            sel = [str(x) for x in np.random.default_rng(20261702 + 100 * di + k).choice(files, 13, replace=False)]; files = [f for f in files if f not in sel]; sets.append(sel)
        for s in NEW:
            for dr in range(2): groups.append({"id": len(groups), "phase": PH, "scen": d, "schema": s, "draw": dr, "ev": sets[dr][:3], "test": sets[dr][3:]})
    ref = json.load(open(os.path.expanduser("~/work/outputs/obsrepair_v1/evidence.json")))["ref"]; ev = {}
    for g in groups:
        perm = S.order(g["schema"]); ev[str(g["id"])] = {"names": [S.SCHEMAS[g["schema"]][k][0] for k in perm], "stats": S.fstats([S.to_foreign(R.load(p)[0], g["schema"]) for p in g["ev"]])}
    allc = [c for g in groups for c in g["ev"] + g["test"]]
    assert not (set(allc) & used), "new calls overlap calls already used"
    json.dump({"groups": groups, "excluded_calls": len(used)}, open(f"{OUT}/groups.json", "w")); json.dump({"ref": ref, "groups": ev}, open(f"{OUT}/evidence.json", "w"))
    print("groups", len(groups), "calls excluded as already used", len(used), "new calls", len(set(allc)))


def cmd_eval(tpath, tag):
    G = json.load(open(f"{OUT}/groups.json")); E = json.load(open(f"{OUT}/evidence.json")); T = json.load(open(tpath)); ref = E["ref"]; jobs = []
    for g in G["groups"]:
        e = E["groups"][str(g["id"])]
        maps = {"ORACLE": S.oracle(g["schema"]), "DIST": S.dist_match(e["stats"], ref), "NAME": S.name_match(e["names"], e["stats"], ref)}
        for k, v in T.get(str(g["id"]), {}).items(): maps[k] = v
        jobs.append((g, maps))
    with ProcessPoolExecutor(40) as ex: rs = dict(ex.map(S.eval_job, jobs))
    json.dump({"results": {str(k): v for k, v in rs.items()}, "maps": {str(g["id"]): m for g, m in jobs}}, open(f"{OUT}/eval_{tag}.json", "w")); print("evaluated groups:", len(rs))


if __name__ == "__main__":
    {"groups": lambda: cmd_groups(), "eval": lambda: cmd_eval(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
