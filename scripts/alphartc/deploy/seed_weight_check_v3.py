#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weight check of lowbw-lambda-ch-v1 and lowbw-lambda-ch-v2 (lowbw_lambda_ch_v1.py and _v2.py, run script v26): candidates ch.pt (l04), ch_l10s1.pt (l10) and ch_l00s1.pt (l00); job names look like c100__l10__r1,
with the arm key in the second field.
Copy of v2 with these candidates and job names; same rule as v2 (smallest error below 1e-3 and at least ten times below the second smallest).
Usage: python3 seed_weight_check_v3.py K_DIR [--max-steps 60] (needs torch); output K/seed_weight_check.json.
"""
import glob, gzip, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "ch_estimator_v1"))
import torch  # noqa: E402
import spec_collector_v6 as C6  # noqa: E402
from ch_estimator_v1 import load_agent  # noqa: E402
CK = {"l04": HERE / "ch_estimator_v1/ckpt/ch.pt", "l10": HERE / "ch_estimator_v1/ckpt/ch_l10s1.pt", "l00": HERE / "ch_estimator_v1/ckpt/ch_l00s1.pt"}


def rows(d):
    fs = glob.glob(str(d / "obs_arm_ch_x*.jsonl*")) + glob.glob(str(d / "invalid_*obs_arm_ch_x*.jsonl*"))
    if not fs: return []
    with (gzip.open(fs[0], "rt") if fs[0].endswith(".gz") else open(fs[0])) as f:
        return [o for o in map(json.loads, f) if "model_raw_bps" in o and "obs" in o]


def main():
    K = Path(sys.argv[1]); n = int(sys.argv[sys.argv.index("--max-steps") + 1]) if "--max-steps" in sys.argv else 60
    M = {k: load_agent(str(p), "cpu").eval() for k, p in CK.items()}; out = {}; bad = []
    for d in sorted((K / "main").iterdir()):
        if not d.is_dir() or "__gcc200__" in d.name: continue
        O = rows(d)[:n]
        if not O: out[d.name] = {"verdict": "no observations"}; continue
        x = torch.tensor([C6.add_audio(list(o["obs"])) for o in O], dtype=torch.float32); rec = torch.tensor([float(o["model_raw_bps"]) for o in O])
        err = {}
        with torch.inference_mode():
            for k, m in M.items():
                y = m(x)[0].reshape(-1); err[k] = float(((y - rec).abs() / rec.abs().clamp(min=1.0)).max())
        srt = sorted(err, key=err.get); hit = [srt[0]] if err[srt[0]] < 1e-3 and err[srt[1]] >= 10 * max(err[srt[0]], 1e-12) else []; want = d.name.split("__")[1]
        v = hit[0] if len(hit) == 1 else "inconclusive"; out[d.name] = {"verdict": v, "want": want, "max_rel_err": err, "n_steps": len(O)}
        if v != want: bad.append(d.name)
    res = {"runs": out, "mismatch": bad, "n_checked": len(out)}; (K / "seed_weight_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps({"n_checked": len(out), "mismatch": bad}, ensure_ascii=False)); sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
