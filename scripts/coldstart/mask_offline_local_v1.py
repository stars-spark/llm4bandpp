#!/usr/bin/env python3
"""Recompute realtel-mask-offline-v2 from the mask runs saved in this package.

scripts/realtel_e2e/mask_offline_v1.py --v2 first copies the mask runs from the GPU server and then summarises them.
This script runs the same summary on the local copies, experiments/results/realtel_mask_offline_v2/M*.json: each run
holds the per-call MSE of the deployed estimator (seed 1, 870 validation calls) when only the features a stack exposes
as single fields are kept and the others are filled with their training medians. The macro MSE weights the three
scenarios equally; the control Mall keeps features 0 to 11 and must reproduce the unmasked 5.795. Each stack keeps
the features labelled same in the realtel-scale-v1 ground truth. The result is compared with the recorded
summary.json, value by value and byte by byte; the exit status is 1 on any difference.

The runs themselves need the challenge validation calls and the deployed checkpoint and are not repeated here.

Usage: python3 scripts/coldstart/mask_offline_local_v1.py [--out PATH]   (--out also writes the recomputed summary)
"""
import hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts/realtel_e2e"))
import mask_offline_v1 as MO  # noqa: E402  same macro() and reference value as the registered summary
OUT = ROOT / "experiments/results/realtel_mask_offline_v2"


def summary():
    S = json.load(open(ROOT / "experiments/results/realtel_scale_v1/sources.json"))
    keep = {n: [k for k, t in enumerate(s["truth"]) if t[0] == "same"] for n, s in S.items()}
    tag = lambda ks: "M" + ("_".join(map(str, ks)) if ks else "none")
    M = {}
    for f in sorted(OUT.glob("M*.json")):
        d = json.load(open(f)); rows = d.get("files", d.get("rows")); assert len(rows) == 870, (f, len(rows)); M[f.stem] = MO.macro(rows)
    ok = abs(M["Mall"][0] - MO.REF) / MO.REF < 1e-4
    per_stack = {n: {"keep": ks, "macro": M[tag(ks)][0], "by_scen": M[tag(ks)][1]} for n, ks in keep.items()}
    return {"control_Mall": {"macro": M["Mall"][0], "ref": MO.REF, "pass": ok}, "masks": {k: {"macro": v[0], "by_scen": v[1]} for k, v in M.items()}, "per_stack": per_stack}


def check_hashes():
    """sha256sums.txt was written on the server next to the runs; the released copies have machine paths replaced, so a difference there is expected."""
    want = {}
    for ln in (OUT / "sha256sums.txt").read_text().splitlines():
        h, name = ln.split(None, 1)
        if name.startswith("out_mask2/"): want[name.split("/", 1)[1]] = h
    same = {n: hashlib.sha256((OUT / n).read_bytes()).hexdigest() == h for n, h in want.items() if (OUT / n).is_file()}
    print(f"run files identical to the server copies: {sum(same.values())} of {len(want)}" + ("" if all(same.values()) else " (paths inside the files were replaced in the public package)"))


def main():
    res = summary(); rec_text = (OUT / "summary.json").read_text(encoding="utf-8"); rec = json.loads(rec_text)
    same_value = res == rec; same_bytes = json.dumps(res, ensure_ascii=False, indent=1) == rec_text
    r2 = lambda x: round(x, 2)
    print(f"control Mall {res['control_Mall']['macro']:.4f} against unmasked {MO.REF:.4f}: {'reproduced' if res['control_Mall']['pass'] else 'NOT reproduced'}")
    for n, v in res["per_stack"].items(): print(f"  {n}: keeps features {v['keep']}, macro MSE {r2(v['macro'])}")
    lo, hi = min(v["macro"] for v in res["per_stack"].values()), max(v["macro"] for v in res["per_stack"].values())
    print(f"macro MSE over the 12 stacks: {lo:.2f} to {hi:.2f} (unmasked {MO.REF:.2f})")
    check_hashes()
    print(f"recorded summary.json: values {'equal' if same_value else 'DIFFER'}, bytes {'equal' if same_bytes else 'DIFFER'}")
    if "--out" in sys.argv: Path(sys.argv[sys.argv.index("--out") + 1]).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(0 if same_value and same_bytes and res["control_Mall"]["pass"] else 1)


if __name__ == "__main__":
    main()
