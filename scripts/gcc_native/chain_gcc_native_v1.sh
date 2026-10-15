#!/usr/bin/env bash
# gcc-native-calib-v1 chain (2026-10-07): wait until the testbed queue has finished (R7_TAIL_DONE) so that Chrome and the
# testbed do not compete for CPU -> one smoke run (2000 kbit/s, into the smoke directory) -> the 6 runs -> summary and registry entry.
set -uo pipefail
repo=/path/to/llm4bandpp; H=$repo/scripts/gcc_native; R=/path/to/testbed/results; K=$R/gcc-native-calib-v1; LOG=$repo/logs/chain_gcc_native_v1.log; ID=gcc-native-calib-v1
log() { echo "[$(TZ=Asia/Shanghai date '+%F %T')] $*" >> "$LOG"; }
stop() { log "Stop: $1"; python3 "$repo/scripts/exp.py" note --id $ID "Chain stopped: $1 (see logs/chain_gcc_native_v1.log)" >> "$LOG" 2>&1; mkdir -p "$K"; date -Is > "$K/CHAIN_FAILED"; exit 1; }
log "Chain started; waiting for the testbed queue to finish"
for i in $(seq 1 360); do [[ -f "$R/R7_TAIL_DONE" ]] && break; sleep 300; done
[[ -f "$R/R7_TAIL_DONE" ]] || stop "testbed queue did not finish within 30 hours"
sleep 60; pgrep -f '^python3 .*parallel_testbed_v' > /dev/null && stop "there are still schedulers running"
SM=$K/smoke; mkdir -p "$SM"
bash -c "source <(sed -n '/^one()/,/^}/p' $H/run_gcc_native_v1.sh); HERE=$H; OUT=$SM; Y4M=/path/to/testbed/gcc_native/johnny_720p.y4m; one 2000 53 1" >> "$LOG" 2>&1
[[ -f "$SM/c2000_r1/OK" ]] || stop "smoke test did not pass (see $SM/c2000_r1)"
python3 - "$SM/c2000_r1/stats.jsonl" >> "$LOG" 2>&1 <<'PY' || stop "smoke test readings are incomplete"
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]; R = [x for r in rows for x in r.get("rows", [])]
inb = [x for x in R if x.get("type") == "inbound-rtp" and x.get("bytesReceived")]; cp = [x for x in R if x.get("type") == "candidate-pair" and x.get("availableOutgoingBitrate")]
w = max((x.get("frameWidth") or 0) for x in R if x.get("type") == "outbound-rtp")
assert len(inb) > 50 and len(cp) > 50, (len(inb), len(cp)); print("smoke test readings are complete: received samples", len(inb), "estimation sample", len(cp), "Send maximum width", w)
PY
log "Smoke test passed, start the run"; bash "$H/run_gcc_native_v1.sh" "$K/runs" >> "$LOG" 2>&1
[[ -f "$K/QUEUE_COMPLETE" ]] || stop "full run did not write QUEUE_COMPLETE"
if python3 "$H/gcc_native_calib_v1.py" >> "$LOG" 2>&1; then date -Is > "$K/JUDGED"; log "Summary complete"; else stop "Summary script error"; fi
