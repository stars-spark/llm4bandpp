#!/usr/bin/env bash
# Launcher of the 16 training runs of ablation-enc-hcq-2x2-v1 and ablation-hcq-lowbw-v1, one fixed queue per GPU.
# Usage: run_enc_hcq_2x2.sh formal <gpu> | smoke <gpu> <cell:seed>... | pair <gpu> <cell:seed> <cell:seed>
# (formal: the scheduled runs of this machine and GPU; smoke: 200 updates into the _smoke directory; pair: two runs at
# once on one GPU to measure memory and throughput). Cells CB, CH, MB, MH are C-B, C-H, M-B, M-H.
# A run starts only after the EVAL marker of the previous run, written by wait_eval_enc_hcq_2x2.py, exists; a failure stops
# the queue; nothing is rerun or overwritten automatically; the launcher waits for free GPU memory and never kills a process.
#
#
set -euo pipefail

W=/path/to/server/work/enc_hcq_2x2_v1
ARM=$W/arm
LOGS=/path/to/server/logs
CHAIN_DONE=/path/to/server/work/openreason_v1/CHAIN_DESIGNER_SCALE_DONE
NEED_MIB=${E2X2_NEED_MIB:-30000}
POLL=${E2X2_POLL:-120}

die() { echo "[$(date '+%m-%d %H:%M:%S')] stop: $*" >&2; exit 3; }
log() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

case "$(hostname)" in
  gpu-server-1)
    MACHINE=gpu-server-1
    PY=python3
    export BWE_PICKLE=/path/to/llm4band_conference/dataset/MRE_4.pickle
    export BWE_QWEN_DIR=/path/to/llm4band_conference/Qwen1.5-0.5B ;;
  gpu-server-2)
    MACHINE=gpu-server-2
    PY=/path/to/server/envs/llm4band_clone/bin/python
    export BWE_PICKLE=/path/to/challenge/solution/dataset/training_dataset_pickle/MRE/MRE_4.pickle
    export BWE_QWEN_DIR=/path/to/server/models/Qwen1.5-0.5B_copy ;;
  *) die "Unknown host $(hostname)" ;;
esac

sched() {
  case "$1:$2" in
    gpu-server-1:0)   echo "CB:0 MB:0 MH:2 CH:2" ;;
    gpu-server-1:1)   echo "MH:0 CH:0 CB:2 MB:2" ;;
    gpu-server-2:0) echo "CB:1 MB:1 MH:3 CB:4" ;;
    gpu-server-2:1) echo "MH:1 CH:1 CB:3 MH:4" ;;
    *) return 1 ;;
  esac
}

enc_of() { case "$1" in CB|CH) echo conf15 ;; MB|MH) echo ms15 ;; *) die "Unknown cell $1" ;; esac; }
lam_of() { case "$1" in CB|MB) echo 0.0 ;; CH|MH) echo 0.4 ;; *) die "Unknown cell $1" ;; esac; }

gpu_free_mib() {
  local u t
  read -r u t < <(nvidia-smi -i "$1" --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | tr ',' ' ')
  echo $(( t - u ))
}

wait_free() {
  local gpu=$1 need=$2 f
  while :; do
    f=$(gpu_free_mib "$gpu")
    [ "$f" -ge "$need" ] && return 0
    log "GPU $gpu idle $f MiB insufficient $need, waiting"
    sleep "$POLL"
  done
}

wait_chain_done() {
  [ "$MACHINE" = gpu-server-2 ] || return 0
  while [ ! -f "$CHAIN_DONE" ]; do
    log "the GPU on gpu-server-2 is reserved for the openreason_v1 chain, wait for $CHAIN_DONE to appear"
    sleep 300
  done
}

wait_eval_marker() {
  local tag=$1
  while :; do
    [ -f "$MARK/EVAL_${tag}_COMPLETE.json" ] && return 0
    [ -f "$MARK/EVAL_${tag}_FAILED" ] && die "$tag evaluation failed; queue stopped"
    [ -f "$MARK/TRAIN_${tag}_FAILED" ] && die "$tag training failed; queue stopped"
    sleep "$POLL"
  done
}

train_one() {
  local gpu=$1 cell=$2 seed=$3 prefix=$4 steps=$5 efreq=$6
  local tag="${cell}_s${seed}" rundir="$OUT/${cell}_s${seed}" logf="$LOGS/enc_hcq_2x2_v1${SUFFIX}_${cell}_s${seed}.log"
  [ -e "$rundir" ] && die "$rundir already exists without a completion marker, not overwriting"
  [ -e "$logf" ] && die "$logf already exists, not overwriting"
  mkdir -p "$rundir"
  log "started $tag on $MACHINE GPU $gpu, BWE_ENC=$(enc_of "$cell") BWE_REWARD_LAMBDA=$(lam_of "$cell"), $steps steps"
  local rc=0
  ( cd "$ARM" && BWE_ENC=$(enc_of "$cell") BWE_REWARD_LAMBDA=$(lam_of "$cell") \
      "$PY" -u IQL.py --device "cuda:$gpu" --env "${prefix}-${cell}-s${seed}" --seed "$seed" \
      --max_timesteps "$steps" --eval_freq "$efreq" --checkpoints_path "$rundir" \
      --buffer_size 3500000 ) > "$logf" 2>&1 || rc=$?
  local d n
  n=$(ls -d "$rundir"/IQL-* 2>/dev/null | wc -l)
  d=$(ls -d "$rundir"/IQL-* 2>/dev/null | head -1)
  if [ "$rc" -ne 0 ] || [ "$n" -ne 1 ] || [ ! -s "$d/checkpoint_${steps}.pt" ] || [ ! -s "$d/TRAIN_DONE.json" ]; then
    printf '{"tag":"%s","host":"%s","gpu":%s,"rc":%s,"log":"%s"}\n' "$tag" "$MACHINE" "$gpu" "$rc" "$logf" \
      > "$MARK/TRAIN_${tag}_FAILED"
    die "$tag training did not end normally (return code $rc, directory count $n), see $logf"
  fi
  printf '{"tag":"%s","cell":"%s","seed":%s,"host":"%s","gpu":%s,"run_dir":"%s","step":%s,"log":"%s","finished_at":"%s"}\n' \
    "$tag" "$cell" "$seed" "$MACHINE" "$gpu" "$d" "$steps" "$logf" "$(date -Is)" > "$MARK/TRAIN_${tag}_COMPLETE.tmp"
  mv "$MARK/TRAIN_${tag}_COMPLETE.tmp" "$MARK/TRAIN_${tag}_COMPLETE"
  log "$tag training complete, writing TRAIN marker, waiting for the watcher to evaluate"
}

run_queue() {
  local gpu=$1 prefix=$2 steps=$3 efreq=$4; shift 4
  local prev="" item cell seed tag
  for item in "$@"; do
    cell=${item%%:*}; seed=${item##*:}; tag="${cell}_s${seed}"
    if [ -n "$prev" ]; then wait_eval_marker "$prev"; fi
    if [ -f "$MARK/TRAIN_${tag}_COMPLETE" ]; then
      log "$tag already has the TRAIN marker, skipping training"
    else
      wait_free "$gpu" "$NEED_MIB"
      train_one "$gpu" "$cell" "$seed" "$prefix" "$steps" "$efreq"
    fi
    prev=$tag
  done
  [ -n "$prev" ] && wait_eval_marker "$prev"
  log "GPU $gpu queue all complete: $*"
}

mode=${1:-}; gpu=${2:-}
[[ "$gpu" =~ ^[01]$ ]] || die "GPU index must be 0 or 1"
[ -f "$ARM/IQL.py" ] || die "Missing $ARM/IQL.py"
"$PY" -m py_compile "$ARM/IQL.py" "$ARM/estimator.py" "$ARM/enc_hcq_2x2_encoders.py" "$ARM/enc_hcq_2x2_runtime.py"

case "$mode" in
  formal)
    OUT=/path/to/server/outputs/enc_hcq_2x2_v1; SUFFIX=""
    MARK=$OUT/markers; mkdir -p "$MARK" "$LOGS"
    items=$(sched "$MACHINE" "$gpu") || die "No $MACHINE GPU $gpu in the schedule"
    wait_chain_done
    # shellcheck disable=SC2086
    run_queue "$gpu" e2x2 50000 10000 $items ;;
  smoke)
    shift 2; [ $# -ge 1 ] || die "smoke test must give at least one cell:seed"
    OUT=/path/to/server/outputs/enc_hcq_2x2_v1_smoke; SUFFIX="_smoke"
    MARK=$OUT/markers; mkdir -p "$MARK" "$LOGS"
    [ "$MACHINE" = gpu-server-1 ] || wait_chain_done
    run_queue "$gpu" e2x2smk 200 100 "$@" ;;
  pair)
    shift 2; [ $# -eq 2 ] || die "pair gives exactly two cells:seed"
    OUT=/path/to/server/outputs/enc_hcq_2x2_v1_smoke/pair; SUFFIX="_smoke_pair"
    MARK=$OUT/markers; mkdir -p "$MARK" "$LOGS"
    [ "$MACHINE" = gpu-server-1 ] || wait_chain_done
    wait_free "$gpu" 30000
    smi="$OUT/smi_gpu${gpu}.csv"
    ( while :; do echo "$(date +%s),$(nvidia-smi -i "$gpu" --query-gpu=memory.used --format=csv,noheader,nounits)"; sleep 5; done ) > "$smi" &
    sp=$!
    c1=${3%%:*}; s1=${3##*:}; c2=${4%%:*}; s2=${4##*:}
    rc=0
    train_one "$gpu" "$c1" "$s1" e2x2pair 600 600 & p1=$!
    train_one "$gpu" "$c2" "$s2" e2x2pair 600 600 & p2=$!
    wait "$p1" || rc=1
    wait "$p2" || rc=1
    kill "$sp" 2>/dev/null || true
    log "Two runs on the same GPU finished, returned $rc, see $smi for GPU memory sampling"
    exit "$rc" ;;
  *) die "Mode must be formal, smoke, or pair" ;;
esac
