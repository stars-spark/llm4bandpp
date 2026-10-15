#!/usr/bin/env python3
"""Minimal stand-in for the experiment registry tool used by the judge scripts.

The judges call `exp.py data|conclude|note|explore|disagree --id ID --key value ...`. This stub appends each call as
one JSON line to experiments/registry_local.jsonl so a judge can be rerun without the full registry. The registered
experiments themselves are summarised in registry/registry_summary.md.
"""
import json, sys, time
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "experiments/registry_local.jsonl"


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    ev = {"event": sys.argv[1], "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    args = sys.argv[2:]; i = 0
    while i < len(args):
        if args[i].startswith("--"):
            k = args[i][2:].replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"): ev[k] = args[i + 1]; i += 2
            else: ev[k] = True; i += 1
        else: i += 1
    with open(LOG, "a", encoding="utf-8") as f: f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"{ev['event']} {ev.get('id', '')} -> {LOG.name}")


if __name__ == "__main__":
    main()
