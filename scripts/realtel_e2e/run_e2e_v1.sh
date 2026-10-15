#!/usr/bin/env bash
# realtel-e2e-v1 batch (criteria in registry/preregistrations/prereg_51.md). Each run in its own user and network namespace:
# netem on the loopback interface with 10 ms delay plus loss, tcpdump -Z root capture, one source per run. Loss 0, 2 and 5%,
# two runs each, four sources. tcpdump stops by itself after G seconds, longer than the source's run time.
set -u; HERE=$(cd "$(dirname "$0")" && pwd); OUT=${1:-/path/to/llm4bandpp/experiments/results/realtel_e2e_v1/runs}; mkdir -p "$OUT"
IPERF=$HOME/opt/iperf3/bin/iperf3
one() {
  local src=$1 loss=$2 rep=$3 d="$OUT/${1}_L${2}_r${3}"; [ -f "$d/OK" ] && return 0; rm -rf "$d"; mkdir -p "$d"
  local G; case $1 in w3c) G=60;; iperf3) G=40;; tcpinfo) G=40;; gst) G=70;; esac
  timeout 180 unshare -rn bash -c "
    ip link set lo up; ip link set lo mtu 1500; ethtool -K lo tso off gso off gro off >/dev/null 2>&1
    tc qdisc add dev lo root netem delay 10ms loss ${loss}%
    tc qdisc show dev lo > '$d/qdisc.txt'; ethtool -k lo 2>/dev/null | grep -E 'segmentation-offload|receive-offload' > '$d/offload.txt'
    tcpdump -Z root -i lo -U -s 160 -G $G -W 1 -w '$d/cap.pcap' 2>'$d/tcpdump.err' & TP=\$!; sleep 1
    case $src in
      w3c)
        python3 '$HERE/logserver.py' 8765 '$d/stats.jsonl' & SP=\$!; sleep 0.5
        google-chrome --headless=new --no-sandbox --disable-gpu --use-fake-device-for-media-stream --use-fake-ui-for-media-stream --allow-loopback-in-peer-connection \
          --disable-features=WebRtcHideLocalIpsWithMdns --autoplay-policy=no-user-gesture-required --user-data-dir='$d/chrome' 'http://localhost:8765/page.html?dur=40' >'$d/chrome.log' 2>&1 & CP=\$!
        for i in \$(seq 1 90); do [ -f '$d/stats.jsonl.DONE' ] && break; sleep 1; done
        kill \$CP \$SP 2>/dev/null; rm -rf '$d/chrome' ;;
      iperf3)
        $IPERF -s -1 -J > '$d/server.json' 2>'$d/server.err' & SP=\$!; sleep 0.5
        $IPERF -c 127.0.0.1 -u -b 1M -l 1200 -t 30 -i 1 -J > '$d/client.json' 2>'$d/client.err'; wait \$SP ;;
      tcpinfo)
        python3 '$HERE/tcpinfo_pair.py' '$d/tcpinfo.jsonl' 30 1500000 ;;
      gst)
        gst-launch-1.0 -q rtpbin name=rb udpsrc port=5000 caps='application/x-rtp,media=video,clock-rate=90000,encoding-name=VP8,payload=96' ! rb.recv_rtp_sink_0 rb. ! rtpvp8depay ! fakesink \
          udpsrc port=5001 ! rb.recv_rtcp_sink_0 rb.send_rtcp_src_0 ! udpsink host=127.0.0.1 port=5005 sync=false async=false >'$d/recv.log' 2>&1 & RP=\$!
        gst-launch-1.0 -q rtpbin name=rb videotestsrc is-live=true pattern=ball ! video/x-raw,width=640,height=480,framerate=30/1 ! vp8enc deadline=1 target-bitrate=1000000 ! rtpvp8pay pt=96 mtu=1200 \
          ! rb.send_rtp_sink_0 rb.send_rtp_src_0 ! udpsink host=127.0.0.1 port=5000 rb.send_rtcp_src_0 ! udpsink host=127.0.0.1 port=5001 sync=false async=false udpsrc port=5005 ! rb.recv_rtcp_sink_0 >'$d/send.log' 2>&1 & XP=\$!
        sleep 60; kill \$XP \$RP 2>/dev/null ;;
    esac
    for i in \$(seq 1 120); do kill -0 \$TP 2>/dev/null || break; ping -c 1 -W 1 -q 127.0.0.1 >/dev/null 2>&1; sleep 1; done
    wait 2>/dev/null
  "
  local n; n=$(python3 -c "import os;print(os.path.getsize('$d/cap.pcap'))" 2>/dev/null || echo 0)
  if [ "$n" -gt 10000 ]; then date -Is > "$d/OK"; echo "$(date '+%T') $src L$loss r$rep completed, captured $n bytes"; else echo "$(date '+%T') $src L$loss r$rep capture too small $n, marked BAD"; date -Is > "$d/BAD"; fi
}
for rep in 1 2; do for loss in 0 2 5; do for src in w3c iperf3 tcpinfo gst; do one $src $loss $rep; done; done; done
date -Is > "$OUT/../QUEUE_COMPLETE"; echo "all done"
