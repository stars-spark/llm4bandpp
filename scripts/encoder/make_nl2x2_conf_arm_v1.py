#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Encoder by reward ablation on the recipe without an LLM (ablation-nl-enc-hcq-2x2-v1): write the estimator.py of the two
conference-encoder cells (C-B, C-H); the output is scripts/encoder/nl2x2_v1/estimator_conf.py. The two M cells use the
multi-scale training directory unchanged (scripts/alphartc/deploy/nl_estimator_v1/src/). The C cells change only the
class bwe_agent: the encoder becomes the conference StateEncoder (Linear(150, 1024), LayerNorm, LeakyReLU, one vector)
feeding the same BweHead, with no LLM. We avoid the split-and-sum fifteen-token form, whose last token would carry only
the fifteenth feature. encoder0, log_std, the head and the output units stay as they are; the launcher copies the other
four files (IQL.py, module.py, model.py, dualEncoder.py) and checks their hashes.
Usage: python3 make_nl2x2_conf_arm_v1.py SOURCE_estimator.py OUTPUT_estimator.py
"""
import hashlib, re, sys
from pathlib import Path

WANT = "62d0e5582fb3617d"


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    s = src.read_text(); assert hashlib.sha256(src.read_bytes()).hexdigest().startswith(WANT), "Source estimator.py hash mismatch"
    i = s.index("class bwe_agent(nn.Module):"); k = s.index("\n", i) + 1; j = k + re.search(r"^\S", s[k:], re.M).start()
    body = s[i:j]
    old_enc = "        self.stateencoder = StateEncoderDualScaleLSTM(self.state_dim, 1024, self.device)\n"
    old_fwd = ("        x = self.stateencoder(x)   # [batch, 15, 1024], identical to MultiToken\n"
               "        # Remove only Qwen; use the same last-token readout and BWE head.\n"
               "        x = x[:, -1, :]                     # [batch, 1024]\n")
    assert body.count(old_enc) == 1 and body.count(old_fwd) == 1, "The structure of the deployed estimator bwe_agent does not match expectations"
    new = body.replace(old_enc, "        # NL2X2_CONF_ENCODER_V1: conference version encoder, outputs a 1024-dimensional vector, connects directly to the head without going through the LLM\n        self.stateencoder = StateEncoder(self.state_dim, 1024, self.device)\n")
    new = new.replace(old_fwd, "        x = self.stateencoder(x)   # [batch, 1024]\n")
    t = s[:i] + new + s[j:]
    assert t.count("NL2X2_CONF_ENCODER_V1") == 1 and "StateEncoder(self.state_dim, 1024, self.device)" in t
    out.write_text(t); print("Written", out, hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
