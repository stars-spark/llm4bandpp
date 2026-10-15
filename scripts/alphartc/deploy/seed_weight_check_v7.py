#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weight check of lowbw-loss1-env6-v1 and content320-ch-gcc-v1 (run script v29; the second gives the 320x240 rows of Table V).
Copy of v6 with two more candidate sets, deployed_ch6 and deployed_dep (ch.pt plus the seed-0 checkpoint as a decoy that no run should match), and --sub to name
the sub-batch directory (default main); same rule as v6.
Usage: python3 seed_weight_check_v7.py K_DIR [--set SET] [--sub main] [--max-steps 60] (needs torch); output K/seed_weight_check_<sub>.json.
"""
import glob, gzip, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "ch_estimator_v1"))
import torch  # noqa: E402
import spec_collector_v6 as C6  # noqa: E402
from ch_estimator_v1 import load_agent  # noqa: E402
_C = HERE / "ch_estimator_v1/ckpt"
SETS = {"seeds": {"l04s0": _C / "ch_s0.pt", "l04s2": _C / "ch_s2.pt", "l00s0": _C / "ch_l00s0.pt", "l00s2": _C / "ch_l00s2.pt", "l10s0": _C / "ch_l10s0.pt", "l10s2": _C / "ch_l10s2.pt"},
        "noanchor": {"ch0": _C / "ch.pt", "a0": _C / "ch_a0s2.pt"},
        "deployed_ch6": {"ch6": _C / "ch.pt", "decoy_s0": _C / "ch_s0.pt"},
        "deployed_dep": {"dep": _C / "ch.pt", "decoy_s0": _C / "ch_s0.pt"}}
CK = SETS[sys.argv[sys.argv.index("--set") + 1]] if "--set" in sys.argv else SETS["seeds"]


def rows(d):
    fs = glob.glob(str(d / "obs_arm_ch_x*.jsonl*")) + glob.glob(str(d / "invalid_*obs_arm_ch_x*.jsonl*"))
    if not fs: return []
    with (gzip.open(fs[0], "rt") if fs[0].endswith(".gz") else open(fs[0])) as f:
        return [o for o in map(json.loads, f) if "model_raw_bps" in o and "obs" in o]


def main():
    K = Path(sys.argv[1]); n = int(sys.argv[sys.argv.index("--max-steps") + 1]) if "--max-steps" in sys.argv else 60
    M = {k: load_agent(str(p), "cpu").eval() for k, p in CK.items()}; out = {}; bad = []
    sub = sys.argv[sys.argv.index("--sub") + 1] if "--sub" in sys.argv else "main"
    for d in sorted((K / sub).iterdir()):
        if not d.is_dir() or "__gcc200__" in d.name or d.name.split("__")[1] not in CK: continue
        O = rows(d)[:n]
        if not O: out[d.name] = {"verdict": "no observations"}; continue
        x = torch.tensor([C6.add_audio(list(o["obs"])) for o in O], dtype=torch.float32); rec = torch.tensor([float(o["model_raw_bps"]) for o in O])
        err = {}
        with torch.inference_mode():
            for k, m in M.items():
                y = m(x)[0].reshape(-1); err[k] = float(((y - rec).abs() / rec.abs().clamp(min=1.0)).max())
        srt = sorted(err, key=err.get); hit = [srt[0]] if err[srt[1]] >= 10 * max(err[srt[0]], 1e-12) else []; want = d.name.split("__")[1]
        v = hit[0] if len(hit) == 1 else "inconclusive"; out[d.name] = {"verdict": v, "want": want, "max_rel_err": err, "n_steps": len(O)}
        if v != want: bad.append(d.name)
    res = {"runs": out, "mismatch": bad, "n_checked": len(out)}; (K / f"seed_weight_check_{sub}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps({"n_checked": len(out), "mismatch": bad}, ensure_ascii=False)); sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
