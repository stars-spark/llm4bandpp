#!/usr/bin/env bash
# Shape the sender egress from a profile with comcast, as comcast_policy_udp_v2.sh. With COMCAST_TCP_PORT set, a mangle rule puts TCP to that destination port into the
# rate-limited class 10:10, so a competing TCP flow shares the netem queue with the media; the rule is removed on exit and a tcp_classify event is logged.
# Version 3: copy of v2 with only this rule and a TERM trap; without COMCAST_TCP_PORT it shapes as v2. Selected with STALENESS_POLICY=v3 (run scripts v12 and later):
# the policy of every 720p batch, and of the TCP competitor (deploy/bg_tcp_flow_v1.py, port 5201) in compete-flow-ch-v1.
# Usage: comcast_policy_tcpudp_v3.sh PROFILE
set -euo pipefail

profile=${1:?usage: comcast_policy_udp_v2.sh PROFILE}
comcast=${COMCAST_BIN:-/root/go/bin/comcast}
device=${COMCAST_DEVICE:-lo}
loop=${COMCAST_LOOP:-0}
queue_packets=${COMCAST_QUEUE_PACKETS:-4}
tcp_port=${COMCAST_TCP_PORT:-}

rate=0
latency=0
loss=0
built=0
deadline_ns=0

del_tcp_rule() {
  [[ -n "$tcp_port" ]] || return 0
  while iptables -t mangle -D POSTROUTING -p tcp --dport "$tcp_port" -j CLASSIFY --set-class 10:10 2>/dev/null; do :; done
  return 0
}
add_tcp_rule() {
  [[ -n "$tcp_port" ]] || return 0
  del_tcp_rule
  iptables -t mangle -A POSTROUTING -p tcp --dport "$tcp_port" -j CLASSIFY --set-class 10:10
  printf '{"event":"tcp_classify","wall_time_ms":%s,"dport":%s,"class":"10:10"}\n' "$(date +%s%3N)" "$tcp_port"
}
on_exit() { del_tcp_rule; }
trap on_exit EXIT
trap 'exit 143' TERM INT

netem_args() {
  netem=(netem limit "$queue_packets")
  [[ "$latency" == "0" ]] || netem+=(delay "${latency}ms")
  if [[ "$loss" != "0" && "$loss" != "0%" ]]; then
    loss_arg=$loss
    [[ "$loss_arg" == *% ]] || loss_arg="${loss_arg}%"
    netem+=(loss random "$loss_arg")
  fi
  [[ "$rate" == "0" ]] || netem+=(rate "${rate}kbit")
}

apply_controls() {
  netem_args
  if [[ "$built" == "0" ]]; then
    "$comcast" --device "$device" --stop >/dev/null 2>&1 || true
    "$comcast" --device "$device" --target-proto udp \
      --latency "$latency" --packet-loss "$loss" --target-bw "$rate"
    tc qdisc change dev "$device" parent 10:10 handle 100: "${netem[@]}"
    add_tcp_rule
    built=1
    mode=build
  else
    [[ "$rate" == "0" ]] || tc class change dev "$device" parent 10: classid 10:10 htb rate "${rate}kbit"
    tc qdisc change dev "$device" parent 10:10 handle 100: "${netem[@]}"
    mode=change
  fi
  printf '{"event":"apply","mode":"%s","wall_time_ms":%s,"rate_kbps":%s,"latency_ms":%s,"loss_pct":"%s"}\n' \
    "$mode" "$(date +%s%3N)" "$rate" "$latency" "$loss"
}

sleep_until_deadline() {
  local secs=${1%s} now_ns rem_ns
  (( deadline_ns == 0 )) && deadline_ns=$(date +%s%N)
  deadline_ns=$(( deadline_ns + $(python3 -c "print(int(float('$secs')*1e9))") ))
  now_ns=$(date +%s%N); rem_ns=$(( deadline_ns - now_ns ))
  (( rem_ns > 0 )) && sleep "$(python3 -c "print($rem_ns/1e9)")"
  return 0
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
        sleep_until_deadline "$value"
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
