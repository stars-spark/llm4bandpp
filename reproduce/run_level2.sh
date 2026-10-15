#!/usr/bin/env bash
# Level 2 check of the reproduction package: rerun every recomputation command of docs/OFFLINE.md, docs/DESIGNER.md,
# docs/TESTBED.md and docs/RESULTS_INDEX.md, each in a fresh temporary copy of the package with the path
# placeholders set, and check the documented outcome: the script's own match report, a byte comparison of every result
# file it rewrites with the released one (three documented exceptions), and the numbers the docs quote. Prints one row
# per command (command | reproduces | result | seconds) and exits with status 1 if any command fails or does not
# reproduce. The package itself is not modified. Commands that need onnxruntime or torch are skipped without them.
#
# Usage, from the package root:
#   reproduce/run_level2.sh                 # all checks, a few minutes
#   reproduce/run_level2.sh --list          # what is checked
#   reproduce/run_level2.sh --only anchor,twelve-stacks [--keep] [--workdir DIR] [--timeout SECONDS]
# PYTHON selects the interpreter (default: python3), e.g. PYTHON=/opt/env/bin/python3 reproduce/run_level2.sh
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py="${PYTHON:-python3}"
if ! command -v "$py" >/dev/null 2>&1; then
    echo "error: $py not found; set PYTHON to a Python 3.10 or later interpreter" >&2
    exit 2
fi
export PYTHONDONTWRITEBYTECODE=1
exec "$py" "$here/level2_checks.py" "$@"
