#!/usr/bin/env bash
# Fetch the Chorus trace repository (GreenLv/Chorus) at the pinned commit with a sparse checkout of bw_traces, retrying
# git up to five times; record the SHA-256 of README, LICENSE and the downlink cellular CSV traces and write a completion
# or failure marker. freeze_chorus_real_traces.py then turns four pre-registered traces into AlphaRTC profiles.
set -euo pipefail

source_url="https://github.com/GreenLv/Chorus.git"
source_commit="8e1e26bc07bcbd0f33e19b00b44768cd75959941"
asset_root="/path/to/alphartc/LLM4Band/real_trace_sources"
checkout="${asset_root}/Chorus-8e1e26bc"
complete_marker="${asset_root}/CHORUS_ACQUIRE_COMPLETE.json"
failure_marker="${asset_root}/CHORUS_ACQUIRE_FAILED.txt"
log_file="${asset_root}/chorus_acquire.log"

mkdir -p "${asset_root}"
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

retry_git() {
    local attempt
    for attempt in 1 2 3 4 5; do
        if "$@"; then
            return 0
        fi
        printf 'git retry attempt=%s time=%s\n' "${attempt}" "$(date -Iseconds)"
        sleep 30
    done
    return 1
}

if [[ ! -d "${checkout}/.git" ]]; then
    rm -rf "${checkout}.partial"
    retry_git git clone --filter=blob:none --no-checkout "${source_url}" "${checkout}.partial"
    mv "${checkout}.partial" "${checkout}"
fi

retry_git git -C "${checkout}" fetch --filter=blob:none origin "${source_commit}"
git -C "${checkout}" sparse-checkout init --cone
git -C "${checkout}" sparse-checkout set bw_traces
git -C "${checkout}" checkout --detach "${source_commit}"

actual_commit=$(git -C "${checkout}" rev-parse HEAD)
[[ "${actual_commit}" == "${source_commit}" ]]
test -s "${checkout}/README.md"
test -s "${checkout}/LICENSE"

python3 - "${checkout}" "${complete_marker}" "${source_url}" "${source_commit}" <<'PY'
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys

checkout = Path(sys.argv[1])
marker = Path(sys.argv[2])
source_url = sys.argv[3]
source_commit = sys.argv[4]
csv_files = sorted((checkout / "bw_traces").glob("downlink-cellular*.csv"))
if len(csv_files) < 4:
    raise SystemExit(f"expected at least four downlink cellular CSV traces, found {len(csv_files)}")

selected_files = [checkout / "README.md", checkout / "LICENSE", *csv_files]
manifest_path = checkout / "source_sha256sums.txt"
total_bytes = 0
with manifest_path.open("w", encoding="utf-8") as output:
    for path in selected_files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        total_bytes += path.stat().st_size
        output.write(f"{digest}  {path.relative_to(checkout)}\n")

payload = {
    "status": "complete",
    "completed_at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(),
    "source_url": source_url,
    "source_commit": source_commit,
    "checkout": str(checkout),
    "license_file": str(checkout / "LICENSE"),
    "readme_file": str(checkout / "README.md"),
    "downlink_cellular_csv_count": len(csv_files),
    "bytes_hashed": total_bytes,
    "sha256_manifest": str(manifest_path),
    "selection_status": "not selected; a separate preregistered conversion step must freeze four held-out profiles before method evaluation",
}
temporary = marker.with_suffix(marker.suffix + ".tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(temporary, marker)
PY

printf 'Chorus source acquisition complete at %s\n' "$(date -Iseconds)"
