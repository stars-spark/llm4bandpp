#!/usr/bin/env bash
# Run one AlphaRTC call on the two-container testbed with estimator ALGORITHM, the sender egress shaped by PROFILE; logs, traces, code hashes and results go to OUT.
# Version 25: copy of v24 that adds arm_ch_schema, the deployed system behind the interface layer and adapter (installs estimator entry point v17 and deploy/fixed_schema_ch_v1.py).
# Used by hd720_designer_ch_v1.py (hd720-designer-ch-v1, Table IV).
# Usage: run_staleness_once_twocontainer_midsnap_v25.sh ALGORITHM PROFILE DELAY REP [OUT] [QUEUE]
set -euo pipefail

algorithm=${1:?usage: run_staleness_once_twocontainer.sh ALGORITHM PROFILE DELAY REP [OUT] [QUEUE]}
profile_path=${2:?missing profile}
delay_ms=${3:?missing delay}
rep=${4:?missing repetition}
receiver_container=${ALPHARTC_RECEIVER_CONTAINER:-alphartc4band}
sender_container=${ALPHARTC_SENDER_CONTAINER:-alphartc-staleness-sender}
network=${ALPHARTC_NETWORK:-bwe-staleness-net}
repo=$(cd "$(dirname "$0")/../.." && pwd)
app_host=${ALPHARTC_APP_HOST:-/path/to/alphartc/LLM4Band}
out_host=${5:-$app_host/result/staleness}
queue_packets=${6:-32}
capture_media=${STALENESS_CAPTURE_MEDIA:-0}
capture_frame_ids=${STALENESS_CAPTURE_FRAME_IDS:-0}
source_file=${STALENESS_SOURCE_FILE:-testmedia/test.yuv}
source_fps=${STALENESS_SOURCE_FPS:-15}
source_width=${STALENESS_SOURCE_WIDTH:-320}
source_height=${STALENESS_SOURCE_HEIGHT:-240}
video_id=${STALENESS_VIDEO_ID:-}
min_decoded_frames=${STALENESS_MIN_DECODED_FRAMES:-0}
monitor_poll_ms=${STALENESS_MONITOR_POLL_MS:-5}
control_slack_s=${STALENESS_CONTROL_SLACK_S:-0}
bwe_feedback_ms=${STALENESS_BWE_FEEDBACK_MS:-}
sender_estimator=${STALENESS_SENDER_ESTIMATOR:-}
sender_logging=${STALENESS_SENDER_LOGGING:-0}
sender_fixed_bps=${STALENESS_SENDER_FIXED_BPS:-}
# Empty by default. A diagnostic run outside the paper sets it to force a known receiver
# estimate; when it is unset, the command environment is unchanged.
receiver_fixed_bps=${BWE_RECEIVER_FIXED_BPS:-}
strace_media=${STALENESS_STRACE_MEDIA:-0}
uprobe_sink=${STALENESS_UPROBE_SINK:-0}
bg_kbps=${STALENESS_BG_UDP_KBPS:-}
bg_start_s=${STALENESS_BG_START_S:-30}
bg_stop_s=${STALENESS_BG_STOP_S:-90}
competitor=${STALENESS_COMPETITOR:-}
comp_start_s=${STALENESS_COMP_START_S:-30}
comp_stop_s=${STALENESS_COMP_STOP_S:-90}
comp_estimator=${STALENESS_COMP_ESTIMATOR:-gcc_pt125_c200}
comp_source=${STALENESS_COMP_SOURCE_FILE:-}
require_gso_segs=${STALENESS_REQUIRE_GSO_SEGS:-}
uprobe_symbol_role=${STALENESS_UPROBE_SYMBOL_ROLE:-core}
uprobe_probe_set=${STALENESS_UPROBE_PROBE_SET:-callback-only}
qwen25_bundle=${BWE_QWEN25_BUNDLE_HOST:-$app_host/model/contextual_qwen25_online}
qwen25_model=${BWE_QWEN25_MODEL_HOST:-$app_host/huggingface/Qwen2.5-0.5B}
c3_risk_bundle=${BWE_C3_RISK_BUNDLE_HOST:-$app_host/model/c3_risk3_online}

case "$algorithm" in
  gcc|gcc_pt125|gcc_pt125_c200|echo_x|adapt_x|switch_llm_x|qwen_dual|fixed_240|fixed_env|qwen25_contextual|c3_risk3|switch_nn|arm_pioneer|arm_schaferct_public|arm_schaferct_retrained|arm_mlp|switch_llm|arm_llm4bandpp|arm_llm4band_conf|switch_gccguard|arm_llm4bandpp_x|arm_llm4bandpp_nl_x|arm_nl_schema|arm_ch_x|arm_llm4band_conf_x|switch_nn_x|arm_lambda|arm_schaferct_public_x|arm_default_env5|arm_default_repair|arm_default_schema|arm_llm4bandpp_schema|arm_schaferct_retrained_d|arm_mlp_d|arm_ch_schema) ;;
  *) echo "unsupported algorithm: $algorithm" >&2; exit 2;;
esac
if [[ "$algorithm" == qwen25_contextual ]]; then
  for required in \
    "$qwen25_bundle/checkpoint_20000.pt" \
    "$qwen25_bundle/training_estimator.py" \
    "$qwen25_bundle/contextual_module.py" \
    "$qwen25_bundle/online_contextual_qwen25.py" \
    "$qwen25_bundle/manifest.json" \
    "$qwen25_model/config.json" \
    "$qwen25_model/model.safetensors"; do
    [[ -s "$required" ]] || { echo "missing qwen25 runtime artifact: $required" >&2; exit 2; }
  done
fi
if [[ "$algorithm" == c3_risk3 ]]; then
  for required in \
    "$c3_risk_bundle/checkpoint_50000.pt" \
    "$c3_risk_bundle/training_estimator.py" \
    "$c3_risk_bundle/module.py" \
    "$c3_risk_bundle/encoder_v3.py" \
    "$c3_risk_bundle/online_c3_risk.py" \
    "$c3_risk_bundle/manifest.json"; do
    [[ -s "$required" ]] || { echo "missing c3 risk3 runtime artifact: $required" >&2; exit 2; }
  done
fi
[[ "$delay_ms" =~ ^[0-9]+$ ]] || exit 2
[[ "$rep" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$source_fps" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$control_slack_s" =~ ^[0-9]+$ ]] || exit 2
[[ "$source_width" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$source_height" =~ ^[1-9][0-9]*$ ]] || exit 2
(( source_width % 2 == 0 && source_height % 2 == 0 )) || exit 2
[[ "$capture_frame_ids" == 0 || "$capture_frame_ids" == 1 ]] || exit 2
[[ -z "$receiver_fixed_bps" || "$receiver_fixed_bps" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$capture_frame_ids" == 0 || "$capture_media" == 1 ]] || {
  echo "STALENESS_CAPTURE_FRAME_IDS=1 requires STALENESS_CAPTURE_MEDIA=1" >&2; exit 2;
}
[[ -z "$video_id" || "$video_id" =~ ^[A-Za-z0-9.-]+$ ]] || exit 2
case "$competitor" in ""|tcp|gcc) ;; *) echo "unsupported competitor: $competitor" >&2; exit 2;; esac
[[ "$comp_start_s" =~ ^[0-9]+$ && "$comp_stop_s" =~ ^[0-9]+$ ]] && (( comp_start_s >= 4 && comp_stop_s > comp_start_s + 4 )) || exit 2
if [[ "$competitor" == gcc ]]; then
  [[ -n "$comp_source" ]] || { echo "competitor gcc needs STALENESS_COMP_SOURCE_FILE" >&2; exit 2; }
  case "$comp_estimator" in gcc|gcc_pt125|gcc_pt125_c200) ;; *) echo "unsupported competitor estimator: $comp_estimator" >&2; exit 2;; esac
fi
case "$out_host" in "$app_host"/*) out_app="/app/${out_host#"$app_host"/}" ;; *) exit 2;; esac
case "$source_file" in
  /app/*) source_host_path="$app_host/${source_file#/app/}" ;;
  /*) echo "source file must be relative to /app or start with /app/: $source_file" >&2; exit 2 ;;
  *) source_host_path="$app_host/$source_file" ;;
esac
[[ -s "$source_host_path" ]] || { echo "missing source video: $source_host_path" >&2; exit 2; }
comp_source_host_path=""
if [[ "$competitor" == gcc ]]; then
  case "$comp_source" in /*) echo "competitor source must be relative to /app" >&2; exit 2 ;; *) comp_source_host_path="$app_host/$comp_source" ;; esac
  [[ -s "$comp_source_host_path" ]] || { echo "missing competitor source: $comp_source_host_path" >&2; exit 2; }
fi

profile_name=$(basename "$profile_path" .profile)
profile_seconds=$(awk '$1 == "wait" {gsub(/s$/, "", $2); total += $2} END {print int(total + 0.999)}' "$profile_path")
expected_controls=$(awk '$1 == "wait" {n += 1} END {print n + 0}' "$profile_path")
min_measurement_seconds=$((profile_seconds - 8)); (( min_measurement_seconds > 5 )) || min_measurement_seconds=5
tag="${algorithm}__${profile_name}__d${delay_ms}__r${rep}"
[[ -z "$video_id" ]] || tag="${tag}__v${video_id}"
summary="$out_host/$tag.json"
sender_config="$out_host/config_sender_$tag.json"
receiver_config="$out_host/config_receiver_$tag.json"
decoded_video="$out_host/decoded_$tag.y4m"
decoded_timestamps="$out_host/decoded_timestamps_$tag.csv"
decoded_timestamps_summary="$out_host/decoded_timestamps_summary_$tag.json"
decoded_monitor_log="$out_host/decoded_monitor_$tag.log"
source_frame_timestamps="$out_host/source_frame_timestamps_$tag.csv"
sink_frame_timestamps="$out_host/sink_frame_timestamps_$tag.csv"
sink_frame_timestamps_generated="$decoded_video.timestamps.csv"
decoded_strace="$out_host/decoded_strace_$tag.log"
sink_uprobe_log="$out_host/sink_uprobe_$tag.log"
sink_uprobe_state="$out_host/sink_uprobe_state_$tag.json"
link_record="$out_host/link_$tag.txt"
cpu_record="$out_host/cpu_$tag.jsonl"
comp_sender_config="$out_host/config_comp_sender_$tag.json"
comp_receiver_config="$out_host/config_comp_receiver_$tag.json"
run_artifacts=(
  "$out_host/decision_$tag.jsonl"
  "$out_host/network_$tag.log"
  "$out_host/recv_$tag.log"
  "$out_host/send_$tag.log"
  "$out_host/control_$tag.log"
  "$out_host/shape_$tag.log"
  "$sender_config"
  "$receiver_config"
  "$summary"
  "$out_host/async_$tag.jsonl"
)
[[ -z "$competitor" ]] || run_artifacts+=("$out_host/comp_shape_$tag.log")
[[ "$competitor" != tcp ]] || run_artifacts+=("$out_host/bg_tcp_send_$tag.jsonl" "$out_host/bg_tcp_recv_$tag.jsonl")
[[ "$competitor" != gcc ]] || run_artifacts+=("$comp_sender_config" "$comp_receiver_config" "$out_host/comp_network_$tag.log" "$out_host/comp_decision_$tag.jsonl" "$out_host/comp_recv_$tag.log" "$out_host/comp_send_$tag.log")
if [[ "$capture_media" == 1 ]]; then
  run_artifacts+=("$decoded_video" "$decoded_timestamps" "$decoded_timestamps_summary" "$decoded_monitor_log")
  [[ "$strace_media" == 1 ]] && run_artifacts+=("$decoded_strace")
  [[ "$uprobe_sink" == 1 ]] && run_artifacts+=("$sink_uprobe_log" "$sink_uprobe_state")
fi
if [[ "$capture_frame_ids" == 1 ]]; then
  run_artifacts+=("$source_frame_timestamps" "$sink_frame_timestamps" "$sink_frame_timestamps_generated")
fi

mkdir -p "$out_host" "$app_host/logging" "$app_host/staleness_profiles"
docker exec "$receiver_container" mkdir -p "$out_app"
docker exec "$receiver_container" chmod 0777 "$out_app" /app/logging
[[ -s "$summary" ]] && { echo "skip completed $tag"; exit 0; }
for c in "$receiver_container" "$sender_container"; do
  if docker exec "$c" pgrep -f '[p]eerconnection_serverless .*_staleness' >/dev/null 2>&1; then
    echo "refusing to overlap peerconnection process in $c" >&2; exit 3
  fi
done

[[ -e "$app_host/BandwidthEstimator.py.pre_staleness" ]] || cp "$app_host/BandwidthEstimator.py" "$app_host/BandwidthEstimator.py.pre_staleness"
install -m 0644 "$repo/scripts/alphartc/BandwidthEstimator_staleness_v17.py" "$app_host/BandwidthEstimator.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_x_v1.py" "$app_host/estimator/online_llm_arms_x_v1.py"
install -m 0644 "$repo/scripts/alphartc/delay_wrapper.py" "$app_host/delay_wrapper.py"
install -m 0644 "$repo/scripts/alphartc/async_infer_v1.py" "$app_host/async_infer_v1.py"
install -m 0644 "$repo/scripts/alphartc/fixed_bandwidth_estimator.py" "$app_host/fixed_bandwidth_estimator.py"
install -m 0644 "$repo/scripts/alphartc/eval_staleness_run.py" "$app_host/eval_staleness_run.py"
install -m 0644 "$repo/scripts/alphartc/validate_staleness_run.py" "$app_host/validate_staleness_run.py"
install -m 0644 "$repo/scripts/alphartc/cmdinfer.py" "$app_host/cmdinfer.py"
install -m 0644 "$repo/scripts/alphartc/deploy/spec_collector.py" "$app_host/estimator/spec_collector.py"
install -m 0644 "$repo/scripts/alphartc/deploy/switcher.py" "$app_host/estimator/switcher.py"
install -m 0644 "$repo/scripts/alphartc/deploy/spec_collector_v4.py" "$app_host/estimator/spec_collector_v4.py"
install -m 0644 "$repo/scripts/alphartc/deploy/spec_collector_v5.py" "$app_host/estimator/spec_collector_v5.py"
install -m 0644 "$repo/scripts/alphartc/deploy/safety_envelope.py" "$app_host/estimator/safety_envelope.py"
install -m 0644 "$repo/scripts/alphartc/deploy/safety_envelope_v3.py" "$app_host/estimator/safety_envelope_v3.py"
install -m 0644 "$repo/scripts/alphartc/deploy/safety_envelope_v4.py" "$app_host/estimator/safety_envelope_v4.py"
install -m 0644 "$repo/scripts/alphartc/deploy/llm_switcher_v1.py" "$app_host/estimator/llm_switcher_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/llm_switch_worker_v1.py" "$app_host/estimator/llm_switch_worker_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_v1.py" "$app_host/estimator/online_llm_arms_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_conference_arm_v1.py" "$app_host/estimator/online_conference_arm_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/bg_udp_flow_v1.py" "$app_host/bg_udp_flow_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/bg_tcp_flow_v1.py" "$app_host/bg_tcp_flow_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/switcher_gcc_guard_v1.py" "$app_host/estimator/switcher_gcc_guard_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/spec_collector_v6.py" "$app_host/estimator/spec_collector_v6.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_v3.py" "$app_host/estimator/online_llm_arms_v3.py"
install -m 0644 "$repo/scripts/alphartc/deploy/switcher_x_v1.py" "$app_host/estimator/switcher_x_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_x_v1.py" "$app_host/estimator/fixed_x_v1.py"   # closedloop-envelope-attribution-v1
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_x_v2.py" "$app_host/estimator/fixed_x_v2.py"
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_schema_ch_v1.py" "$app_host/estimator/fixed_schema_ch_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/safety_envelope_v5.py" "$app_host/estimator/safety_envelope_v5.py"
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_env_x_v1.py" "$app_host/estimator/fixed_env_x_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_repair_x_v1.py" "$app_host/estimator/fixed_repair_x_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_schema_x_v1.py" "$app_host/estimator/fixed_schema_x_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_schema_llm4bandpp_v1.py" "$app_host/estimator/fixed_schema_llm4bandpp_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_lambda_arms_v1.py" "$app_host/estimator/online_lambda_arms_v1.py"
install -m 0755 "$repo/scripts/alphartc/comcast_policy_udp.sh" "$app_host/comcast_policy_udp.sh"
install -m 0755 "$repo/scripts/alphartc/comcast_policy_udp_v2.sh" "$app_host/comcast_policy_udp_v2.sh"
install -m 0755 "$repo/scripts/alphartc/comcast_policy_tcpudp_v3.sh" "$app_host/comcast_policy_tcpudp_v3.sh"
install -m 0644 "$repo/scripts/alphartc/deploy/gcc_pt125_v1.py" "$app_host/estimator/gcc_pt125_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/gcc_pt125_c200_v1.py" "$app_host/estimator/gcc_pt125_c200_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/echo_x_v1.py" "$app_host/estimator/echo_x_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/safety_envelope_v6.py" "$app_host/estimator/safety_envelope_v6.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_v4.py" "$app_host/estimator/online_llm_arms_v4.py"
install -m 0644 "$repo/scripts/alphartc/deploy/echo_x_v2.py" "$app_host/estimator/echo_x_v2.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_v5.py" "$app_host/estimator/online_llm_arms_v5.py"
install -m 0644 "$repo/scripts/alphartc/deploy/nl_estimator_v1/nl_estimator_v1.py" "$app_host/estimator/nl_estimator_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/fixed_schema_nl_v1.py" "$app_host/estimator/fixed_schema_nl_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_v6.py" "$app_host/estimator/online_llm_arms_v6.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_v7.py" "$app_host/estimator/online_llm_arms_v7.py"
install -m 0644 "$repo/scripts/alphartc/deploy/online_llm_arms_v8.py" "$app_host/estimator/online_llm_arms_v8.py"
install -m 0644 "$repo/scripts/alphartc/deploy/spec_collector_v7.py" "$app_host/estimator/spec_collector_v7.py"
install -m 0644 "$repo/scripts/alphartc/deploy/ch_estimator_v1/ch_estimator_v1.py" "$app_host/estimator/ch_estimator_v1.py"
install -d -m 0755 "$app_host/model/ch_v1"
install -m 0644 "$repo/scripts/alphartc/deploy/ch_estimator_v1/ckpt/ch.pt" "$app_host/model/ch_v1/ch.pt"
install -m 0644 "$repo/scripts/alphartc/deploy/ch_estimator_v1/ckpt/ch_s0.pt" "$app_host/model/ch_v1/ch_s0.pt"
install -m 0644 "$repo/scripts/alphartc/deploy/ch_estimator_v1/ckpt/ch_s2.pt" "$app_host/model/ch_v1/ch_s2.pt"
install -m 0644 "$repo/scripts/alphartc/deploy/ch_estimator_v1/ckpt/ch_l08s1.pt" "$app_host/model/ch_v1/ch_l08s1.pt"
hb_env=""
if [[ "${STALENESS_HIGH_BITRATE:-0}" == 1 ]]; then
  echo "1ff185744a306df642f716201c89edeecfee865613ee91859e4d7d5df1c1d5ea  /path/to/testbed/hb_v1/peerconnection_serverless.origin" | sha256sum -c --quiet - || { echo "patched binary hash mismatch" >&2; exit 2; }
  install -d -m 0755 "$app_host/hb"; install -m 0755 /path/to/testbed/hb_v1/peerconnection_serverless.origin "$app_host/hb/peerconnection_serverless.origin"
  hb_env='PATH=/app/hb:$PATH'
fi
install -d -m 0755 "$app_host/model/nl_v1"
install -m 0644 "$repo/scripts/alphartc/deploy/nl_estimator_v1/ckpt/NLs1/checkpoint_50000.pt" "$app_host/model/nl_v1/nl_s1.pt"
install -m 0644 "$repo/scripts/alphartc/deploy/adapt_x_v1.py" "$app_host/estimator/adapt_x_v1.py"
install -m 0644 "$repo/scripts/alphartc/deploy/adapt_mlp_np_v1.py" "$app_host/estimator/adapt_mlp_np_v1.py"
inject_files=()
restore_inject() {
  local rel
  for rel in "${inject_files[@]}"; do
    if [[ -e "$app_host/$rel.pre_inject_$$" ]]; then mv -f "$app_host/$rel.pre_inject_$$" "$app_host/$rel"; else rm -f "$app_host/$rel"; fi
  done
  [[ ${#inject_files[@]} -eq 0 ]] || { [[ -z "${inject_orig_sha:-}" ]] || (cd "$app_host" && echo "$inject_orig_sha" | sha256sum -c --quiet -) || echo "restored files do not match their hashes before injection" >&2; }
  inject_files=()
}
if [[ -n "${STALENESS_INJECT_DIR:-}" ]]; then
  while IFS= read -r -d '' f; do
    rel=${f#"$STALENESS_INJECT_DIR"/}; inject_files+=("$rel")
    [[ -e "$app_host/$rel" ]] && cp -p "$app_host/$rel" "$app_host/$rel.pre_inject_$$"
  done < <(find "$STALENESS_INJECT_DIR" -type f -print0)
  inject_orig_sha=$(cd "$app_host" && for rel in "${inject_files[@]}"; do [[ -e "$rel" ]] && sha256sum "$rel"; done)
  trap restore_inject EXIT INT TERM
  for rel in "${inject_files[@]}"; do
    install -m 0644 "$STALENESS_INJECT_DIR/$rel" "$app_host/$rel"; [[ "$rel" != *.sh ]] || chmod 0755 "$app_host/$rel"
  done
  mkdir -p "$out_host"; (cd "$app_host" && sha256sum "${inject_files[@]}") > "$out_host/inject_${algorithm}__$(basename "$2" .profile)__d${3}__r${4}.sha256"
fi
adapt_model_host="$app_host/${STALENESS_ADAPT_MODEL#/app/}"; [[ -n "${STALENESS_ADAPT_MODEL:-}" ]] || adapt_model_host="$app_host/model/adapt_v1/adapt_mlp.npz"
[[ "$algorithm" != adapt_x ]] || [[ -s "$adapt_model_host" ]] || { echo "adapt_x weights missing: $adapt_model_host" >&2; exit 3; }
policy_script=comcast_policy_udp.sh
[[ "${STALENESS_POLICY:-}" != v2 ]] || policy_script=comcast_policy_udp_v2.sh
[[ "${STALENESS_POLICY:-}" != v3 ]] || policy_script=comcast_policy_tcpudp_v3.sh
[[ "$competitor" != tcp || "$policy_script" == comcast_policy_tcpudp_v3.sh ]] || { echo "competitor tcp needs STALENESS_POLICY=v3" >&2; exit 2; }
install -m 0644 "$profile_path" "$app_host/staleness_profiles/$profile_name.profile"
receiver_ip=$(docker inspect "$receiver_container" --format "{{(index .NetworkSettings.Networks \"$network\").IPAddress}}")
docker exec "$sender_container" ip -d link show eth0 > "$link_record" 2>&1
if [[ -n "$require_gso_segs" ]]; then
  got_segs=$(awk '{for (i = 1; i < NF; i++) if ($i == "gso_max_segs") print $(i + 1)}' "$link_record" | head -n 1)
  [[ "$got_segs" == "$require_gso_segs" ]] || { echo "sender gso_max_segs=$got_segs, required $require_gso_segs" >&2; exit 7; }
fi

rm -f "$app_host/logging/staleness.log" "${run_artifacts[@]}"
if [[ "$competitor" == gcc ]]; then
  python3 "$repo/scripts/alphartc/build_staleness_configs.py" \
    --sender-template "$repo/scripts/alphartc/sender_staleness.json" \
    --receiver-template "$repo/scripts/alphartc/receiver_staleness.json" \
    --receiver-ip "$receiver_ip" --source-file "$comp_source" \
    --fps "$source_fps" --width "$source_width" --height "$source_height" \
    --capture-media 0 --decoded-video "$out_app/comp_unused.y4m" \
    --sender-out "$comp_sender_config" --receiver-out "$comp_receiver_config"
  python3 - "$comp_sender_config" "$comp_receiver_config" "$((comp_stop_s - comp_start_s + 4))" "$out_app/comp_network_$tag.log" <<'PYCOMP'
import json, sys
s_path, r_path, autoclose, netlog = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
s = json.load(open(s_path)); r = json.load(open(r_path))
s["serverless_connection"]["sender"]["dest_port"] = 8001; r["serverless_connection"]["receiver"]["listening_port"] = 8001
for c in (s, r): c["serverless_connection"]["autoclose"] = autoclose
r["logging"] = {"enabled": True, "log_output_path": netlog}
json.dump(s, open(s_path, "w"), indent=2, sort_keys=True); json.dump(r, open(r_path, "w"), indent=2, sort_keys=True)
PYCOMP
fi
python3 "$repo/scripts/alphartc/build_staleness_configs.py" \
  --sender-template "$repo/scripts/alphartc/sender_staleness.json" \
  --receiver-template "$repo/scripts/alphartc/receiver_staleness.json" \
  --receiver-ip "$receiver_ip" --source-file "$source_file" \
  --fps "$source_fps" --width "$source_width" --height "$source_height" \
  --capture-media "$capture_media" --decoded-video "$out_app/$(basename "$decoded_video")" \
  --sender-out "$sender_config" --receiver-out "$receiver_config"
if (( control_slack_s > 0 )); then
  python3 - "$sender_config" "$receiver_config" "$control_slack_s" <<'PYAUTOCLOSE'
import json, sys
slack = int(sys.argv[3])
for path in sys.argv[1:3]:
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    conn = cfg["serverless_connection"]
    conn["autoclose"] = int(conn["autoclose"]) + slack
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2, sort_keys=True)
PYAUTOCLOSE
fi
if [[ -n "$bwe_feedback_ms" ]]; then
  [[ "$bwe_feedback_ms" =~ ^[0-9]+$ ]] || exit 2
  python3 - "$sender_config" "$receiver_config" "$bwe_feedback_ms" <<'PYFEEDBACK'
import json, sys
ms = int(sys.argv[3])
for path in sys.argv[1:3]:
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    cfg["bwe_feedback_duration"] = ms
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2, sort_keys=True)
PYFEEDBACK
fi
if [[ "$sender_logging" == 1 ]]; then
  python3 - "$sender_config" "$out_app/senderwebrtc_$tag.log" <<'PYSENDLOG'
import json, sys
path, logpath = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as handle:
    cfg = json.load(handle)
cfg["logging"] = {"enabled": True, "log_output_path": logpath}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(cfg, handle, indent=2, sort_keys=True)
PYSENDLOG
fi
sender_config_app="$out_app/$(basename "$sender_config")"
receiver_config_app="$out_app/$(basename "$receiver_config")"
obs_trace_env=""
[[ "${STALENESS_OBS_TRACE:-0}" != 1 ]] || obs_trace_env="BWE_OBS_TRACE='$out_app/obs_$tag.jsonl'"
collector_env=""
[[ -z "${STALENESS_COLLECTOR:-}" ]] || collector_env="BWE_COLLECTOR='${STALENESS_COLLECTOR}'"
[[ -z "${STALENESS_STARTUP_GUARD:-}" ]] || collector_env="$collector_env BWE_STARTUP_GUARD='${STALENESS_STARTUP_GUARD}'"
[[ -z "${STALENESS_MIN_BPS_FLOOR:-}" ]] || collector_env="$collector_env BWE_MIN_BPS_FLOOR='${STALENESS_MIN_BPS_FLOOR}'"
[[ -z "${STALENESS_CH_CHECKPOINT:-}" ]] || collector_env="$collector_env BWE_CH_CHECKPOINT='${STALENESS_CH_CHECKPOINT}'"
[[ "${STALENESS_ENVELOPE:-0}" != 1 ]] || collector_env="$collector_env BWE_ENVELOPE=1"
[[ "${STALENESS_ENVELOPE:-0}" != 3 ]] || collector_env="$collector_env BWE_ENVELOPE=3"
[[ "${STALENESS_ENVELOPE:-0}" != 4 ]] || collector_env="$collector_env BWE_ENVELOPE=4"
[[ "${STALENESS_ENVELOPE:-0}" != 6 ]] || collector_env="$collector_env BWE_ENVELOPE=6"
[[ -z "${STALENESS_SWITCH_MODEL_DIR:-}" ]] || collector_env="$collector_env BWE_SWITCH_MODEL_DIR='${STALENESS_SWITCH_MODEL_DIR}'"
[[ -z "${STALENESS_LLM_SWITCH_DIR:-}" ]] || collector_env="$collector_env BWE_LLM_SWITCH_DIR='${STALENESS_LLM_SWITCH_DIR}'"
[[ -z "${STALENESS_ADAPT_MODEL:-}" ]] || collector_env="$collector_env BWE_ADAPT_MODEL='${STALENESS_ADAPT_MODEL}'"
[[ -z "${STALENESS_ENVELOPE_PARAMS:-}" ]] || collector_env="$collector_env BWE_ENVELOPE_PARAMS='${STALENESS_ENVELOPE_PARAMS}'"
[[ -z "${STALENESS_OBS_FAULT:-}" ]] || collector_env="$collector_env BWE_OBS_FAULT='${STALENESS_OBS_FAULT}'"
[[ -z "${STALENESS_OBS_REPAIR:-}" ]] || collector_env="$collector_env BWE_OBS_REPAIR='${STALENESS_OBS_REPAIR}'"
[[ -z "${STALENESS_OBS_SCHEMA:-}" ]] || collector_env="$collector_env BWE_OBS_SCHEMA='${STALENESS_OBS_SCHEMA}'"
[[ -z "${STALENESS_OBS_MAP:-}" ]] || collector_env="$collector_env BWE_OBS_MAP='${STALENESS_OBS_MAP}'"
async_env=""
[[ -z "${STALENESS_ASYNC_DEADLINE_MS:-}" ]] || async_env="BWE_ASYNC_DEADLINE_MS='${STALENESS_ASYNC_DEADLINE_MS}'"
receiver_fixed_env=""
[[ -z "$receiver_fixed_bps" ]] || receiver_fixed_env="BWE_FIXED_BPS='$receiver_fixed_bps'"
receiver_pid=""; sender_pid=""; policy_pid=""; monitor_pid=""; uprobe_container=""; comp_receiver_pid=""; comp_sender_pid=""; cpu_pid=""
firewall_comment=bwe-staleness-no-tcp-ice
remove_tcp_ice_block() {
  for c in "$receiver_container" "$sender_container"; do
    docker exec "$c" iptables -D OUTPUT -p tcp -m conntrack --ctstate NEW ! --dport 8000 \
      -m comment --comment "$firewall_comment" -j REJECT >/dev/null 2>&1 || true
    docker exec "$c" iptables -D INPUT -p tcp -m conntrack --ctstate NEW ! --dport 8000 \
      -m comment --comment "$firewall_comment" -j REJECT >/dev/null 2>&1 || true
    for port in 8001 5201; do for ch in OUTPUT INPUT; do
      docker exec "$c" iptables -D "$ch" -p tcp -m conntrack --ctstate NEW --dport "$port" \
        -m comment --comment "$firewall_comment" -j ACCEPT >/dev/null 2>&1 || true
    done; done
  done
}
remove_tcp_classify() {
  docker exec "$sender_container" bash -c 'while iptables -t mangle -D POSTROUTING -p tcp --dport 5201 -j CLASSIFY --set-class 10:10 2>/dev/null; do :; done' >/dev/null 2>&1 || true
}
cleanup() {
  [[ -z "$monitor_pid" ]] || kill -TERM "$monitor_pid" >/dev/null 2>&1 || true
  [[ -z "$policy_pid" ]] || docker exec "$sender_container" bash -c "kill -TERM -- -$policy_pid" >/dev/null 2>&1 || true
  [[ -z "$sender_pid" ]] || docker exec "$sender_container" bash -c "kill -TERM -- -$sender_pid" >/dev/null 2>&1 || true
  [[ -z "$receiver_pid" ]] || docker exec "$receiver_container" bash -c "kill -TERM -- -$receiver_pid" >/dev/null 2>&1 || true
  [[ -z "$uprobe_container" ]] || docker stop --time 1 "$uprobe_container" >/dev/null 2>&1 || true
  [[ -z "$comp_sender_pid" ]] || docker exec "$sender_container" bash -c "kill -TERM -- -$comp_sender_pid" >/dev/null 2>&1 || true
  [[ -z "$comp_receiver_pid" ]] || docker exec "$receiver_container" bash -c "kill -TERM -- -$comp_receiver_pid" >/dev/null 2>&1 || true
  [[ "$competitor" != tcp ]] || { docker exec "$sender_container" pkill -f '[b]g_tcp_flow_v1.py send' >/dev/null 2>&1 || true; docker exec "$receiver_container" pkill -f '[b]g_tcp_flow_v1.py sink' >/dev/null 2>&1 || true; }
  [[ -z "$cpu_pid" ]] || kill -TERM "$cpu_pid" >/dev/null 2>&1 || true
  docker exec "$sender_container" /root/go/bin/comcast --device eth0 --stop >/dev/null 2>&1 || true
  remove_tcp_classify
  remove_tcp_ice_block
}
trap 'cleanup; restore_inject' EXIT INT TERM

docker exec "$sender_container" /root/go/bin/comcast --device eth0 --stop >/dev/null 2>&1 || true
remove_tcp_ice_block
# Keep the TCP:8000 signaling flow, but prevent a congested UDP media path from
# escaping the experiment through a newly created TCP ICE candidate.
remove_tcp_classify
for c in "$receiver_container" "$sender_container"; do
  docker exec "$c" iptables -I OUTPUT 1 -p tcp -m conntrack --ctstate NEW ! --dport 8000 \
    -m comment --comment "$firewall_comment" -j REJECT
  docker exec "$c" iptables -I INPUT 1 -p tcp -m conntrack --ctstate NEW ! --dport 8000 \
    -m comment --comment "$firewall_comment" -j REJECT
  if [[ -n "$competitor" ]]; then
    for port in 8001 5201; do for ch in OUTPUT INPUT; do
      docker exec "$c" iptables -I "$ch" 1 -p tcp -m conntrack --ctstate NEW --dport "$port" \
        -m comment --comment "$firewall_comment" -j ACCEPT
    done; done
  fi
done
if [[ "$capture_media" == 1 ]]; then
  python3 "$repo/scripts/alphartc/monitor_decoded_yuv_v2.py" \
    --path "$decoded_video" --out-csv "$decoded_timestamps" \
    --out-json "$decoded_timestamps_summary" --poll-interval-ms "$monitor_poll_ms" \
    --capture-format y4m --width "$source_width" --height "$source_height" \
    > "$decoded_monitor_log" 2>&1 &
  monitor_pid=$!
fi
python3 "$repo/scripts/alphartc/deploy/cpu_role_sampler_v1.py" "$tag" "$cpu_record" "$((profile_seconds + control_slack_s + 30))" > /dev/null 2>&1 &
cpu_pid=$!
receiver_command="peerconnection_serverless '$receiver_config_app'"
if [[ "$capture_media" == 1 && "$strace_media" == 1 ]]; then
  receiver_command="strace -f -ttt -T -y -e trace=write,writev,pwrite64 -P '$out_app/$(basename "$decoded_video")' -o '$out_app/$(basename "$decoded_strace")' $receiver_command"
fi
receiver_pid=$(docker exec "$receiver_container" bash -lc \
  "cd /app; BWE_ESTIMATOR='$algorithm' BWE_LAMBDA_CKPT='${STALENESS_LAMBDA_CKPT:-}' BWE_DELAY_MS='$delay_ms' BWE_DELAY_TRACE='$out_app/decision_$tag.jsonl' BWE_ASYNC_TRACE='$out_app/async_$tag.jsonl' $async_env $receiver_fixed_env $obs_trace_env $collector_env BWE_TORCH_THREADS=4 $hb_env nohup setsid $receiver_command > '$out_app/recv_$tag.log' 2>&1 < /dev/null & echo \$!")
if [[ "$capture_media" == 1 && "$uprobe_sink" == 1 ]]; then
  uprobe_container="alphartc-sink-${tag//_/-}"
  python3 "$repo/scripts/alphartc/start_sink_uprobe.py" \
    --config-fragment "$(basename "$receiver_config")" \
    --container-name "$uprobe_container" \
    --out-log "$sink_uprobe_log" --out-state "$sink_uprobe_state" \
    --symbol-role "$uprobe_symbol_role" --probe-set "$uprobe_probe_set"
fi
sleep 2
sender_timestamp_env=""
if [[ "$capture_frame_ids" == 1 ]]; then
  sender_timestamp_env="ALPHARTC_SOURCE_TIMESTAMPS='$out_app/$(basename "$source_frame_timestamps")'"
fi
sender_bwe_env=""
if [[ -n "$sender_estimator" ]]; then
  sender_bwe_env="BWE_ESTIMATOR='$sender_estimator'"
  [[ -z "$sender_fixed_bps" ]] || sender_bwe_env="$sender_bwe_env BWE_FIXED_BPS='$sender_fixed_bps'"
fi
sender_pid=$(docker exec "$sender_container" bash -lc \
  "cd /app; $sender_bwe_env $sender_timestamp_env $hb_env nohup setsid timeout --kill-after=2s '$((profile_seconds + 10 + control_slack_s))s' peerconnection_serverless '$sender_config_app' > '$out_app/send_$tag.log' 2>&1 < /dev/null & echo \$!")
# Let ICE/DTLS establish on an unshaped path, then start the one-way profile.
sleep 4
policy_tcp_env=""
[[ "$competitor" != tcp ]] || policy_tcp_env="COMCAST_TCP_PORT=5201"
policy_t0=$(date +%s.%N)
policy_pid=$(docker exec "$sender_container" bash -lc \
  "cd /app; COMCAST_LOOP=0 COMCAST_DEVICE=eth0 COMCAST_QUEUE_PACKETS='$queue_packets' $policy_tcp_env nohup setsid bash $policy_script '/app/staleness_profiles/$profile_name.profile' > '$out_app/control_$tag.log' 2>&1 < /dev/null & echo \$!")
sleep_until_rel() {
  local rem; rem=$(awk -v t0="$policy_t0" -v rel="$1" -v now="$(date +%s.%N)" 'BEGIN { r = t0 + rel - now; if (r < 0) r = 0; printf "%.3f", r }')
  sleep "$rem"
}
comp_snapshot() {
  docker exec "$sender_container" bash -lc \
    "{ date +%s%3N; tc -s qdisc show dev eth0; tc -s class show dev eth0; iptables -t mangle -vnxL POSTROUTING; } > '$out_app/comp_shape_$tag.log' 2>&1"
}
if [[ "$competitor" == tcp ]]; then
  docker exec -d "$receiver_container" python3 /app/bg_tcp_flow_v1.py sink 5201 "$((profile_seconds + control_slack_s))" "$out_app/bg_tcp_recv_$tag.jsonl"
  docker exec -d "$sender_container" python3 /app/bg_tcp_flow_v1.py send "$receiver_ip" 5201 "$comp_start_s" "$comp_stop_s" "$out_app/bg_tcp_send_$tag.jsonl" cubic
fi
if [[ -n "$bg_kbps" ]]; then
  docker exec -d "$receiver_container" python3 /app/bg_udp_flow_v1.py sink 39217 "$((profile_seconds + control_slack_s))" "$out_app/bg_recv_$tag.jsonl"
  docker exec -d "$sender_container" python3 /app/bg_udp_flow_v1.py send "$receiver_ip" 39217 "$bg_kbps" "$bg_start_s" "$bg_stop_s" "$out_app/bg_send_$tag.jsonl"
fi
if [[ "$competitor" == gcc ]]; then
  sleep_until_rel "$((comp_start_s - 2))"
  comp_receiver_pid=$(docker exec "$receiver_container" bash -lc \
    "cd /app; BWE_ESTIMATOR='$comp_estimator' BWE_DELAY_MS=0 BWE_DELAY_TRACE='$out_app/comp_decision_$tag.jsonl' BWE_TORCH_THREADS=1 nohup setsid peerconnection_serverless '$out_app/$(basename "$comp_receiver_config")' > '$out_app/comp_recv_$tag.log' 2>&1 < /dev/null & echo \$!")
  sleep_until_rel "$comp_start_s"
  comp_sender_pid=$(docker exec "$sender_container" bash -lc \
    "cd /app; nohup setsid timeout --kill-after=2s '$((comp_stop_s - comp_start_s + 6))s' peerconnection_serverless '$out_app/$(basename "$comp_sender_config")' > '$out_app/comp_send_$tag.log' 2>&1 < /dev/null & echo \$!")
fi
if [[ -n "$competitor" ]]; then
  sleep_until_rel "$((comp_stop_s - 1))"
  comp_snapshot
  sleep_until_rel "$profile_seconds"
else
  sleep "$profile_seconds"
fi
docker exec "$sender_container" bash -lc \
  "{ tc -s qdisc show dev eth0; tc -s class show dev eth0; iptables -t mangle -vnL; } > '$out_app/shape_$tag.log' 2>&1"
waited_s=0
while (( waited_s < control_slack_s )); do
  docker exec "$sender_container" pgrep -f "[p]eerconnection_serverless .*config_sender_$tag" >/dev/null 2>&1 || \
    docker exec "$receiver_container" pgrep -f "[p]eerconnection_serverless .*config_receiver_$tag" >/dev/null 2>&1 || break
  sleep 2; waited_s=$((waited_s + 2))
done
echo "v10 call exit wait ${waited_s}s of slack ${control_slack_s}s"
docker exec "$sender_container" bash -c "kill -TERM -- -$sender_pid" >/dev/null 2>&1 || true
docker exec "$receiver_container" bash -c "kill -TERM -- -$receiver_pid" >/dev/null 2>&1 || true
if [[ -n "$comp_sender_pid" ]]; then
  docker exec "$sender_container" bash -c "kill -TERM -- -$comp_sender_pid" >/dev/null 2>&1 || true
  docker exec "$receiver_container" bash -c "kill -TERM -- -$comp_receiver_pid" >/dev/null 2>&1 || true
  comp_sender_pid=""; comp_receiver_pid=""
fi
[[ -z "$cpu_pid" ]] || { kill -TERM "$cpu_pid" >/dev/null 2>&1 || true; wait "$cpu_pid" 2>/dev/null || true; cpu_pid=""; }
if [[ -n "$uprobe_container" ]]; then
  docker stop --time 1 "$uprobe_container" >/dev/null 2>&1 || true
  uprobe_container=""
fi
sleep 2
if [[ -n "$monitor_pid" ]]; then
  kill -INT "$monitor_pid" >/dev/null 2>&1 || true
  wait "$monitor_pid"
  monitor_pid=""
fi

if [[ "$capture_media" == 1 ]]; then
  [[ -s "$decoded_video" ]] || { echo "missing decoded video" >&2; exit 6; }
  decoded_frames=$(ffprobe -v error -count_frames -select_streams v:0 \
    -show_entries stream=nb_read_frames -of default=nw=1:nk=1 "$decoded_video")
  [[ "$decoded_frames" =~ ^[0-9]+$ ]] || { echo "cannot parse decoded Y4M" >&2; exit 6; }
  (( decoded_frames >= min_decoded_frames )) || {
    echo "decoded frames $decoded_frames below minimum $min_decoded_frames" >&2; exit 6;
  }
  [[ -s "$decoded_timestamps" && -s "$decoded_timestamps_summary" ]] || {
    echo "missing decoded file-growth timestamps" >&2; exit 6;
  }
fi
if [[ "$capture_frame_ids" == 1 ]]; then
  [[ -s "$source_frame_timestamps" ]] || { echo "missing sender source-frame timestamps" >&2; exit 6; }
  [[ -s "$sink_frame_timestamps_generated" ]] || { echo "missing receiver sink-frame timestamps" >&2; exit 6; }
  mv "$sink_frame_timestamps_generated" "$sink_frame_timestamps"
  sender_header=$(head -n 1 "$source_frame_timestamps")
  sink_header=$(head -n 1 "$sink_frame_timestamps")
  [[ "$sender_header" == "emitted_frame_index,capture_timestamp_us,ntp_time_ms" ]] || exit 6
  [[ "$sink_header" == "decoded_frame_index,sink_callback_us,write_complete_us,video_timestamp_us,rtp_timestamp,ntp_time_ms,width,height,write_ok" ]] || exit 6
fi

[[ -s "$app_host/logging/staleness.log" ]] || { echo "missing network log" >&2; exit 4; }
mv "$app_host/logging/staleness.log" "$out_host/network_$tag.log"
docker exec "$receiver_container" python3 /app/eval_staleness_run.py \
  --network-log "$out_app/network_$tag.log" --decision-trace "$out_app/decision_$tag.jsonl" \
  --control-log "$out_app/control_$tag.log" --warmup-s 2 --out "$out_app/$tag.json"
if ! docker exec "$receiver_container" python3 /app/validate_staleness_run.py "$out_app/$tag.json" \
    --expected-controls "$expected_controls" --min-duration-s "$min_measurement_seconds" \
    --transport-log "$out_app/network_$tag.log" --shape-log "$out_app/shape_$tag.log"; then
  stamp=$(date +%s)
  for artifact in "${run_artifacts[@]}"; do
    if [[ -e "$artifact" ]]; then
      mv "$artifact" "$out_host/invalid_${stamp}_$(basename "$artifact")"
    fi
  done
  echo "invalid run artifacts preserved with prefix invalid_$stamp" >&2
  exit 5
fi
gzip -f "$out_host/network_$tag.log"
hash_inputs=(
  "$app_host/BandwidthEstimator.py"
  "$app_host/delay_wrapper.py"
  "$app_host/async_infer_v1.py"
  "$app_host/fixed_bandwidth_estimator.py"
  "$app_host/eval_staleness_run.py"
  "$app_host/staleness_profiles/$profile_name.profile"
  "$source_host_path"
  "$app_host/$policy_script"
  "$app_host/bg_tcp_flow_v1.py"
)
[[ -z "$comp_source_host_path" ]] || hash_inputs+=("$comp_source_host_path")
if [[ "$algorithm" == qwen25_contextual ]]; then
  hash_inputs+=(
    "$qwen25_bundle/checkpoint_20000.pt"
    "$qwen25_bundle/training_estimator.py"
    "$qwen25_bundle/contextual_module.py"
    "$qwen25_bundle/online_contextual_qwen25.py"
    "$qwen25_bundle/manifest.json"
    "$qwen25_model/config.json"
    "$qwen25_model/model.safetensors"
  )
fi
if [[ "$algorithm" == switch_nn* || "$algorithm" == switch_llm || "$algorithm" == switch_llm_x || "$algorithm" == switch_gccguard || "$algorithm" == arm_* || "$algorithm" == echo_x || "$algorithm" == adapt_x ]]; then
  hash_inputs+=("$app_host/estimator/switcher.py" "$app_host/estimator/spec_collector.py" "$app_host/estimator/spec_collector_v4.py" "$app_host/estimator/spec_collector_v5.py" "$app_host/estimator/safety_envelope.py" "$app_host/estimator/safety_envelope_v3.py" "$app_host/estimator/safety_envelope_v4.py" "$app_host/estimator/llm_switcher_v1.py" "$app_host/estimator/llm_switch_worker_v1.py" "$app_host/estimator/online_llm_arms_v1.py" "$app_host/estimator/online_conference_arm_v1.py" "$app_host/estimator/switcher_gcc_guard_v1.py" "$app_host/estimator/spec_collector_v6.py" "$app_host/estimator/online_llm_arms_v3.py" "$app_host/estimator/switcher_x_v1.py" "$app_host/estimator/fixed_x_v1.py" "$app_host/estimator/online_lambda_arms_v1.py" "$app_host/estimator/online_llm_arms_x_v1.py" "$app_host/estimator/echo_x_v1.py" "$app_host/estimator/adapt_x_v1.py" "$app_host/estimator/adapt_mlp_np_v1.py" "$app_host/estimator/safety_envelope_v5.py" "$app_host/estimator/fixed_env_x_v1.py" "$app_host/estimator/fixed_repair_x_v1.py" "$app_host/estimator/fixed_schema_x_v1.py" "$app_host/estimator/fixed_schema_llm4bandpp_v1.py")
  hash_inputs+=("$app_host/estimator/safety_envelope_v6.py" "$app_host/estimator/online_llm_arms_v4.py" "$app_host/estimator/echo_x_v2.py" "$app_host/estimator/gcc.py" "$app_host/estimator/gcc_pt125_v1.py" "$app_host/estimator/gcc_pt125_c200_v1.py")
  hash_inputs+=("$app_host/estimator/online_llm_arms_v5.py" "$app_host/estimator/nl_estimator_v1.py" "$app_host/model/nl_v1/nl_s1.pt")
  hash_inputs+=("$app_host/estimator/fixed_schema_nl_v1.py")
  hash_inputs+=("$app_host/estimator/online_llm_arms_v6.py" "$app_host/estimator/ch_estimator_v1.py" "$app_host/model/ch_v1/ch.pt")
  hash_inputs+=("$app_host/model/ch_v1/ch_s0.pt" "$app_host/model/ch_v1/ch_s2.pt")
  hash_inputs+=("$app_host/model/ch_v1/ch_l08s1.pt")
  hash_inputs+=("$app_host/estimator/fixed_x_v2.py" "$app_host/model/switch_v1/schaferct_retrained.onnx" "$app_host/model/switch_v1/mlp_seed0.pt")
  hash_inputs+=("$app_host/estimator/fixed_schema_ch_v1.py" "$app_host/estimator/fixed_schema_nl_v1.py" "$app_host/estimator/fixed_schema_x_v1.py")
  hash_inputs+=("$app_host/estimator/online_llm_arms_v7.py" "$app_host/estimator/spec_collector_v7.py")
  hash_inputs+=("$app_host/estimator/online_llm_arms_v8.py")
[[ "$algorithm" != adapt_x ]] || hash_inputs+=("$adapt_model_host")
fi
[[ -z "$hb_env" ]] || hash_inputs+=("$app_host/hb/peerconnection_serverless.origin")
sha256sum "${hash_inputs[@]}" > "$out_host/code_$tag.sha256"
docker exec "$receiver_container" sha256sum \
  /usr/bin/peerconnection_serverless /usr/bin/peerconnection_serverless.origin \
  >> "$out_host/code_$tag.sha256"
echo "completed $tag (v25 competitor=${competitor:-none})"
