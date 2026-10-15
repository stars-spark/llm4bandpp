#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate ch_estimator_v1.py, the testbed module of the deployed estimator (cell C-H of ablation-nl-enc-hcq-2x2-v1).
C-H: conference encoder (Linear(150,1024), LayerNorm, LeakyReLU) feeding the bandwidth head directly, HCQ reward with λ 0.4,
otherwise the no-LLM training recipe with the capacity anchor.
StateEncoder and BweHead are copied verbatim from ../nl_estimator_v1/src/module.py (sha256 prefix 645ddc46); bwe_agent and the LOG_STD
constants from scripts/encoder/nl2x2_v1/estimator_conf.py (sha256 prefix f78405de). Only the transformers and peft imports are left out;
both source hashes are asserted first and no forward code is changed.
Usage: python3 build_ch_estimator_v1.py  (writes ch_estimator_v1.py and prints its sha256)
"""
import hashlib, re
from pathlib import Path

H = Path(__file__).resolve().parent; ROOT = H.parents[3]
MOD = H.parent / "nl_estimator_v1/src/module.py"; EST = ROOT / "scripts/encoder/nl2x2_v1/estimator_conf.py"
OUT = H / "ch_estimator_v1.py"
WANT = {MOD: "645ddc461220e508", EST: "f78405de1d20dc68"}


# Source text of class `name`, from its header to the next line that starts in column 0.
def cls(src, name):
    i = src.index(f"class {name}("); k = src.index("\n", i) + 1
    m = re.search(r"^\S", src[k:], re.M)
    return src[i: k + m.start()].rstrip() + "\n" if m else src[i:].rstrip() + "\n"


def main():
    for f, h in WANT.items():
        got = hashlib.sha256(f.read_bytes()).hexdigest()
        assert got.startswith(h), (f, got)
    mod = MOD.read_text(); est = EST.read_text()
    parts = [cls(mod, n) for n in ("StateEncoder", "BweHead")]
    agent = cls(est, "bwe_agent")
    assert "StateEncoder(self.state_dim, 1024" in agent and "self.llm" not in agent and "x[:, -1, :]" not in agent
    consts = re.search(r"^LOG_STD_MIN = .*\nLOG_STD_MAX = .*\n", est, re.M).group(0)
    head = ('# -*- coding: utf-8 -*-\n"""C-H estimator (conference version encoder plus HCQ, no LLM, 2026-10-04 exploratory smoke test). Generated verbatim by build_ch_estimator_v1.py from the training code, do not edit by hand.\nSource: module.py sha256 prefix 645ddc46, estimator_conf.py prefix f78405de (the two C cells of ablation-nl-enc-hcq-2x2-v1).\nInput: the 150-dimensional observation given by the collector (15 features times 10 monitoring intervals); output: bandwidth estimate, unit bit/s, taking the policy mean."""\nimport math\nimport torch\nimport torch.nn as nn\n\n' + consts + "\n\n")
    agent = agent.replace("        self.encoder0 = nn.Parameter(", "        # ANTIPATTERN-OK: extracted verbatim by build_ch_estimator_v1.py from the training code estimator_conf.py, must be bit-identical to training (generator exemption)\n        self.encoder0 = nn.Parameter(", 1)
    assert "ANTIPATTERN-OK" in agent
    body = "\n\n".join(parts + [agent])
    tail = ('\n\ndef load_agent(path, device="cpu"):\n    """Build the model and load it strictly in the manner of the evaluation script eval_value_per_file.py: bwe_agent(20, 150, 1, device), load_state_dict(strict=True), eval()."""\n    model = bwe_agent(20, 150, 1, torch.device(device))\n    try: state = torch.load(path, map_location="cpu", weights_only=True)\n    except TypeError: state = torch.load(path, map_location="cpu")\n    model.load_state_dict(state, strict=True); model.eval(); return model\n')
    OUT.write_text(head + body + tail)
    print("Written", OUT, hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
