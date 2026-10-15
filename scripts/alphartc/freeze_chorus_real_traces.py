#!/usr/bin/env python3
"""Convert four preregistered Chorus bandwidth traces into fixed AlphaRTC profiles."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import statistics


SOURCE_URL = "https://github.com/GreenLv/Chorus.git"
SOURCE_COMMIT = "8e1e26bc07bcbd0f33e19b00b44768cd75959941"
HEADER = ["Timestamp (s)", "Bandwidth (Mbps)"]
WINDOW_START = Decimal("1.0")
WINDOW_END = Decimal("43.0")
SOURCE_STEP = Decimal("0.2")
BIN_SECONDS = Decimal("1.0")
EXPECTED_SAMPLES_PER_BIN = 5
MAX_RATE_KBPS = 20_000
SELECTIONS = (
    ("real_01", "airport", "downlink-cellular_airport.csv"),
    ("real_02", "driving", "downlink-cellular_driving_2.csv"),
    ("real_03", "high_speed_rail", "downlink-cellular_hsr_16.csv"),
    ("real_04", "railway_station", "downlink-cellular_railwaystation_2.csv"),
)


@dataclass(frozen=True)
class Sample:
    timestamp_s: Decimal
    bandwidth_mbps: Decimal
    source_line: int


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_source(path: Path) -> list[Sample]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header != HEADER:
            raise ValueError(f"{path.name}: unexpected header {header!r}")
        samples = [
            Sample(Decimal(row[0]), Decimal(row[1]), line_number)
            for line_number, row in enumerate(reader, start=2)
            if row
        ]
    if len(samples) < 2:
        raise ValueError(f"{path.name}: too few samples")
    for left, right in zip(samples, samples[1:]):
        delta = right.timestamp_s - left.timestamp_s
        if delta != SOURCE_STEP:
            raise ValueError(
                f"{path.name}: timestamp step at source line {right.source_line} is {delta}, expected {SOURCE_STEP}"
            )
    return samples


def aggregate(
    samples: list[Sample], source_name: str,
    window_start: Decimal = WINDOW_START,
    window_end: Decimal = WINDOW_END,
) -> list[dict]:
    rows = []
    for bin_index in range(int((window_end - window_start) / BIN_SECONDS)):
        start = window_start + bin_index * BIN_SECONDS
        end = start + BIN_SECONDS
        selected = [sample for sample in samples if start <= sample.timestamp_s < end]
        if len(selected) != EXPECTED_SAMPLES_PER_BIN:
            raise ValueError(
                f"{source_name}: [{start},{end}) has {len(selected)} samples, expected {EXPECTED_SAMPLES_PER_BIN}"
            )
        mean_mbps = sum((sample.bandwidth_mbps for sample in selected), Decimal(0)) / len(selected)
        rate_kbps = int((mean_mbps * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if not 1 <= rate_kbps <= MAX_RATE_KBPS:
            raise ValueError(f"{source_name}: bin {bin_index + 1} rate {rate_kbps} kbit/s is outside 1..20000")
        rows.append({
            "bin_index": bin_index + 1,
            "start_s": str(start),
            "end_s": str(end),
            "sample_count": len(selected),
            "mean_bandwidth_mbps": f"{mean_mbps:.6f}",
            "rate_kbps": rate_kbps,
            "source_first_line": selected[0].source_line,
            "source_last_line": selected[-1].source_line,
            "source_timestamps_s": ";".join(str(sample.timestamp_s) for sample in selected),
        })
    return rows


def select_earliest_eligible_window(samples: list[Sample], source_name: str) -> tuple[Decimal, Decimal, list[dict]]:
    duration = WINDOW_END - WINDOW_START
    last_covered_time = samples[-1].timestamp_s + SOURCE_STEP
    latest_start = int(last_covered_time - duration)
    for integer_start in range(int(WINDOW_START), latest_start + 1):
        start = Decimal(integer_start)
        end = start + duration
        try:
            rows = aggregate(samples, source_name, start, end)
        except ValueError as error:
            if "outside 1..20000" in str(error):
                continue
            raise
        return start, end, rows
    raise ValueError(f"{source_name}: no eligible 42-second integer-aligned window in 1..20000 kbit/s")


def write_profile(
    path: Path, trace_id: str, source_name: str,
    window_start: Decimal, window_end: Decimal, rows: list[dict],
) -> None:
    lines = [
        f"# trace_id={trace_id} source={source_name}",
        f"# Chorus commit={SOURCE_COMMIT} window=[{window_start},{window_end})s; 1s arithmetic means; Mbps to kbit/s only",
    ]
    for index, row in enumerate(rows):
        lines.append(f"rate {row['rate_kbps']}")
        if index == 0:
            lines.extend(("delay 50", "loss 0"))
        lines.append("wait 1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_rates(rows: list[dict]) -> dict:
    rates = [row["rate_kbps"] for row in rows]
    return {
        "bins": len(rates),
        "mean_kbps": statistics.fmean(rates),
        "min_kbps": min(rates),
        "max_kbps": max(rates),
        "population_sd_kbps": statistics.pstdev(rates),
        "cv": statistics.pstdev(rates) / statistics.fmean(rates),
    }


def freeze(source_root: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    for trace_id, scenario, filename in SELECTIONS:
        source = source_root / "bw_traces" / filename
        samples = load_source(source)
        window_start, window_end, rows = select_earliest_eligible_window(samples, filename)
        profile = out / f"{trace_id}.profile"
        bins_csv = out / f"{trace_id}_bins.csv"
        write_profile(profile, trace_id, filename, window_start, window_end, rows)
        fields = ["trace_id", "scenario", "source_file", *rows[0].keys()]
        with bins_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({"trace_id": trace_id, "scenario": scenario, "source_file": filename, **row})
        manifest_rows.append({
            "trace_id": trace_id,
            "scenario": scenario,
            "source_file": str(source),
            "source_sha256": sha256(source),
            "source_rows": len(samples),
            "source_start_s": str(samples[0].timestamp_s),
            "source_end_s": str(samples[-1].timestamp_s),
            "selected_window": f"[{window_start},{window_end}) seconds",
            "profile": str(profile),
            "profile_sha256": sha256(profile),
            "bin_mapping": str(bins_csv),
            "bin_mapping_sha256": sha256(bins_csv),
            "rate_summary": summarize_rates(rows),
            "training_or_tuning_use": "none",
        })

    dictionary = {
        "schema": "chorus-to-alphartc-profile-v1",
        "source_columns": {"Timestamp (s)": "seconds", "Bandwidth (Mbps)": "measured downlink bandwidth in Mbps"},
        "bin_mapping_columns": {
            "start_s,end_s": "half-open one-second interval in the source trace",
            "mean_bandwidth_mbps": "arithmetic mean of five 0.2-second source samples",
            "rate_kbps": "mean_bandwidth_mbps multiplied by 1000 and rounded half-up; no scaling or clipping",
            "source_first_line,source_last_line": "1-based lines in the original CSV including its header",
        },
        "testbed_constants": {"delay_ms": 50, "loss_percent": 0},
        "interpretation": "The replay uses measured available downlink bandwidth as the shaping-rate series; it is not a direct measurement of physical link capacity.",
    }
    dictionary_path = out / "data_dictionary.json"
    dictionary_path.write_text(json.dumps(dictionary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "schema": "staleness-real-traces-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "source_url": SOURCE_URL,
        "source_commit": SOURCE_COMMIT,
        "license": "CC BY 4.0; see pinned checkout LICENSE",
        "selection_frozen_before_method_evaluation": True,
        "selection_rule": "four named scenario files; independently choose the earliest integer-second 42-second window whose rates all fit 1..20000 kbit/s, preregistered in paper-real-trace-freeze-v19",
        "aggregation": "five 0.2-second samples per 1-second half-open bin; arithmetic mean",
        "conversion": "Mbps * 1000 -> kbit/s, round half-up; no scaling and no clipping",
        "traces": manifest_rows,
    }
    provenance_path = out / "provenance.json"
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts = sorted([*out.glob("real_*.profile"), *out.glob("real_*_bins.csv"), dictionary_path, provenance_path])
    sums = out / "sha256sums.txt"
    sums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in artifacts), encoding="utf-8")
    complete = {
        "status": "complete",
        "trace_count": len(manifest_rows),
        "bins_per_trace": 42,
        "source_commit": SOURCE_COMMIT,
        "provenance": str(provenance_path),
        "sha256_manifest": str(sums),
    }
    temporary = out / "FREEZE_COMPLETE.json.tmp"
    temporary.write_text(json.dumps(complete, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, out / "FREEZE_COMPLETE.json")
    return complete


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.source_root, args.out), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
