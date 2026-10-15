#!/usr/bin/env bash
# gcc-native-calib-v1 runs (pre-registration registry/preregistrations/prereg_26.md): each run in its own user and network
# namespace, netem rate limit and delay on the loopback interface, headless Chrome in a 720p loopback call on one page (fake
# camera looping the Johnny 720p y4m), estimated by the native libwebrtc GCC; getStats every 500 ms. Capacities 1000 and
# 2000 kbit/s with the queue lengths of the testbed's hd_c1 and hd_c2 (27 and 53 packets), 3 runs each, 70 s per run.
set -u; HERE=$(cd "$(dirname "$0")" && pwd); OUT=${1:-/path/to/testbed/results/gcc-native-calib-v1/runs}; Y4M=/path/to/testbed/gcc_native/johnny_720p.y4m; mkdir -p "$OUT"
one() {
  local cap=$1 qp=$2 rep=$3 d="$OUT/c${1}_r${3}"; [ -f "$d/OK" ] && return 0; rm -rf "$d"; mkdir -p "$d"
  timeout 150 unshare -rn bash -c "
    ip link set lo up; ip link set lo mtu 1500; ethtool -K lo tso off gso off gro off >/dev/null 2>&1
    tc qdisc add dev lo root netem delay 50ms rate ${cap}kbit limit ${qp}
    tc qdisc show dev lo > '$d/qdisc.txt'
    python3 '$HERE/logserver.py' 8766 '$d/stats.jsonl' & SP=\$!; sleep 0.5
    google-chrome --headless=new --no-sandbox --disable-gpu --use-fake-device-for-media-stream --use-fake-ui-for-media-stream --use-file-for-fake-video-capture='$Y4M' \
      --allow-loopback-in-peer-connection --disable-features=WebRtcHideLocalIpsWithMdns --autoplay-policy=no-user-gesture-required --user-data-dir='$d/chrome' \
      'http://localhost:8766/page_gcc.html?dur=70' >'$d/chrome.log' 2>&1 & CP=\$!
    for i in \$(seq 1 120); do [ -f '$d/stats.jsonl.DONE' ] && break; sleep 1; done
    kill \$CP \$SP 2>/dev/null; wait 2>/dev/null; rm -rf '$d/chrome'
  "
  if [ -f "$d/stats.jsonl.DONE" ] && [ "$(wc -l < "$d/stats.jsonl")" -gt 100 ]; then date -Is > "$d/OK"; echo "$(date '+%T') c$cap r$rep completed"; else date -Is > "$d/BAD"; echo "$(date '+%T') c$cap r$rep failed"; fi
}
for rep in 1 2 3; do one 1000 27 $rep; one 2000 53 $rep; done
date -Is > "$OUT/../QUEUE_COMPLETE"; echo "all done"
