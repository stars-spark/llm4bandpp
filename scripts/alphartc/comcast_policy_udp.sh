#!/usr/bin/env bash
# Shape all UDP traffic on COMCAST_DEVICE (default lo; the run scripts pass the sender container's eth0) from a profile of rate, delay, loss and wait lines;
# a netem queue of COMCAST_QUEUE_PACKETS packets keeps the backlog finite.
# First version: every control point stops comcast and rebuilds tc and iptables. The run scripts use it when STALENESS_POLICY is unset, as in the early batches; the paper's
# batches select comcast_policy_udp_v2.sh (320x240) or comcast_policy_tcpudp_v3.sh (720p).
# Usage: comcast_policy_udp.sh PROFILE
# Media uses ephemeral UDP ports, so filtering on signaling port 8000 is wrong.
set -euo pipefail

profile=${1:?usage: comcast_policy_udp.sh PROFILE}
comcast=${COMCAST_BIN:-/root/go/bin/comcast}
device=${COMCAST_DEVICE:-lo}
loop=${COMCAST_LOOP:-0}
queue_packets=${COMCAST_QUEUE_PACKETS:-4}

rate=0
latency=0
loss=0

apply_controls() {
  "$comcast" --device "$device" --stop >/dev/null 2>&1 || true
  "$comcast" --device "$device" --target-proto udp \
    --latency "$latency" --packet-loss "$loss" --target-bw "$rate"
  # Comcast's netem default is 1000 packets.  At 70--220 kbit/s that permits
  # seconds of backlog and floors the paper's 500 ms delay score.  Four RTP
  # packets keep the queue finite while still allowing a several-BDP burst.
  netem=(tc qdisc change dev "$device" parent 10:10 handle 100: netem limit "$queue_packets")
  [[ "$latency" == "0" ]] || netem+=(delay "${latency}ms")
  if [[ "$loss" != "0" && "$loss" != "0%" ]]; then
    loss_arg=$loss
    [[ "$loss_arg" == *% ]] || loss_arg="${loss_arg}%"
    netem+=(loss random "$loss_arg")
  fi
  [[ "$rate" == "0" ]] || netem+=(rate "${rate}kbit")
  "${netem[@]}"
  printf '{"event":"apply","wall_time_ms":%s,"rate_kbps":%s,"latency_ms":%s,"loss_pct":"%s"}\n' \
    "$(date +%s%3N)" "$rate" "$latency" "$loss"
}

run_profile() {
  local dirty=0
  while read -r command value rest; do
    case "$command" in
      ""|\#*) continue ;;
      rate) rate=$value; dirty=1 ;;
      delay) latency=$value; dirty=1 ;;
      loss) loss=$value; dirty=1 ;;
      wait)
        if [[ "$dirty" == "1" ]]; then apply_controls; dirty=0; fi
        sleep "${value%s}"
        ;;
      *) echo "unknown profile command: $command" >&2; return 2 ;;
    esac
  done < "$profile"
  if [[ "$dirty" == "1" ]]; then apply_controls; fi
}

if [[ "$loop" == "1" ]]; then
  while true; do run_profile; done
else
  run_profile
fi
