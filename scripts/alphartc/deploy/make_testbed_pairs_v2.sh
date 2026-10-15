#!/usr/bin/env bash
# Build N sender-receiver container pairs pN, each with its own /app directory, docker network and container names; run scripts v10 and later point to a pair through
# ALPHARTC_APP_HOST, ALPHARTC_RECEIVER_CONTAINER, ALPHARTC_SENDER_CONTAINER and ALPHARTC_NETWORK. Each pair's /app copies the small files of the shared app directory and links
# the large directories (model, testmedia, huggingface, real_trace_sources, metrics) back to it; the containers mount it read-only at the same path, so links resolve and stay read-only.
# Version 2: copy of v1 (not in this package) that gives the receiver container PYTHONPATH=/usr/lib/python3/dist-packages, as the original receiver had; without it a new receiver
# decided only once per call and the sender stopped (testbed-parallel-equiv-v1). Such a receiver is removed and recreated. Builds the pairs that parallel_testbed_v1.py and _v2.py use.
# Usage: bash make_testbed_pairs_v2.sh N
set -euo pipefail
N=${1:?Usage: make_testbed_pairs_v2.sh N}
SHARED=/path/to/alphartc/LLM4Band; BASE=/path/to/testbed; IMG=alphartc4band:latest
HEAVY=(model testmedia huggingface real_trace_sources metrics)
mkdir -p "$BASE"
for i in $(seq 1 "$N"); do
  d="$BASE/p$i"
  if [ ! -d "$d" ]; then
    mkdir -p "$d"
    rsync -a --exclude=/result --exclude=/logging --exclude=/__pycache__ $(printf -- '--exclude=/%s ' "${HEAVY[@]}") "$SHARED/" "$d/"
    mkdir -p "$d/result" "$d/logging"
    for h in "${HEAVY[@]}"; do ln -s "$SHARED/$h" "$d/$h"; done
  fi
  docker network inspect "bwe-p$i-net" >/dev/null 2>&1 || docker network create "bwe-p$i-net" >/dev/null
  for c in "alphartc4band-p$i" "alphartc-sender-p$i"; do
    envarg=(); [ "$c" = "alphartc4band-p$i" ] && envarg=(-e PYTHONPATH=/usr/lib/python3/dist-packages)
    if [ "$c" = "alphartc4band-p$i" ] && docker inspect "$c" >/dev/null 2>&1 && ! docker inspect -f '{{json .Config.Env}}' "$c" | grep -q 'PYTHONPATH=/usr/lib/python3/dist-packages'; then
      docker rm -f "$c" >/dev/null; echo "p$i receiver is missing PYTHONPATH, rebuild"
    fi
    if ! docker inspect "$c" >/dev/null 2>&1; then
      docker run -d --name "$c" --network "bwe-p$i-net" --cap-add NET_ADMIN "${envarg[@]}" -v "$d:/app" -v "$SHARED:$SHARED:ro" "$IMG" tail -f /dev/null >/dev/null
    fi
    [ "$(docker inspect -f '{{.State.Running}}' "$c")" = true ] || docker start "$c" >/dev/null
    docker exec "$c" test -s /app/model/adapt_v2/adapt_mlp.npz -a -s /app/testmedia/qoe_labeled_medium_320x240.yuv -a -x /usr/bin/peerconnection_serverless || { echo "p$i $c mount check failed" >&2; exit 1; }
    if docker exec "$c" touch "$SHARED/.write_probe_p$i" 2>/dev/null; then echo "p$i $c can actually write to the shared directory" >&2; exit 1; fi
  done
  echo "p$i ready: $d, network bwe-p$i-net, containers alphartc4band-p$i and alphartc-sender-p$i"
done
