#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parallel testbed scheduler: runs a job list in stages, one thread per container pair taking jobs from the stage queue and running one call each through the run script.
Scoring (qoe_quality_once_v1.py, or the job list's quality_script) runs in a background pool of at most vmaf_workers (mode async, inline or defer; drain_before empties the pool
before a stage). Each run moves to K/<condition> with run_meta.json; existing results or invalid_* are skipped; K/QUEUE_COMPLETE marks the end, K/QUEUE_FAILED a disk-space stop.
First version, written with run script v10; pairs are canon (the original pair) or i (pair pi of make_testbed_pairs_v2.sh). It schedules the 320x240 batches
(obsschema-closedloop-v2, obsschema-closedloop-nl-v1, the 100 to 400 kbit/s batches, content320-ch-gcc-v1); the 720p batches use parallel_testbed_v2.py.
Usage: python3 parallel_testbed_v1.py JOBS.json
"""
import gzip, json, os, queue, shutil, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]; SHARED = Path("/path/to/alphartc/LLM4Band"); BASE = Path("/path/to/testbed")
QUALITY = REPO / "scripts/alphartc/deploy/qoe_quality_once_v1.py"


def pair_env(p):
    if p == "canon": return {"ALPHARTC_APP_HOST": str(SHARED), "ALPHARTC_RECEIVER_CONTAINER": "alphartc4band", "ALPHARTC_SENDER_CONTAINER": "alphartc-staleness-sender", "ALPHARTC_NETWORK": "bwe-staleness-net"}
    return {"ALPHARTC_APP_HOST": str(BASE / f"p{p}"), "ALPHARTC_RECEIVER_CONTAINER": f"alphartc4band-p{p}", "ALPHARTC_SENDER_CONTAINER": f"alphartc-sender-p{p}", "ALPHARTC_NETWORK": f"bwe-p{p}-net"}


def free_gb(path): s = os.statvfs(path); return s.f_bavail * s.f_frsize / 2 ** 30


def cpu_temp_c():
    """Return the CPU package temperature (coretemp Package id 0) in °C, or None if it cannot be read."""
    import glob
    for lab in glob.glob("/sys/class/hwmon/hwmon*/temp*_label"):
        try:
            if open(lab).read().strip() == "Package id 0": return int(open(lab.replace("_label", "_input")).read()) / 1000
        except OSError: pass
    return None


class Runner:
    def __init__(self, spec):
        self.s = spec; self.K = Path(spec["K"]); self.K.mkdir(parents=True, exist_ok=True); self.lock = threading.Lock(); self.pending = 0; self.stop = False
        self.logf = Path(spec["log"]); self.pool = ThreadPoolExecutor(int(spec.get("vmaf_workers", 3))); self.futs = []

    def log(self, msg):
        with self.lock, self.logf.open("a") as f: f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")

    @staticmethod
    def tag(job): return f"{job['arm']}__{Path(job['profile']).stem}__d0__r1"

    def done(self, job):
        d = self.K / job["cond"]; return d.is_dir() and ((d / f"{self.tag(job)}.json").is_file() or any(d.glob("invalid_*")))

    def finish(self, src, cond, tag, media, meta):
        """Score the decoded video if present, delete it, compress large logs and move the run into K; runs in the scoring pool."""
        try:
            dec = src / f"decoded_{tag}.y4m"; q = "none"
            if media and dec.is_file() and (src / f"{tag}.json").is_file():
                qs = REPO / self.s["quality_script"] if self.s.get("quality_script") else QUALITY
                r = subprocess.run(["nice", "-n", "15", "/usr/bin/python3", str(qs), str(dec), str(SHARED / self.s["source"]), str(src / f"quality_{tag}.json"), "--step", "4"] + list(self.s.get("quality_args", [])),
                                   stdout=subprocess.DEVNULL, stderr=(src / "quality.log").open("w"), timeout=1800); q = r.returncode
            for p in list(src.glob("decoded_*.y4m")) + list(src.glob("invalid_*decoded_*.y4m")): p.unlink(missing_ok=True)
            for p in list(src.glob("obs_*.jsonl")) + list(src.glob("recv_*.log")):
                with p.open("rb") as a, gzip.open(str(p) + ".gz", "wb") as b: shutil.copyfileobj(a, b)
                p.unlink()
            meta["quality_rc"] = q; (src / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
            dst = self.K / cond
            if dst.exists(): shutil.rmtree(dst)
            shutil.move(str(src), str(dst)); self.log(f"{cond} finalizer quality code {q}")
        except Exception as e: self.log(f"{cond} finalizer exception {e!r}")
        finally:
            with self.lock: self.pending -= 1

    def run_one(self, pair, job, phase):
        cond = job["cond"]; arm = job["arm"]; prof = Path(job["profile"]); tag = self.tag(job)
        pe = pair_env(pair); out = Path(pe["ALPHARTC_APP_HOST"]) / "result" / self.s["name"] / cond
        if out.exists(): shutil.rmtree(out)
        out.mkdir(parents=True); env = dict(os.environ); env.update(self.s.get("common_env", {})); env.update(job.get("env", {})); env.update(pe)
        t0 = time.time(); temp0 = cpu_temp_c(); pp0 = (open("/sys/firmware/acpi/platform_profile").read().strip() if os.path.exists("/sys/firmware/acpi/platform_profile") else None); self.log(f"p{pair} {cond} start")
        with (out / "runner.log").open("w") as lf:
            try: rc = subprocess.run([self.s["runner"], arm, str(prof), "0", "1", str(out), "32"], env=env, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT, timeout=900).returncode
            except subprocess.TimeoutExpired: rc = "timeout"
        meta = {"pair": pair, "phase": phase["name"], "cond": cond, "arm": arm, "profile": str(prof), "start": t0, "end": time.time(), "rc": rc, "platform_profile": pp0, "cpu_temp_start": temp0, "cpu_temp_end": cpu_temp_c(), "env_overrides": {**self.s.get("common_env", {}), **job.get("env", {})}}
        self.log(f"p{pair} {cond} exit code {rc} elapsed {time.time() - t0:.0f}s")
        with self.lock: self.pending += 1
        return out, cond, tag, meta

    def run_phase(self, phase):
        if phase.get("drain_before"):
            self.log(f"Wait for the scoring pool to empty before phase {phase['name']} starts")
            while True:
                with self.lock:
                    if self.pending == 0: break
                time.sleep(5)
        jobs = [j for j in self.s["jobs"] if j["phase"] == phase["name"] and not self.done(j)]; q = queue.Queue()
        for j in jobs: q.put(j)
        self.log(f"Phase {phase['name']} starts: {len(jobs)} jobs, container pair {phase['pairs']}, scoring {phase['vmaf']}"); deferred = []; media = self.s.get("media", True)
        def worker(pair):
            while not self.stop:
                while phase["vmaf"] != "defer":
                    with self.lock: busy = self.pending >= int(self.s.get("max_pending", 6))
                    if not busy: break
                    time.sleep(3)
                t = cpu_temp_c()
                if t is not None and t >= 95:
                    self.log(f"p{pair} package temperature {t:.0f}°C, pause starting new calls")
                    while (cpu_temp_c() or 0) > 85: time.sleep(10)
                try: job = q.get_nowait()
                except queue.Empty: return
                root = SHARED if pair == "canon" else BASE
                if free_gb(root) < 1.5 or free_gb(self.K) < 1.5:
                    self.log(f"p{pair} available space less than 1.5 GB, stop"); self.stop = True; return
                res = self.run_one(pair, job, phase)
                if phase["vmaf"] == "async": self.futs.append(self.pool.submit(self.finish, res[0], res[1], res[2], media, res[3]))
                elif phase["vmaf"] == "inline": self.finish(res[0], res[1], res[2], media, res[3])
                else:
                    with self.lock: deferred.append(res)
        ths = [threading.Thread(target=worker, args=(p,)) for p in phase["pairs"]]
        for t in ths: t.start(); time.sleep(float(self.s.get("stagger_s", 7)))
        for t in ths: t.join()
        for res in deferred: self.futs.append(self.pool.submit(self.finish, res[0], res[1], res[2], media, res[3]))

    def main(self):
        self.log(f"scheduling started {self.s['name']}, running script {self.s['runner']}")
        for ph in self.s["phases"]:
            if self.stop: break
            self.run_phase(ph)
        for f in self.futs: f.result()
        self.pool.shutdown()
        if self.stop: (self.K / "QUEUE_FAILED").write_text(time.strftime("%FT%T")); self.log("scheduling failed and ended"); sys.exit(1)
        (self.K / "QUEUE_COMPLETE").write_text(time.strftime("%FT%T")); self.log("scheduling ended")


if __name__ == "__main__":
    Runner(json.load(open(sys.argv[1]))).main()
