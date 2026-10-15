#!/usr/bin/env python3
"""Rebuild the 870 offline validation calls from the public emulated dataset of the MMSys 2024 challenge.

Every validation call is a file of the public emulated dataset (9405 calls, unpacked from emulated_dataset_chunk_0-2.zip),
copied unchanged into one of four scenario directories, as the conference version's scripts
validation/prepare_scenario/generate_high_low_bw_call.py and generate_fluctuating_bw_call.py did with its evaluation
split: high_bw_call (77 calls), low_bw_call (469), high_fluctuating_bw (76) and low_fluctuating_bw (248). The list of
<scenario directory>/<file name> is read from the per-step export experiments/results/arb_perstep_dump_v1/perstep.npz
(field keys), or, if that file is absent, from a per-call evaluation file (field files[].file).

With --check, each copied call is compared with the per-step export: the number of steps, the ground-truth capacity
and the short-window value of the 15 features must match. The resulting directory is the --scen argument of
scripts/alphartc/deploy/nl_estimator_v1/src/eval_value_per_file.py.

Usage: python3 scripts/arb/make_validation_scenarios_v1.py --emulated DIR --out DIR [--link] [--check] [--skip-missing]
  --emulated      directory holding the unpacked public files (NNNNN.json)
  --out           output root; the four scenario directories are created below it
  --link          create symbolic links instead of copies
  --skip-missing  build the calls that are present and report the rest (for a partial download)
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
NPZ = ROOT / "experiments/results/arb_perstep_dump_v1/perstep.npz"
PER_CALL = ROOT / "experiments/results/nl_2x2_v1/eval/CHs1.json"
COUNTS = {"high_bw_call": 77, "low_bw_call": 469, "high_fluctuating_bw": 76, "low_fluctuating_bw": 248}


def call_list():
    if NPZ.exists():
        z = np.load(NPZ, allow_pickle=True)
        return [str(k) for k in z["keys"]], z
    rows = json.loads(PER_CALL.read_text(encoding="utf-8"))["files"]
    return [r["file"] for r in rows], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emulated", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--skip-missing", action="store_true")
    a = ap.parse_args()
    src, out = Path(a.emulated), Path(a.out)
    keys, z = call_list()
    assert len(keys) == 870 and {d: sum(k.split("/")[0] == d for k in keys) for d in COUNTS} == COUNTS
    if a.check and z is None:
        raise SystemExit("--check needs experiments/results/arb_perstep_dump_v1/perstep.npz")
    missing, bad, done = [], [], 0
    for i, key in enumerate(keys):
        d, name = key.split("/")
        f = src / name
        if not f.is_file():
            missing.append(key)
            continue
        dst = out / d / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        if a.link:
            os.symlink(f.resolve(), dst)
        else:
            shutil.copyfile(f, dst)
        done += 1
        if a.check:
            c = json.loads(f.read_text(encoding="utf-8"))
            lo, hi = int(z["offsets"][i]), int(z["offsets"][i + 1])
            truth = np.asarray(c["true_capacity"], np.float32) / 1e6
            obs = np.asarray(c["observations"], np.float32)
            ok = len(truth) == hi - lo and np.allclose(truth, z["truth_mbps"][lo:hi], equal_nan=True) \
                and np.allclose(obs[:, np.arange(15) * 10], z["feat_short"][lo:hi], equal_nan=True)
            if not ok:
                bad.append(key)
    print(f"{done} of 870 calls written to {out}" + (f"; {len(missing)} not found in {src}" if missing else ""))
    if a.check:
        print("all written calls match the per-step export" if not bad else f"{len(bad)} calls differ: {bad[:5]}")
    if bad or (missing and not a.skip_missing):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
