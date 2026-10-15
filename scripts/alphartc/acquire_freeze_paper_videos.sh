#!/usr/bin/env bash
# Download the Johnny, Mobcal and Parkrun 720p sequences from the Xiph Derf collection and record their SHA-256 and
# ffprobe output; cut 10 s at 15 fps and loop it to 42 s; compute P.910 SI/TI and write paper_720p_{low,medium,high}.yuv,
# ordered by temporal information, with a provenance record, to the testbed's media directory.
set -euo pipefail

repo="/path/to/llm4bandpp"
testmedia="/path/to/alphartc/LLM4Band/testmedia"
staging="${testmedia}/.paper_video_staging"
complete_marker="${testmedia}/VIDEO_FREEZE_COMPLETE.json"
failure_marker="${testmedia}/VIDEO_FREEZE_FAILED.txt"
log_file="${testmedia}/paper_video_freeze.log"
minimum_start_bytes=$((15 * 1024 * 1024 * 1024))
minimum_remaining_bytes=$((10 * 1024 * 1024 * 1024))
final_bytes=870912000
cycle_bytes=207360000

mkdir -p "${testmedia}" "${staging}"
rm -f "${complete_marker}" "${failure_marker}"
exec >>"${log_file}" 2>&1

on_error() {
    local exit_code=$?
    local line_number=${1:-unknown}
    {
        printf 'failed_at=%s\n' "$(date -Iseconds)"
        printf 'exit_code=%s\n' "${exit_code}"
        printf 'line=%s\n' "${line_number}"
    } >"${failure_marker}.tmp"
    mv "${failure_marker}.tmp" "${failure_marker}"
    exit "${exit_code}"
}
trap 'on_error ${LINENO}' ERR

available_bytes=$(df -B1 --output=avail /path/to/storage | tail -n 1 | tr -d ' ')
if (( available_bytes < minimum_start_bytes )); then
    printf 'insufficient storage before video acquisition: available=%s required=%s\n' "${available_bytes}" "${minimum_start_bytes}" >&2
    exit 31
fi

curl -L --fail --retry 5 --retry-delay 30 \
    https://media.xiph.org/video/derf/ -o "${testmedia}/xiph_derf_index.html"
curl -L --fail --retry 5 --retry-delay 30 \
    https://media.xiph.org/video/derf/ftp.ldv.e-technik.tu-muenchen.de/pub/test_sequences/720p/ReadMe_720p.txt \
    -o "${testmedia}/ReadMe_720p.txt"

ids=(johnny mobcal parkrun)
urls=(
    "https://media.xiph.org/video/derf/y4m/Johnny_1280x720_60.y4m"
    "https://media.xiph.org/video/derf/y4m/720p50_mobcal_ter.y4m"
    "https://media.xiph.org/video/derf/y4m/720p50_parkrun_ter.y4m"
)
expected_sizes=(830826065 696732659 696732659)

for index in 0 1 2; do
    id=${ids[$index]}
    url=${urls[$index]}
    expected=${expected_sizes[$index]}
    download="${staging}/${id}.y4m"
    cycle="${staging}/${id}_10s_15fps.yuv"
    candidate="${staging}/${id}_42s_15fps.yuv"
    curl -L --fail --retry 8 --retry-delay 30 --continue-at - "${url}" -o "${download}"
    actual=$(stat -c %s "${download}")
    [[ "${actual}" == "${expected}" ]] || { printf '%s size=%s expected=%s\n' "${id}" "${actual}" "${expected}" >&2; exit 32; }
    sha256sum "${download}" >"${staging}/${id}_upstream.sha256"
    ffprobe -v error -show_streams -show_format -of json "${download}" >"${staging}/${id}_ffprobe.json"
    ffmpeg -hide_banner -nostdin -y -i "${download}" -t 10 \
        -vf fps=15 -pix_fmt yuv420p -f rawvideo "${cycle}"
    [[ "$(stat -c %s "${cycle}")" == "${cycle_bytes}" ]]
    ffmpeg -hide_banner -nostdin -y -stream_loop -1 \
        -f rawvideo -pixel_format yuv420p -video_size 1280x720 -framerate 15 -i "${cycle}" \
        -t 42 -pix_fmt yuv420p -f rawvideo "${candidate}"
    [[ "$(stat -c %s "${candidate}")" == "${final_bytes}" ]]
    /usr/bin/python3 "${repo}/scripts/alphartc/compute_p910_si_ti.py" \
        --input "${candidate}" --width 1280 --height 720 --frames 150 \
        --out-csv "${staging}/${id}_si_ti.csv" --out-json "${staging}/${id}_si_ti.json"
    rm -f "${download}" "${cycle}"
done

/usr/bin/python3 - "${staging}" "${testmedia}" "${complete_marker}" <<'PY'
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

staging, output, marker = map(Path, sys.argv[1:])


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


source_info = {
    "johnny": {"url": "https://media.xiph.org/video/derf/y4m/Johnny_1280x720_60.y4m", "bytes": 830826065, "license": "public domain per Xiph Derf index"},
    "mobcal": {"url": "https://media.xiph.org/video/derf/y4m/720p50_mobcal_ter.y4m", "bytes": 696732659, "license": "no restrictions; no copyright per ReadMe_720p.txt"},
    "parkrun": {"url": "https://media.xiph.org/video/derf/y4m/720p50_parkrun_ter.y4m", "bytes": 696732659, "license": "no restrictions; no copyright per ReadMe_720p.txt"},
}
ranked = []
for candidate_id in source_info:
    summary = json.loads((staging / f"{candidate_id}_si_ti.json").read_text())
    upstream_hash = (staging / f"{candidate_id}_upstream.sha256").read_text().split()[0]
    ranked.append((summary["ti"]["mean"], candidate_id, summary, upstream_hash))
ranked.sort()
ratios = [ranked[i + 1][0] / ranked[i][0] for i in range(2)]
if any(ratio < 1.15 for ratio in ratios):
    raise SystemExit(f"TI separation ratios {ratios} do not both reach 1.15")

labels = ("low", "medium", "high")
videos = []
for label, (mean_ti, candidate_id, summary, upstream_hash) in zip(labels, ranked):
    final_video = output / f"paper_720p_{label}.yuv"
    final_csv = output / f"paper_720p_{label}_si_ti.csv"
    final_json = output / f"paper_720p_{label}_si_ti.json"
    upstream_ffprobe = output / f"paper_720p_{label}_upstream_ffprobe.json"
    upstream_sum = output / f"paper_720p_{label}_upstream.sha256"
    os.replace(staging / f"{candidate_id}_42s_15fps.yuv", final_video)
    os.replace(staging / f"{candidate_id}_si_ti.csv", final_csv)
    os.replace(staging / f"{candidate_id}_si_ti.json", final_json)
    os.replace(staging / f"{candidate_id}_ffprobe.json", upstream_ffprobe)
    os.replace(staging / f"{candidate_id}_upstream.sha256", upstream_sum)
    videos.append({
        "motion_label": label,
        "candidate_id": candidate_id,
        "source_url": source_info[candidate_id]["url"],
        "source_expected_bytes": source_info[candidate_id]["bytes"],
        "source_sha256": upstream_hash,
        "license": source_info[candidate_id]["license"],
        "preprocessing": "first 10 seconds -> fps=15 yuv420p -> loop and truncate to 42 seconds",
        "video": str(final_video),
        "video_bytes": final_video.stat().st_size,
        "video_sha256": file_sha256(final_video),
        "si_ti_csv": str(final_csv),
        "si_ti_csv_sha256": file_sha256(final_csv),
        "si_ti_summary": str(final_json),
        "si_ti_summary_sha256": file_sha256(final_json),
        "upstream_ffprobe": str(upstream_ffprobe),
        "upstream_sha256_record": str(upstream_sum),
        "classification_frames": 150,
        "mean_si": summary["si"]["mean"],
        "mean_ti": mean_ti,
    })

provenance = {
    "schema": "paper-720p-video-sources-v1",
    "created_at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(),
    "selection_frozen_before_method_evaluation": True,
    "candidate_set": list(source_info),
    "motion_assignment": "ascending classic P.910 mean TI on frames 0..149 of each processed source",
    "minimum_adjacent_ti_ratio": 1.15,
    "observed_adjacent_ti_ratios": ratios,
    "format": {"width": 1280, "height": 720, "fps": 15, "seconds": 42, "frames": 630, "pixel_format": "yuv420p8"},
    "videos": videos,
    "license_evidence": [str(output / "xiph_derf_index.html"), str(output / "ReadMe_720p.txt")],
}
provenance_path = output / "paper_720p_provenance.json"
provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
dictionary = {
    "schema": "paper-720p-video-data-dictionary-v1",
    "si": "per-frame spatial SD of Sobel magnitude on 8-bit luma",
    "ti": "per-frame spatial SD of current minus previous 8-bit luma; absent for frame 0",
    "classification": "ascending mean TI; data-independent candidate set; adjacent ratio must be at least 1.15",
    "raw_video": "headerless 1280x720 yuv420p8 at 15 fps; 630 frames; 42 seconds",
}
(output / "paper_720p_data_dictionary.json").write_text(json.dumps(dictionary, ensure_ascii=False, indent=2) + "\n")
artifacts = [
    *(Path(video["video"]) for video in videos),
    *(Path(video["si_ti_csv"]) for video in videos),
    *(Path(video["si_ti_summary"]) for video in videos),
    *(Path(video["upstream_ffprobe"]) for video in videos),
    *(Path(video["upstream_sha256_record"]) for video in videos),
    provenance_path,
    output / "paper_720p_data_dictionary.json",
    output / "xiph_derf_index.html",
    output / "ReadMe_720p.txt",
]
sums = output / "paper_720p_sha256sums.txt"
with sums.open("w") as handle:
    for path in sorted(artifacts):
        handle.write(f"{file_sha256(path)}  {path.name}\n")
remaining = shutil.disk_usage(output).free
if remaining < 10 * 1024**3:
    raise SystemExit(f"remaining storage {remaining} below 10 GiB")
complete = {
    "status": "complete", "video_count": 3, "frames_each": 630,
    "bytes_each": 870912000, "motion_labels": list(labels),
    "observed_adjacent_ti_ratios": ratios,
    "storage_free_bytes_after": remaining,
    "provenance": str(provenance_path), "sha256_manifest": str(sums),
}
temporary = marker.with_suffix(marker.suffix + ".tmp")
temporary.write_text(json.dumps(complete, ensure_ascii=False, indent=2) + "\n")
os.replace(temporary, marker)
PY

rm -rf "${staging}"
printf 'paper video freeze complete at %s\n' "$(date -Iseconds)"
