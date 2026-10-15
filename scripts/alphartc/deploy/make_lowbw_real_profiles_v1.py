#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build 12 low-bandwidth real-trace comcast profiles from the public trace corpus corpus_v1 (rule lowbw_real_v1).

Reads only data/llm_kp/corpus_v1.jsonl and writes only scripts/alphartc/deploy/profiles/lowbw_real/.
Does not run the testbed or change any existing file. The selection rule, fixed before the profiles were built, is
SELECTION_RULE below; it is also written to provenance.json.
Usage: python3 scripts/alphartc/deploy/make_lowbw_real_profiles_v1.py
"""
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
CORPUS = REPO / "data" / "llm_kp" / "corpus_v1.jsonl"
OUT = HERE.parent / "profiles" / "lowbw_real"
SEED, WIN, DELAY, LOSS = 20260909, 120, 50, 0
FLOOR, MAX_CLAMP, CAP_LINE = 30, 12, 600
SOURCES = ("ucc_4g", "chorus")
TIERS = (("T1", 0, 300), ("T2", 300, 600), ("T3", 600, 1000))
QUANTS = (1 / 8, 3 / 8, 5 / 8, 7 / 8)

SELECTION_RULE = """Rule version lowbw_real_v1, fixed seed 20260909.
(1) source. Use only traces in corpus_v1 whose source is ucc_4g and chorus; never use norway_hsdpa.
(2) window. Window length 120 seconds, one step per second. If any second in the window is missing (capacity_mbps is null), the whole window is void; no interpolation, no concatenation.
(3) statistical basis. Convert per-second capacity to kbit/s (Mbps times 1000), then compute on the unclipped original values the mean, minimum, coefficient of variation (population standard deviation divided by mean), and the fraction of seconds below 600 kbit/s. Stratification uses only the unclipped mean: tier one below 300, tier two 300 to 600 (including 300, excluding 600), tier three 600 to 1000 (including 600, excluding 1000).
(4) window slicing for candidate statistics. Each trace is sliced from second 0 on a non-overlapping 120-second grid, and a tail shorter than 120 seconds is discarded. This basis is used only for the candidate statistics table.
(5) candidate pool for selection. Under the grid basis tier one has fewer than 4 qualifying traces, so selection switches to a per-second sliding start (start takes every integer second from 0 to n_seconds minus 120), with all other conditions unchanged. Because a single trace yields at most 1 window, selected windows are naturally non-overlapping.
(6) qualifying condition. A second that rounds to an integer kbit/s below 30 is called a clipped second; a window with more than 12 clipped seconds (one tenth of the window) is not qualified, because that is a broken calls scenario rather than a low bandwidth scenario, and clipping noticeably changes the mean.
(7) representative window per trace. For each tier and each trace, sort all qualifying windows of that trace in that tier by start ascending, and draw 1 with choice using the same instance of random.Random(20260909); the traversal order is tier one to tier three, and within a tier trace_id in ascending lexicographic order.
(8) take 4 per tier. Process in the order tier one, tier two, tier three (the tier with the fewest candidates is selected first). For each tier first remove traces already selected by earlier tiers, sort the remaining representative windows by coefficient of variation ascending (ties by trace_id ascending), let the count be n, and take index floor(n times q), where q is one eighth, three eighths, five eighths, seven eighths in turn, that is one each from stable to volatile. When n is less than 4, take as many as the tier has and record it in the notes as incomplete.
(9) numbering. real_lowbw_01 to 04 are tier one, 05 to 08 are tier two, 09 to 12 are tier three, and within a tier in ascending coefficient of variation order.
(10) write out. rate takes the kbit/s value of that second rounded with Python built-in round (round half to even), values below 30 are clipped to 30, and the number of clipped seconds is written into the first-line comment; delay 50 and loss 0 each appear only once at the beginning, and each second has one line of rate plus one line of wait 1.
(11) no post hoc adjustment. After the selection result is out, do not change windows because of how specific traces look; if a change is needed, the rule version number must be raised and a separate directory started.
"""


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tier_of(mean):
    for name, lo, hi in TIERS:
        if lo <= mean < hi:
            return name
    return None


def window_stats(trace, start):
    w = trace["capacity_mbps"][start:start + WIN]
    if len(w) < WIN or any(v is None or not math.isfinite(v) for v in w):
        return None
    kb = [v * 1000.0 for v in w]
    mean = sum(kb) / WIN
    rates = [max(FLOOR, round(x)) for x in kb]
    return {
        "trace_id": trace["trace_id"], "source": trace["source"], "direction": trace["direction"],
        "technology": trace["technology"], "mobility_or_env": trace["mobility_or_env"],
        "split_role": trace["split_role"], "start_s": start, "end_s": start + WIN,
        "mean_kbps": mean, "min_kbps": min(kb),
        "cv": (statistics.pstdev(kb) / mean) if mean > 0 else float("nan"),
        "frac_below_600": sum(x < CAP_LINE for x in kb) / WIN,
        "n_clamped": sum(round(x) < FLOOR for x in kb),
        "mean_kbps_after_clamp": sum(rates) / WIN,
        "tier": tier_of(mean), "rates": rates,
    }


def tier_summary(wins):
    out = {}
    for name, _, _ in TIERS:
        x = [w for w in wins if w["tier"] == name]
        ok = [w for w in x if w["n_clamped"] <= MAX_CLAMP]
        out[name] = {
            "windows": len(x), "traces": len({w["trace_id"] for w in x}),
            "windows_by_source": dict(sorted(Counter(w["source"] for w in x).items())),
            "traces_by_source": dict(sorted(Counter(
                s for _, s in {(w["trace_id"], w["source"]) for w in x}).items())),
            "eligible_windows": len(ok), "eligible_traces": len({w["trace_id"] for w in ok}),
        }
    return out


def main():
    traces = [json.loads(l) for l in CORPUS.open()]
    traces = sorted((t for t in traces if t["source"] in SOURCES), key=lambda t: t["trace_id"])

    grid_total, grid_full, grid = Counter(), Counter(), []
    for t in traces:
        for k in range(t["n_seconds"] // WIN):
            grid_total[t["source"]] += 1
            s = window_stats(t, k * WIN)
            if s is None:
                continue
            grid_full[t["source"]] += 1
            grid.append(s)
    grid_low = [w for w in grid if w["tier"]]

    slide = defaultdict(lambda: defaultdict(list))  # tier -> trace_id -> windows
    slide_all = []
    for t in traces:
        for start in range(0, t["n_seconds"] - WIN + 1):
            s = window_stats(t, start)
            if s is None or s["tier"] is None:
                continue
            slide_all.append(s)
            if s["n_clamped"] <= MAX_CLAMP:
                slide[s["tier"]][t["trace_id"]].append(s)

    rng = random.Random(SEED)
    reps = {}
    for name, _, _ in TIERS:
        reps[name] = [rng.choice(sorted(slide[name][tid], key=lambda w: w["start_s"]))
                      for tid in sorted(slide[name])]

    used, chosen, shortfall = set(), [], {}
    for name, _, _ in TIERS:
        pool = sorted((w for w in reps[name] if w["trace_id"] not in used),
                      key=lambda w: (w["cv"], w["trace_id"]))
        n = len(pool)
        picks = [pool[math.floor(n * q)] for q in QUANTS] if n >= 4 else pool
        if n < 4:
            shortfall[name] = n
        for rank, w in zip([math.floor(n * q) for q in QUANTS] if n >= 4 else range(n), picks):
            w["cv_rank_in_tier_pool"], w["tier_pool_size"] = rank, n
            used.add(w["trace_id"])
            chosen.append(w)

    OUT.mkdir(parents=True, exist_ok=True)
    corpus_sha, script_sha = sha256(CORPUS), sha256(HERE)
    records = []
    for i, w in enumerate(chosen, 1):
        name = f"real_lowbw_{i:02d}"
        lines = [
            f"# trace_id={w['trace_id']} source={w['source']} window=[{w['start_s']},{w['end_s']})s "
            f"mean_kbps={w['mean_kbps']:.1f} tier={w['tier']} clamped_seconds={w['n_clamped']}",
            f"# corpus_v1 sha256={corpus_sha[:16]} rule=lowbw_real_v1 seed={SEED}; 1s values, Mbps to kbit/s, "
            f"round to int, floor {FLOOR}; direction={w['direction']} cv={w['cv']:.3f} "
            f"frac_below_600={w['frac_below_600']:.3f}",
        ]
        for j, r in enumerate(w["rates"]):
            lines.append(f"rate {r}")
            if j == 0:
                lines += [f"delay {DELAY}", f"loss {LOSS}"]
            lines.append("wait 1")
        path = OUT / f"{name}.profile"
        path.write_text("\n".join(lines) + "\n")
        rec = {k: v for k, v in w.items() if k != "rates"}
        rec.update({"profile": path.name, "profile_sha256": sha256(path), "rates_kbit": w["rates"]})
        records.append(rec)

    with (OUT / "candidates_grid_v1.csv").open("w", newline="") as f:
        cols = ["trace_id", "source", "direction", "mobility_or_env", "start_s", "end_s", "tier",
                "mean_kbps", "min_kbps", "cv", "frac_below_600", "n_clamped"]
        wr = csv.writer(f)
        wr.writerow(cols)
        for w in sorted(grid_low, key=lambda w: (w["tier"], w["trace_id"], w["start_s"])):
            wr.writerow([round(w[c], 4) if isinstance(w[c], float) else w[c] for c in cols])

    prov = {
        "rule_version": "lowbw_real_v1", "seed": SEED, "window_s": WIN, "delay_ms": DELAY, "loss_pct": LOSS,
        "rate_floor_kbit": FLOOR, "max_clamped_seconds": MAX_CLAMP,
        "corpus_path": str(CORPUS.relative_to(REPO)), "corpus_sha256": corpus_sha,
        "script_path": str(HERE.relative_to(REPO)), "script_sha256": script_sha,
        "selection_rule": SELECTION_RULE,
        "candidate_stats_grid": {
            "grid_windows_total": dict(sorted(grid_total.items())),
            "grid_windows_without_missing": dict(sorted(grid_full.items())),
            "windows_mean_below_1000": len(grid_low),
            "windows_mean_below_1000_by_source": dict(sorted(Counter(w["source"] for w in grid_low).items())),
            "traces_mean_below_1000": len({w["trace_id"] for w in grid_low}),
            "tiers": tier_summary(grid_low),
        },
        "candidate_stats_sliding": {
            "note": "Start points slide by one second, so windows overlap heavily; only the trace count is meaningful",
            "tiers": {k: {"traces": v["traces"], "eligible_traces": v["eligible_traces"],
                          "traces_by_source": v["traces_by_source"]}
                      for k, v in tier_summary(slide_all).items()},
        },
        "shortfall": shortfall,
        "profiles": records,
    }
    (OUT / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1) + "\n")

    print(json.dumps({k: v for k, v in prov.items() if k.startswith("candidate_stats")}, ensure_ascii=False, indent=1))
    for r in records:
        print(f"{r['profile']} {r['tier']} {r['source']} {r['trace_id']} [{r['start_s']},{r['end_s']}) "
              f"mean={r['mean_kbps']:.1f} min={r['min_kbps']:.0f} cv={r['cv']:.3f} "
              f"below600={r['frac_below_600']:.3f} clamped={r['n_clamped']} dir={r['direction']} "
              f"env={r['mobility_or_env']} rank={r['cv_rank_in_tier_pool']}of{r['tier_pool_size']}")
    if shortfall:
        print("SHORTFALL", shortfall)


if __name__ == "__main__":
    main()
