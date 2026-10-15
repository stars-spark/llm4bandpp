#!/usr/bin/env bash
# Training and evaluation queue for ablation-nl-enc-hcq-2x2-v1 and ablation-nl-hcq-lowbw-v1 on a two-GPU server.
# PER_GPU workers per GPU take jobs in turn; a job starts only when its GPU has at least NEED_MIB free (it waits and never kills other processes).
# Each job trains 50,000 steps (same command as the reused NLs0 to NLs2 except --env, --seed and --reward_lambda 0.0 for the B cells),
# then evaluates the 870 calls on the same GPU and writes DONE_<tag>. Three evaluation-only jobs re-evaluate the reused NLs0 to NLs2 (void check).
# Before starting, checks the hashes of the M code directory and that the C directory matches it except for its generated estimator.py.
# Writes QUEUE_DONE at the end; a failed job writes FAIL_<tag> and the queue goes on.
# Usage: PER_GPU=N NEED_MIB=M bash run_nl2x2_v1.sh
set -uo pipefail
W=$HOME/work/work/nl_2x2_v1; M=$HOME/work/work/caiql_llm_screen_v2r1/nollm_mt_anchor; C=$W/conf
OUT=$HOME/work/outputs/nl_2x2_v1; EV=$OUT/eval; LOGS=$HOME/work/logs; PY=python3
EVAL=$HOME/work/work/llm_value/eval_value_per_file.py; SCEN=/path/to/challenge/solution/validation/prepare_scenario
PER_GPU=${PER_GPU:?workers per GPU}; NEED_MIB=${NEED_MIB:?free MiB a job needs}
mkdir -p $OUT $EV $LOGS; rm -f $OUT/QUEUE_DONE
# Expected sha256 prefixes of IQL.py, module.py, model.py, dualEncoder.py and estimator.py in the M directory.
want_m="f8c834926b790875 645ddc461220e508 c8dad8401fefb358 2b7bca18000ac8ec 62d0e5582fb3617d"
got_m=$(cd $M && for f in IQL.py module.py model.py dualEncoder.py estimator.py; do sha256sum $f | cut -c1-16; done | tr '\n' ' ')
[[ "${got_m% }" == "$want_m" ]] || { echo "M directory hash mismatch: $got_m" > $OUT/QUEUE_FAILED; exit 3; }
for f in IQL.py module.py model.py dualEncoder.py; do cmp -s $M/$f $C/$f || { echo "C directory $f differs from M" > $OUT/QUEUE_FAILED; exit 3; }; done
[[ $(sha256sum $C/estimator.py | cut -c1-16) == f78405de1d20dc68 ]] || { echo "C directory estimator.py hash mismatch" > $OUT/QUEUE_FAILED; exit 3; }
wait_free() { local g=$1 t=0; while :; do read -r u tt < <(nvidia-smi -i $g --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | tr ',' ' ');
  (( tt - u >= NEED_MIB )) && return 0; (( t >= 172800 )) && return 1; sleep 120; t=$((t+120)); done; }
evaluate() {
  $PY $EVAL --code-dir $1 --scen $SCEN --ckpt $2 --device cuda:$4 --chunk 256 --tag $3 --out $EV/$3.json > $LOGS/nl2x2_eval_$3.log 2>&1; }
job() {
  local cell=$1 s=$2 g=$3 d lam tag="$1s$2"
  [[ -f $OUT/DONE_$tag ]] && return 0
  if [[ $cell == REUSE ]]; then
    local ck=$(ls -d $HOME/work/outputs/llm_indispensability/IQL-lid-NLs$s-*/checkpoint_50000.pt | head -1)
    wait_free $g || { echo "timed out waiting for free GPU memory" > $OUT/FAIL_$tag; return; }
    evaluate $M $ck MHreuse_s$s $g && date -Is > $OUT/DONE_$tag || echo "evaluation failure" > $OUT/FAIL_$tag; return
  fi
  case $cell in MH|MB) d=$M;; CH|CB) d=$C;; esac; case $cell in *B) lam="--reward_lambda 0.0";; *) lam="";; esac
  wait_free $g || { echo "timed out waiting for free GPU memory" > $OUT/FAIL_$tag; return; }
  cd $d && $PY -u IQL.py --device cuda:$g --env nl2x2-$tag --max_timesteps 50000 --checkpoints_path $OUT --buffer_size 3500000 --eval_freq 5000 --seed $s $lam > $LOGS/nl2x2_train_$tag.log 2>&1
  local ck=$(ls -d $OUT/IQL-nl2x2-$tag-*/checkpoint_50000.pt 2>/dev/null | head -1)
  [[ -s "$ck" ]] || { echo "missing 50000-step checkpoint" > $OUT/FAIL_$tag; return; }
  evaluate $d $ck $tag $g && date -Is > $OUT/DONE_$tag || echo "evaluation failure" > $OUT/FAIL_$tag
}
# Seeds 0 to 4 for CB and MH (MH seeds 0 to 2 are reused), seeds 0 to 2 for CH and MB.
JOBS=(REUSE:0 REUSE:1 REUSE:2 CB:0 MH:3 CB:1 MH:4 CB:2 MB:0 CH:0 CB:3 MB:1 CH:1 CB:4 MB:2 CH:2)
nw=$((2 * PER_GPU)); for w in $(seq 0 $((nw - 1))); do
  ( g=$((w % 2)); i=$w; while (( i < ${#JOBS[@]} )); do j=${JOBS[$i]}; job ${j%%:*} ${j##*:} $g; i=$((i + nw)); sleep 5; done ) &
  sleep 40
done
wait
n=$(ls $OUT/DONE_* 2>/dev/null | wc -l); echo "{\"done\": $n, \"jobs\": ${#JOBS[@]}, \"t\": \"$(date -Is)\"}" > $OUT/QUEUE_DONE
