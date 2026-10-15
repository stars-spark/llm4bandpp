#!/usr/bin/env bash
# realtel-closure-v1 runs (criteria in the registry entry realtel-closure-v1). Each run in its own user and network namespace:
# netem on the loopback interface with 20 ms delay, a rate limit and loss; tcpdump -Z root -G exits by itself; headless Chrome
# in a 60 s loopback audio and video call, exporting the receiver's full getStats every 60 ms.
# Usage: run_closure_v1.sh OUT_DIR "CONDITIONS", each condition written NAME:RATE:LOSS, e.g. r1000_L0:1mbit:0
set -u; HERE=$(cd "$(dirname "$0")" && pwd); OUT=$1; shift; mkdir -p "$OUT"
for spec in $@; do
  IFS=: read -r name rate loss <<< "$spec"; d="$OUT/$name"; [ -f "$d/OK" ] && continue; rm -rf "$d"; mkdir -p "$d"
  timeout 200 unshare -rn bash -c "
    ip link set lo up; ip link set lo mtu 1500; ethtool -K lo tso off gso off gro off >/dev/null 2>&1
    tc qdisc add dev lo root netem delay 20ms loss ${loss}% rate ${rate}; tc qdisc show dev lo > '$d/qdisc.txt'
    tcpdump -Z root -i lo -U -s 200 -G 80 -W 1 -w '$d/cap.pcap' udp 2>'$d/tcpdump.err' & TP=\$!; sleep 1
    python3 '$HERE/logserver.py' 8765 '$d/stats.jsonl' & SP=\$!; sleep 0.5
    google-chrome --headless=new --no-sandbox --disable-gpu --use-fake-device-for-media-stream --use-fake-ui-for-media-stream --allow-loopback-in-peer-connection \
      --disable-features=WebRtcHideLocalIpsWithMdns --autoplay-policy=no-user-gesture-required --user-data-dir='$d/chrome' 'http://localhost:8765/page_closure.html?dur=60' >'$d/chrome.log' 2>&1 & CP=\$!
    for i in \$(seq 1 110); do [ -f '$d/stats.jsonl.DONE' ] && break; sleep 1; done
    kill \$CP \$SP 2>/dev/null; sleep 1; rm -rf '$d/chrome'
    for i in \$(seq 1 120); do kill -0 \$TP 2>/dev/null || break; ping -c 1 -W 1 -q 127.0.0.1 >/dev/null 2>&1; sleep 1; done
    wait 2>/dev/null
  "
  n=$(stat -c %s "$d/cap.pcap" 2>/dev/null || echo 0); s=$(wc -l < "$d/stats.jsonl" 2>/dev/null || echo 0)
  if [ "$n" -gt 100000 ] && [ "$s" -gt 500 ]; then date -Is > "$d/OK"; echo "$(date '+%T') $name completed, captured $n bytes, $s snapshots"; else date -Is > "$d/BAD"; echo "$(date '+%T') $name failed the size check, captured $n bytes, $s snapshots"; fi
done
