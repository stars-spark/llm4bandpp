#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the public cellular-trace corpus from which the UCC 4G, Norwegian 3G and Chorus windows are cut: normalization and context labels only.

Blinding (registry entry llm-kp-public-trace-corpus-stage-v1): this script computes no loss, safety-factor curve,
per-context optimum or variability statistic; it reports only counts, lengths and label counts.
The raw traces are not redistributed. Download them from their sources (UCC 4G: Zenodo 10.5281/zenodo.1219679; Norwegian
3G/HSDPA: the MMSys 2013 dataset page; Chorus: GreenLv/Chorus at commit 8e1e26bc) into RAW, then run this script. main()
also reads a Starlink road-test iperf file (RAW/starlink_road/data/iperf.csv) that no network profile uses; without it,
drop the starlink() call: the other traces come out the same, only the corpus file hash differs.
"""
import csv
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

RAW = Path("/path/to/server/datasets/llm_kp/raw")
CHORUS = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW / "chorus"
OUT = Path("/path/to/server/datasets/llm_kp/corpus_v1")
MIN_SECONDS = 60
GAP_S = 5.0


def emit(rows, tr):
    c = np.asarray(tr["capacity_mbps"], dtype=float)
    valid = np.isfinite(c)
    if valid.sum() < MIN_SECONDS:
        return False
    tr["capacity_mbps"] = [None if not np.isfinite(x) else round(float(x), 6) for x in c]
    tr["n_seconds"] = int(len(c))
    tr["n_valid_seconds"] = int(valid.sum())
    rows.append(tr)
    return True


def chorus(rows, drop):
    rx = re.compile(r"^(downlink|uplink)-(cellular|wifi)_([a-z]+?)(?:_(\d+))?$")
    for p in sorted(glob.glob(str(CHORUS / "bw_traces" / "*.csv"))):
        stem = Path(p).stem
        if stem == "all_trace_bw":
            continue
        d, tech, env, _ = rx.match(stem).groups()
        r = list(csv.DictReader(open(p)))
        bw = np.array([float(x["Bandwidth (Mbps)"]) for x in r])
        n = len(bw) // 5
        c = bw[:n * 5].reshape(n, 5).mean(axis=1)
        ok = emit(rows, {"trace_id": f"chorus/{stem}", "source": "chorus", "split_role": "train_only",
                         "direction": d, "technology": tech, "mobility_or_env": env,
                         "operator": None, "start_network_mode": None, "capacity_mbps": c.tolist()})
        drop["chorus"] += 0 if ok else 1


def ucc(rows, drop):
    for p in sorted(glob.glob(str(RAW / "ucc_4g/Dataset/*/*.csv"))):
        mob = Path(p).parent.name
        r = list(csv.DictReader(open(p)))
        cap, mode0 = [], None
        for x in r:
            if x["State"] != "D":
                cap.append(np.nan)
                continue
            try:
                cap.append(float(x["DL_bitrate"]) / 1000.0)
            except ValueError:
                cap.append(np.nan)
                continue
            if mode0 is None:
                mode0 = x["NetworkMode"]
        op = r[0]["Operatorname"] if r else None
        ok = emit(rows, {"trace_id": f"ucc_4g/{mob}/{Path(p).stem}", "source": "ucc_4g", "split_role": "eval_pool",
                         "direction": "downlink", "technology": "cellular", "mobility_or_env": mob,
                         "operator": op, "start_network_mode": mode0, "capacity_mbps": cap})
        drop["ucc_4g"] += 0 if ok else 1


def norway(rows, drop):
    for p in sorted(glob.glob(str(RAW / "norway_hsdpa/*/*"))):
        if Path(p).name.startswith("index.html"):
            continue
        route = Path(p).parent.name
        mode = route.split(".")[0]
        cap = []
        for line in open(p):
            f = line.split()
            if len(f) < 6:
                continue
            nbytes, period_ms = float(f[4]), float(f[5])
            cap.append(nbytes * 8 / (period_ms / 1000.0) / 1e6 if period_ms > 0 else np.nan)
        ok = emit(rows, {"trace_id": f"norway_hsdpa/{route}/{Path(p).name}", "source": "norway_hsdpa",
                         "split_role": "eval_pool", "direction": "downlink", "technology": "cellular_3g_hsdpa",
                         "mobility_or_env": mode, "operator": "telenor", "start_network_mode": "HSDPA",
                         "capacity_mbps": cap})
        drop["norway_hsdpa"] += 0 if ok else 1


def starlink(rows, drop):
    r = list(csv.DictReader(open(RAW / "starlink_road/data/iperf.csv")))
    fmt = "%Y-%m-%d %H:%M:%S"
    r.sort(key=lambda x: x["timestamp_start"])
    sessions, cur, prev = [], [], None
    for x in r:
        t = datetime.strptime(x["timestamp_start"], fmt)
        if prev is not None and (t - prev).total_seconds() > GAP_S:
            sessions.append(cur); cur = []
        cur.append(x); prev = t
    if cur:
        sessions.append(cur)
    for i, s in enumerate(sessions):
        spd0 = float(s[0]["average_speed"] or 0)
        mob = "static" if spd0 == 0 else "driving"
        for d, col in (("downlink", "download_mbps"), ("uplink", "upload_mbps")):
            cap = [float(x[col]) if x[col] not in ("", None) else np.nan for x in s]
            ok = emit(rows, {"trace_id": f"starlink_road/s{i:03d}/{d}", "source": "starlink_road",
                             "split_role": "eval_pool", "direction": d, "technology": "leo_satellite",
                             "mobility_or_env": mob, "operator": "starlink", "start_network_mode": None,
                             "capacity_mbps": cap})
            drop["starlink_road"] += 0 if ok else 1


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, drop = [], Counter()
    chorus(rows, drop); ucc(rows, drop); norway(rows, drop); starlink(rows, drop)
    with (OUT / "corpus.jsonl").open("w", encoding="utf-8") as fh:
        for tr in rows:
            fh.write(json.dumps(tr, ensure_ascii=False) + "\n")
    h = hashlib.sha256((OUT / "corpus.jsonl").read_bytes()).hexdigest()
    ctx = Counter((t["source"], t["technology"], t["mobility_or_env"], t["direction"]) for t in rows)
    manifest = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "blinding": "No losses, safety factor curves, per-context optima, or fluctuation statistics were computed",
        "min_valid_seconds": MIN_SECONDS, "starlink_gap_s": GAP_S,
        "n_traces": len(rows), "dropped_short": dict(drop), "corpus_sha256": h,
        "by_source": dict(Counter(t["source"] for t in rows)),
        "by_context": [{"source": s, "technology": te, "mobility_or_env": m, "direction": d, "n": n}
                       for (s, te, m, d), n in sorted(ctx.items())],
        "start_network_mode_ucc": dict(Counter(t["start_network_mode"] for t in rows if t["source"] == "ucc_4g")),
        "length_seconds": {s: {"min": min(t["n_seconds"] for t in rows if t["source"] == s),
                               "median": int(np.median([t["n_seconds"] for t in rows if t["source"] == s])),
                               "max": max(t["n_seconds"] for t in rows if t["source"] == s)}
                           for s in sorted({t["source"] for t in rows})},
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "by_context"}, indent=2, ensure_ascii=False))
    print("\nContext counts (source technique mobility or environment direction count)")
    for e in manifest["by_context"]:
        print(f"  {e['source']:14s} {e['technology']:18s} {e['mobility_or_env']:16s} {e['direction']:8s} {e['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
