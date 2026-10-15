#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watcher of ablation-enc-hcq-2x2-v1, one per machine. For each run with a TRAIN marker and no evaluation yet, it exports
the per-step predictions on the 870 calls (20 in smoke mode) on the run's GPU and writes the EVAL marker that releases
the next run of that queue; a failure writes EVAL_<cell>_s<seed>_FAILED and stops the queue. In formal mode the first
server then exports the checkpoint of our earlier version, so that the judge can check 6.743 within 0.5%. The keys of the
EVAL marker are defined only here. Before evaluating, BWE_ENC and BWE_REWARD_LAMBDA in the run manifest must match the
cell and the code hashes must match the generation manifest; otherwise FAILED is written.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

W = Path("/path/to/server/work/enc_hcq_2x2_v1")
ARM = W / "arm"
DUMP = W / "dump_perstep_enc_hcq_2x2.py"
LOGS = Path("/path/to/server/logs")
EXPERIMENT = "ablation-enc-hcq-2x2-v1"
ENC = {"CB": "conf15", "CH": "conf15", "MB": "ms15", "MH": "ms15"}
LAM = {"CB": "0.0", "CH": "0.4", "MB": "0.0", "MH": "0.4"}
HOSTS = {"gpu-server-1": "gpu-server-1", "gpu-server-2": "gpu-server-2"}
CFG = {
    "gpu-server-1": {"py": "python3",
            "qwen": "/path/to/llm4band_conference/Qwen1.5-0.5B",
            "scen": "/path/to/llm4band_conference/validation/prepare_scenario"},
    "gpu-server-2": {"py": "/path/to/server/envs/llm4band_clone/bin/python",
              "qwen": "/path/to/server/models/Qwen1.5-0.5B_copy",
              "scen": "/path/to/challenge/solution/validation/prepare_scenario"},
}
PAPER_CODE = "/path/to/server/work/eval"
PAPER_CKPT = ("/path/to/llm4band_conference/Qwen_for_bwe/Qwen_LoRa/checkpoints_iql/"
              "IQL-qwen1.5lora-dual-MRE4-f6a2d3ee/actor_1240000.pt")


def log(m):
    print(f"[{dt.datetime.now():%m-%d %H:%M:%S}] {m}", flush=True)


def sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def gpu_free_mib(i: int) -> int:
    r = subprocess.run(["nvidia-smi", "-i", str(i), "--query-gpu=memory.used,memory.total",
                        "--format=csv,noheader,nounits"], text=True, capture_output=True)
    used, total = (int(x) for x in r.stdout.strip().split(","))
    return total - used


def write_json_atomic(p: Path, obj) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["formal", "smoke"])
    ap.add_argument("--expect", type=int, required=True, help="The runs that should be evaluated on this machine; exit once all are evaluated")
    ap.add_argument("--need-mib", type=int, default=8000)
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--curve", action="store_true",
                    help="After all primary evaluations are complete, export the intermediate checkpoints of each run (for training curves only; not used in the verdict)")
    a = ap.parse_args()
    machine = HOSTS[socket.gethostname()]
    cfg = CFG[machine]
    smoke = a.mode == "smoke"
    out = Path("/path/to/server/outputs/enc_hcq_2x2_v1" + ("_smoke" if smoke else ""))
    mark = out / "markers"
    evald = Path(str(out) + "_eval") if not smoke else out / "eval"
    evald.mkdir(parents=True, exist_ok=True)
    mark.mkdir(parents=True, exist_ok=True)
    arm_man = json.loads((W / "arm_manifest.json").read_text(encoding="utf-8"))["code_sha256"]
    env = dict(os.environ, BWE_QWEN_DIR=cfg["qwen"])
    env.pop("BWE_REWARD_LAMBDA", None)
    running = {}          # gpu -> (tag, Popen, train_marker, log, t0)
    log(f"{machine} watcher started, mode {a.mode}, expected {a.expect} runs, evaluation directory {evald}")

    def fail(tag, why):
        (mark / f"EVAL_{tag}_FAILED").write_text(
            json.dumps({"tag": tag, "host": machine, "why": why, "at": dt.datetime.now().isoformat()},
                       ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"{tag} evaluation failed: {why}")

    while True:
        for gpu, (tag, proc, t, lg, t0, npz) in list(running.items()):
            if proc.poll() is None:
                continue
            del running[gpu]
            if proc.returncode != 0 or not npz.exists():
                fail(tag, f"Export return code {proc.returncode}, see {lg}")
                continue
            info = json.loads(npz.with_suffix(".json").read_text(encoding="utf-8"))
            rd = Path(t["run_dir"])
            write_json_atomic(mark / f"EVAL_{tag}_COMPLETE.json", {
                "experiment": EXPERIMENT, "cell": t["cell"], "seed": t["seed"], "tag": tag,
                "host": machine, "gpu": gpu, "step": t["step"], "run_dir": str(rd),
                "checkpoint": str(rd / f"checkpoint_{t['step']}.pt"), "npz": str(npz),
                "npz_json": str(npz.with_suffix(".json")), "dump": info,
                "train_done": json.loads((rd / "TRAIN_DONE.json").read_text(encoding="utf-8")),
                "run_manifest": json.loads((rd / "enc_hcq_2x2_run.json").read_text(encoding="utf-8")),
                "code_sha256_now": {f: sha256(ARM / f) for f in arm_man},
                "evaluated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "eval_minutes": round((time.time() - t0) / 60, 1)})
            log(f"{tag} evaluation complete, {info['minutes']} minutes, per-scenario {info['mse_nanmean_by_scenario']}")
        mine = []
        for p in sorted(mark.glob("TRAIN_*_COMPLETE")):
            t = json.loads(p.read_text(encoding="utf-8"))
            if t["host"] == machine:
                mine.append(t)
        done = [t["tag"] for t in mine if (mark / f"EVAL_{t['tag']}_COMPLETE.json").exists()]
        failed = [t["tag"] for t in mine if (mark / f"EVAL_{t['tag']}_FAILED").exists()]
        for t in mine:
            tag, gpu = t["tag"], int(t["gpu"])
            if tag in done or tag in failed or gpu in running or \
                    any(v[0] == tag for v in running.values()):
                continue
            rd = Path(t["run_dir"])
            try:
                man = json.loads((rd / "enc_hcq_2x2_run.json").read_text(encoding="utf-8"))
            except OSError as e:
                fail(tag, f"Failed to read the run manifest {e}")
                continue
            cell = t["cell"]
            if man["cell"] != cell or man["BWE_ENC"] != ENC[cell] or man["BWE_REWARD_LAMBDA"] != LAM[cell] \
                    or int(man["seed"]) != int(t["seed"]):
                fail(tag, f"Run manifest does not match cell name: {man['cell']} {man['BWE_ENC']} {man['BWE_REWARD_LAMBDA']} seed {man['seed']}")
                continue
            if man["code_sha256"] != arm_man:
                fail(tag, "Runtime code hash does not match the generated manifest")
                continue
            if gpu_free_mib(gpu) < a.need_mib:
                log(f"{tag} pending evaluation, GPU {gpu} free memory insufficient {a.need_mib} MiB, waiting, not killing")
                continue
            npz = evald / f"{tag}_{t['step']}.npz"
            lg = LOGS / f"enc_hcq_2x2_v1{'_smoke' if smoke else ''}_eval_{tag}.log"
            if npz.exists():
                fail(tag, f"{npz} already exists, not overwriting")
                continue
            cmd = [cfg["py"], "-u", str(DUMP), "--code-dir", str(ARM),
                   "--ckpt", str(rd / f"checkpoint_{t['step']}.pt"), "--scen", cfg["scen"],
                   "--device", f"cuda:{gpu}", "--chunk", "512", "--out", str(npz)]
            if smoke:
                cmd += ["--limit", "20"]
            fh = open(lg, "w")
            proc = subprocess.Popen(cmd, env=dict(env, BWE_ENC=ENC[cell]), stdout=fh,
                                    stderr=subprocess.STDOUT, cwd=str(ARM))
            running[gpu] = (tag, proc, t, lg, time.time(), npz)
            log(f"{tag} starting evaluation on GPU {gpu}, log {lg}")
        if failed:
            log(f"Evaluation already failed: {failed}; the watcher continues processing the remaining runs")
        if len(done) + len(failed) >= a.expect and not running:
            break
        time.sleep(a.poll)

    if machine == "gpu-server-1" and not smoke and not failed:
        npz = evald / "paper_ckpt_1240000.npz"
        if not npz.exists():
            gpu = None
            while gpu is None:
                for i in (0, 1):
                    if gpu_free_mib(i) >= a.need_mib:
                        gpu = i
                        break
                else:
                    log("waiting for a GPU with enough free memory to re-export the earlier version's checkpoint (no process is killed)")
                    time.sleep(a.poll)
            lg = LOGS / "enc_hcq_2x2_v1_eval_paper_ckpt.log"
            with open(lg, "w") as fh:
                r = subprocess.run([cfg["py"], "-u", str(DUMP), "--code-dir", PAPER_CODE, "--ckpt", PAPER_CKPT,
                                    "--scen", cfg["scen"], "--device", f"cuda:{gpu}", "--chunk", "512",
                                    "--out", str(npz)], stdout=fh, stderr=subprocess.STDOUT, cwd=PAPER_CODE)
            if r.returncode != 0:
                (mark / "EVAL_PAPER_FAILED").write_text(f"See {lg}\n", encoding="utf-8")
                log("re-export of the checkpoint of the earlier version failed")
                return 1
        write_json_atomic(mark / "EVAL_PAPER_COMPLETE.json",
                          {"experiment": EXPERIMENT, "npz": str(npz),
                           "dump": json.loads(npz.with_suffix(".json").read_text(encoding="utf-8"))})
        log("re-export of the checkpoint of the earlier version completed")
    if a.curve and not failed:
        curve_pass(a, machine, cfg, mark, evald, env, smoke)
    log(f"{machine} watcher finished: completed {len(done)}, failed {len(failed)}")
    return 0 if not failed else 1


def curve_pass(a, machine, cfg, mark, evald, env, smoke):
    """Exports of the intermediate checkpoints, one at a time per GPU, on the run's GPU; existing exports are skipped."""
    cdir = evald / "curve"
    cdir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for p in sorted(mark.glob("TRAIN_*_COMPLETE")):
        t = json.loads(p.read_text(encoding="utf-8"))
        if t["host"] != machine:
            continue
        man = json.loads((Path(t["run_dir"]) / "enc_hcq_2x2_run.json").read_text(encoding="utf-8"))
        for st in range(int(man["eval_freq"]), int(t["step"]), int(man["eval_freq"])):
            jobs.append((int(t["gpu"]), t["tag"], t["cell"], st, Path(t["run_dir"]) / f"checkpoint_{st}.pt"))
    running, bad = {}, []
    while jobs or running:
        for gpu, (tag, st, proc, lg) in list(running.items()):
            if proc.poll() is not None:
                del running[gpu]
                if proc.returncode != 0:
                    bad.append(f"{tag}_{st}")
                    log(f"Failed to export curve point {tag} {st}, see {lg}")
        for job in list(jobs):
            gpu, tag, cell, st, ck = job
            if gpu in running:
                continue
            out = cdir / f"{tag}_{st}.npz"
            if out.exists() or not ck.exists():
                jobs.remove(job)
                if not ck.exists():
                    bad.append(f"{tag}_{st} missing checkpoint")
                continue
            if gpu_free_mib(gpu) < a.need_mib:
                continue
            lg = LOGS / f"enc_hcq_2x2_v1{'_smoke' if smoke else ''}_curve_{tag}_{st}.log"
            cmd = [cfg["py"], "-u", str(DUMP), "--code-dir", str(ARM), "--ckpt", str(ck), "--scen", cfg["scen"],
                   "--device", f"cuda:{gpu}", "--chunk", "512", "--out", str(out)] + (["--limit", "20"] if smoke else [])
            fh = open(lg, "w")
            running[gpu] = (tag, st, subprocess.Popen(cmd, env=dict(env, BWE_ENC=ENC[cell]), stdout=fh,
                                                      stderr=subprocess.STDOUT, cwd=str(ARM)), lg)
            jobs.remove(job)
            log(f"Started exporting curve point {tag} {st} on GPU {gpu}")
        time.sleep(a.poll)
    write_json_atomic(mark / f"CURVE_{machine}_DONE.json",
                      {"experiment": EXPERIMENT, "host": machine, "failed": bad,
                       "files": sorted(p.name for p in cdir.glob("*.npz"))})
    log(f"Curve point export finished, failures {bad}")


if __name__ == "__main__":
    sys.exit(main())
