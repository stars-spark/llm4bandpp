#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arm generator of aggregator-mamba-control-v1 (ran on the GPU server). Replaces the two-layer cross-feature Transformer
aggregator of the encoder by two Mamba-style selective state-space blocks and leaves everything else unchanged. The
shared environment had no mamba-ssm package, so the selective scan is plain PyTorch; with 15 tokens a step-by-step scan
costs little. Two arms: MB, the arm without the LLM (main criterion, three seeds), and MBL, the arm with the LLM (report
only, one seed). Files are copied from a fixed list; the source directories are only read.
"""
import hashlib, shutil, subprocess, sys
from pathlib import Path
SRC = {"MB": Path("/path/to/server/work/caiql_llm_screen_v2r1/nollm_mt_anchor"), "MBL": Path("/path/to/server/work/rcaiql_screen_v1/mt_anchor")}
DST = Path("/path/to/server/work/mamba_aggregator"); FILES = ("IQL.py", "estimator.py", "module.py", "model.py", "dualEncoder.py")
MAMBA_CLASS = '''
# MAMBA_AGGREGATOR_V1: pure PyTorch of Mamba selective state space block (S6), used to replace cross-feature Transformer Aggregator.
class _MambaBlock(nn.Module):
    def __init__(self, d_model, d_state=8, d_conv=4, expand=2):
        super().__init__()
        self.d_inner = expand * d_model; self.d_state = d_state; self.dt_rank = max(1, d_model // 8)
        self.norm = nn.LayerNorm(d_model); self.in_proj = nn.Linear(d_model, 2 * self.d_inner, bias=False)
        self.conv1d = nn.Conv1d(self.d_inner, self.d_inner, d_conv, groups=self.d_inner, padding=d_conv - 1)
        self.x_proj = nn.Linear(self.d_inner, self.dt_rank + 2 * d_state, bias=False); self.dt_proj = nn.Linear(self.dt_rank, self.d_inner)
        self.A_log = nn.Parameter(torch.log(torch.arange(1, d_state + 1, dtype=torch.float32)).repeat(self.d_inner, 1))
        # Initial step size according to Mamba The original approach takes 0.001 to 0.1 log-uniform distribution (via softplus inverse function written into the bias); otherwise the decay is too fast and the information of the first token cannot reach the last token
        _dt = torch.exp(torch.rand(self.d_inner) * (math.log(0.1) - math.log(0.001)) + math.log(0.001)).clamp(min=1e-4)
        with torch.no_grad(): self.dt_proj.bias.copy_(_dt + torch.log(-torch.expm1(-_dt)))
        self.D = nn.Parameter(torch.ones(self.d_inner)); self.out_proj = nn.Linear(self.d_inner, d_model, bias=False); self.drop = nn.Dropout(0.1)

    def forward(self, x):                                  # [B, L, d_model]
        res = x; x = self.norm(x); B_, L, _ = x.shape
        xz = self.in_proj(x); u, z = xz.chunk(2, dim=-1)
        u = self.conv1d(u.transpose(1, 2))[..., :L].transpose(1, 2); u = torch.nn.functional.silu(u)
        dbc = self.x_proj(u); dt, Bm, Cm = torch.split(dbc, [self.dt_rank, self.d_state, self.d_state], dim=-1)
        dt = torch.nn.functional.softplus(self.dt_proj(dt)); A = -torch.exp(self.A_log)                 # [d_inner, d_state]
        h = torch.zeros(B_, self.d_inner, self.d_state, device=x.device, dtype=x.dtype); ys = []
        for t in range(L):                                 # selective scan: discretised, causal, one step at a time
            dA = torch.exp(dt[:, t].unsqueeze(-1) * A); dB = dt[:, t].unsqueeze(-1) * Bm[:, t].unsqueeze(1)
            h = dA * h + dB * u[:, t].unsqueeze(-1); ys.append((h * Cm[:, t].unsqueeze(1)).sum(-1) + self.D * u[:, t])
        y = torch.stack(ys, dim=1) * torch.nn.functional.silu(z)
        return res + self.drop(self.out_proj(y))


class _MambaStack(nn.Module):
    def __init__(self, d_model, num_layers=2):
        super().__init__(); self.layers = nn.ModuleList([_MambaBlock(d_model) for _ in range(num_layers)])

    def forward(self, x):
        for l in self.layers: x = l(x)
        return x

'''
PATCH = """        # MAMBA_AGGREGATOR_V1: replace the two-layer Transformer aggregator with two-layer Mamba-style blocks, forward unchanged.
        self.transformer_layer = nn.Identity()
        self.transformer_encoder = _MambaStack(self.feature_embedding_dim, num_layers=2).to(device)"""
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if DST.exists(): shutil.rmtree(DST)
for arm, src in SRC.items():
    d = DST / arm; d.mkdir(parents=True); total = 0
    for f in FILES:
        assert (src / f).is_file(), f"{src/f} does not exist"; total += (src / f).stat().st_size; assert total < 5 * 1024 * 1024, "files to copy exceed 5 MiB"
        shutil.copy2(src / f, d / f); (d / f).chmod((d / f).stat().st_mode | 0o200)
    p = d / "module.py"; s = p.read_text()
    i0 = s.find("self.transformer_layer = nn.TransformerEncoderLayer("); assert i0 != -1, f"{arm} cannot find the aggregator layer anchor"
    i1 = s.index(")", s.index("num_layers=2", i0)); i1 = s.index("\n", i1)
    start = s.rindex("\n", 0, i0) + 1; block = s[start:i1]
    assert block.count("nn.TransformerEncoder") == 2, block
    s = s.replace(block, PATCH, 1); k = s.index("class StateEncoderDualScaleLSTM"); s = s[:k] + MAMBA_CLASS.lstrip("\n") + "\n" + s[k:]
    assert "nn.TransformerEncoder(" not in s.split("class StateEncoderDualScaleLSTM")[1].split("def _create_positional_encoding")[0], f"{arm} aggregator not fully replaced"
    p.write_text(s)
    for f in ("estimator.py", "module.py", "IQL.py"):
        r = subprocess.run([sys.executable, "-m", "py_compile", str(d / f)], capture_output=True, text=True); assert r.returncode == 0, r.stderr[-300:]
    for f in FILES:
        if f != "module.py": assert sha(d / f) == sha(src / f), f"{arm}/{f} should have no changes"
print("Both arms have been generated:", DST); [print(f"  {a}/module.py {sha(DST / a / 'module.py')[:16]}") for a in SRC]
