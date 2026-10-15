#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parallel testbed scheduler for the 720p batches: as v1 it runs a job list stage by stage, one thread per container pair, and hands scoring (qoe_quality_once_v3.py) to a background pool.
Copy of v1 with these changes: jobs carry repetition, content id, queue length and scoring source (run tags carry r{rep} and v{video_id}); the decoded video (about 5 GB for a
128 s call) is subsampled into sub_*.y4m right after the call and deleted; gso_max_segs of the sender eth0 is reset before every run if needed (set_gso_netlink_v1.py);
a free-space gate stops with QUEUE_FAILED after 30 minutes; each job runs once and always writes run_meta.json, so a resume skips it; large logs are compressed; pin_pair fixes the pair.
Runs every 720p batch of Tables IV and V and compete-flow-ch-v1 (TESTBED.md, section 7).
Usage: python3 parallel_testbed_v2.py JOBS.json; --selftest checks tags, subsampling, resume and the disk gate with a fake run script (including cases that must fail).
"""
import gzip, json, os, queue, shutil, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]; SHARED = Path("/path/to/alphartc/LLM4Band"); BASE = Path("/path/to/testbed")
QUALITY = REPO / "scripts/alphartc/deploy/qoe_quality_once_v3.py"; GSO_TOOL = REPO / "scripts/alphartc/deploy/set_gso_netlink_v1.py"


def pair_env(p):
    if p == "canon": return {"ALPHARTC_APP_HOST": str(SHARED), "ALPHARTC_RECEIVER_CONTAINER": "alphartc4band", "ALPHARTC_SENDER_CONTAINER": "alphartc-staleness-sender", "ALPHARTC_NETWORK": "bwe-staleness-net"}
    return {"ALPHARTC_APP_HOST": str(BASE / f"p{p}"), "ALPHARTC_RECEIVER_CONTAINER": f"alphartc4band-p{p}", "ALPHARTC_SENDER_CONTAINER": f"alphartc-sender-p{p}", "ALPHARTC_NETWORK": f"bwe-p{p}-net"}


def free_gb(path): s = os.statvfs(path); return s.f_bavail * s.f_frsize / 2 ** 30


def cpu_temp_c():
    import glob
    for lab in glob.glob("/sys/class/hwmon/hwmon*/temp*_label"):
        try:
            if open(lab).read().strip() == "Package id 0": return int(open(lab.replace("_label", "_input")).read()) / 1000
        except OSError: pass
    return None


def run_tag(job):
    t = f"{job['arm']}__{Path(job['profile']).stem}__d0__r{int(job.get('rep', 1))}"
    return t + (f"__v{job['video_id']}" if job.get("video_id") else "")


def decoded_duration_s(csv_path):
    """Seconds between the first and last complete-frame growth in the decoded-file growth record; None if it cannot be read."""
    try:
        import csv
        ts = [int(r["wall_time_ns"]) for r in csv.DictReader(open(csv_path)) if int(r.get("delta_complete_frames") or 0) > 0]
        return (ts[-1] - ts[0]) / 1e9 if len(ts) >= 2 else None
    except Exception: return None


def gzip_inplace(p):
    with p.open("rb") as a, gzip.open(str(p) + ".gz", "wb") as b: shutil.copyfileobj(a, b)
    p.unlink()


class Runner:
    def __init__(self, spec, dry=False):
        self.s = spec; self.K = Path(spec["K"]); self.K.mkdir(parents=True, exist_ok=True); self.lock = threading.Lock(); self.pending = 0; self.stop = False; self.dry = dry
        self.logf = Path(spec["log"]); self.logf.parent.mkdir(parents=True, exist_ok=True); self.pool = ThreadPoolExecutor(int(spec.get("vmaf_workers", 1))); self.futs = []
        self.q = spec.get("quality", {}); self.step = int(self.q.get("step", 8))

    def log(self, msg):
        with self.lock, self.logf.open("a") as f: f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")

    def done(self, job): return (self.K / job["cond"] / "run_meta.json").is_file()

    def ensure_gso(self, pair):
        want = self.s.get("gso_segs")
        if want is None or self.dry: return None
        sc = pair_env(pair)["ALPHARTC_SENDER_CONTAINER"]
        def get():
            r = subprocess.run(["docker", "exec", "-i", "-u", "root", sc, "python3", "-", "get", "eth0"], stdin=open(GSO_TOOL), capture_output=True, text=True, timeout=30)
            try: return eval(r.stdout.strip(), {"__builtins__": {}}).get("gso_max_segs")
            except Exception: return None
        before = get(); after = before
        if before != int(want):
            subprocess.run(["docker", "exec", "-i", "-u", "root", sc, "python3", "-", "set", "eth0", str(int(want))], stdin=open(GSO_TOOL), capture_output=True, text=True, timeout=30)
            after = get(); self.log(f"p{pair} sender gso_max_segs {before}, set to {after}")
        return {"before": before, "after": after}

    def space_ok(self):
        tmpdir = self.q.get("tmpdir", "/path/to/storage")
        return free_gb(BASE if BASE.exists() else self.K) >= float(self.s.get("min_free_gb_home", 8)) and free_gb(Path(tmpdir) if Path(tmpdir).exists() else Path(tmpdir).parent) >= float(self.s.get("min_free_gb_storage", 1.5))

    def subsample(self, src, tag):
        """Subsample the full decoded video by the frame step and delete it; for an invalid run the full video is deleted directly. Returns the subsequence path or None."""
        dec = src / f"decoded_{tag}.y4m"; sub = None
        if dec.is_file() and (src / f"{tag}.json").is_file():
            sub = src / f"sub_{tag}.y4m"
            r = subprocess.run(["nice", "-n", "10", "ffmpeg", "-v", "error", "-y", "-i", str(dec), "-vf", f"select=not(mod(n\\,{self.step}))", "-fps_mode", "passthrough", "-pix_fmt", "yuv420p", str(sub)],
                               capture_output=True, text=True, timeout=900)
            if r.returncode != 0: self.log(f"{src.name} frame extraction failed {r.stderr[-200:]}"); sub = None
        for p in list(src.glob("decoded_*.y4m")) + list(src.glob("invalid_*decoded_*.y4m")): p.unlink(missing_ok=True)
        return sub

    def finish(self, src, cond, tag, sub, job, meta):
        try:
            q = "none"
            if sub is not None and sub.is_file():
                dur = decoded_duration_s(src / f"decoded_timestamps_{tag}.csv"); meta["decoded_duration_s"] = dur; Q = self.q
                cmd = ["nice", "-n", "15", "/usr/bin/python3", str(QUALITY), str(sub), str(SHARED / job["source"]), str(src / f"quality_{tag}.json"), "--width", str(Q.get("width", 1280)), "--height", str(Q.get("height", 720)),
                       "--label-y", str(Q["label_y"]), "--ref-frames", str(Q.get("ref_frames", 300)), "--step", str(self.step), "--ocr-jobs", str(Q.get("ocr_jobs", 6)), "--vmaf-threads", str(Q.get("vmaf_threads", 6)),
                       "--ocr-scale", str(Q.get("ocr_scale", 0.5)), "--tmpdir", str(Q.get("tmpdir", "/path/to/storage/hd720_scoring_tmp")), "--ocr-csv", str(src / f"ocr_{tag}.csv")] + (["--duration-s", f"{dur:.3f}"] if dur else [])
                if self.dry: cmd = ["true"]
                r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=(src / "quality.log").open("w"), timeout=2400); q = r.returncode
                sub.unlink(missing_ok=True)
            for pat in ("obs_*.jsonl", "recv_*.log", "senderwebrtc_*.log", "comp_network_*.log", "comp_recv_*.log", "decoded_timestamps_*.csv", "decision_*.jsonl", "comp_decision_*.jsonl", "ocr_*.csv"):
                for p in src.glob(pat):
                    if p.stat().st_size > 200_000: gzip_inplace(p)
            meta["quality_rc"] = q; meta["finished"] = time.time(); (src / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
            dst = self.K / cond
            if dst.exists(): shutil.rmtree(dst)
            shutil.move(str(src), str(dst)); self.log(f"{cond} finalizer quality code {q}")
        except Exception as e: self.log(f"{cond} finalizer exception {e!r}")
        finally:
            with self.lock: self.pending -= 1

    def run_one(self, pair, job, phase):
        cond = job["cond"]; tag = run_tag(job); pe = pair_env(pair); out = Path(pe["ALPHARTC_APP_HOST"]) / "result" / self.s["name"] / cond
        if out.exists(): shutil.rmtree(out)
        out.mkdir(parents=True); env = dict(os.environ); env.update(self.s.get("common_env", {})); env.update(job.get("env", {})); env.update(pe)
        if job.get("video_id"): env["STALENESS_VIDEO_ID"] = str(job["video_id"])
        if job.get("source"): env["STALENESS_SOURCE_FILE"] = str(job["source"])
        gso = self.ensure_gso(pair)
        free0 = round(free_gb(BASE), 2) if BASE.exists() else None; t0 = time.time(); temp0 = cpu_temp_c(); pp0 = (open("/sys/firmware/acpi/platform_profile").read().strip() if os.path.exists("/sys/firmware/acpi/platform_profile") else None); self.log(f"p{pair} {cond} start")
        with (out / "runner.log").open("w") as lf:
            try: rc = subprocess.run([self.s["runner"], job["arm"], str(job["profile"]), "0", str(int(job.get("rep", 1))), str(out), str(int(job.get("queue", 32)))], env=env, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT, timeout=900).returncode
            except subprocess.TimeoutExpired: rc = "timeout"
        meta = {"pair": pair, "phase": phase["name"], "cond": cond, "tag": tag, "arm": job["arm"], "profile": str(job["profile"]), "rep": job.get("rep", 1), "video_id": job.get("video_id"), "queue": job.get("queue", 32),
                "source": job.get("source"), "start": t0, "end": time.time(), "rc": rc, "platform_profile": pp0, "cpu_temp_start": temp0, "cpu_temp_end": cpu_temp_c(), "gso": gso,
                "free_gb_home_start": free0, "free_gb_home_end": round(free_gb(BASE), 2) if BASE.exists() else None, "env_overrides": {**self.s.get("common_env", {}), **job.get("env", {})}}
        self.log(f"p{pair} {cond} exit code {rc} elapsed {time.time() - t0:.0f}s")
        sub = self.subsample(out, tag) if self.s.get("media", True) else None
        with self.lock: self.pending += 1
        return out, cond, tag, sub, job, meta

    def wait_space(self, pair):
        t = 0
        while not self.space_ok():
            with self.lock: pend = self.pending
            if t == 0: self.log(f"p{pair} insufficient disk space (/home {free_gb(BASE):.1f} GB), waiting for the scoring pool to drain (pending evaluation {pend})")
            if t >= 1800 or (pend == 0 and t >= 60): return False
            time.sleep(15); t += 15
        return True

    def run_phase(self, phase):
        if phase.get("drain_before"):
            while True:
                with self.lock:
                    if self.pending == 0: break
                time.sleep(5)
        jobs = [j for j in self.s["jobs"] if j["phase"] == phase["name"] and not self.done(j)]; q = queue.Queue(); pinned = {p: queue.Queue() for p in phase["pairs"]}
        for j in jobs:
            (pinned[j["pin_pair"]] if j.get("pin_pair") in pinned else q).put(j)
        self.log(f"Phase {phase['name']} starts: {len(jobs)} jobs, container pair {phase['pairs']}, scoring {phase['vmaf']}")

        def worker(pair):
            while not self.stop:
                while True:
                    with self.lock: busy = self.pending >= int(self.s.get("max_pending", 4))
                    if not busy: break
                    time.sleep(3)
                t = cpu_temp_c()
                if t is not None and t >= 95:
                    self.log(f"p{pair} package temperature {t:.0f}°C, pause starting new calls")
                    while (cpu_temp_c() or 0) > 85: time.sleep(10)
                try: job = pinned[pair].get_nowait()
                except queue.Empty:
                    try: job = q.get_nowait()
                    except queue.Empty: return
                if not self.wait_space(pair):
                    self.log(f"p{pair} disk space still below the gate after the scoring pool drained; stopping"); self.stop = True; return
                res = self.run_one(pair, job, phase)
                if phase["vmaf"] == "async": self.futs.append(self.pool.submit(self.finish, *res))
                else: self.finish(*res)
        ths = [threading.Thread(target=worker, args=(p,)) for p in phase["pairs"]]
        for t in ths: t.start(); time.sleep(float(self.s.get("stagger_s", 7)))
        for t in ths: t.join()

    def main(self):
        self.log(f"scheduling started {self.s['name']}, running script {self.s['runner']}")
        for ph in self.s["phases"]:
            if self.stop: break
            self.run_phase(ph)
        for f in self.futs: f.result()
        self.pool.shutdown()
        if self.stop: (self.K / "QUEUE_FAILED").write_text(time.strftime("%FT%T")); self.log("scheduling failed and ended"); sys.exit(1)
        (self.K / "QUEUE_COMPLETE").write_text(time.strftime("%FT%T")); self.log("scheduling ended")


def selftest():
    import tempfile
    global BASE
    d = Path(tempfile.mkdtemp(dir="/path/to/storage")); old_base = BASE
    try:
        BASE = d / "tb"; (BASE / "p1").mkdir(parents=True); (BASE / "p2").mkdir(parents=True)
        fake = d / "fake_runner.sh"
        fake.write_text("""#!/usr/bin/env bash
arm=$1; prof=$2; rep=$4; out=$5; q=$6; vid=${STALENESS_VIDEO_ID:-}
tag="${arm}__$(basename "$prof" .profile)__d0__r${rep}"; [ -z "$vid" ] || tag="${tag}__v${vid}"
echo "q=$q" > "$out/args_$tag.txt"
ffmpeg -v error -y -f lavfi -i testsrc=size=64x48:rate=30 -frames:v 40 -pix_fmt yuv420p "$out/decoded_$tag.y4m"
[ "$arm" = bad ] && exit 5
echo '{}' > "$out/$tag.json"
""")
        fake.chmod(0o755)
        jobs = [{"phase": "x", "cond": f"c{i}", "arm": "bad" if i == 3 else "a", "profile": "/x/C2.profile", "rep": i, "video_id": "johnny", "queue": 53, "source": "none", "env": {}} for i in range(1, 5)]
        spec = {"name": "selftest", "K": str(d / "K"), "log": str(d / "log.txt"), "runner": str(fake), "media": True, "vmaf_workers": 1, "max_pending": 2, "stagger_s": 0,
                "quality": {"step": 8, "label_y": 40, "tmpdir": str(d)}, "min_free_gb_home": 0.1, "min_free_gb_storage": 0.1, "phases": [{"name": "x", "pairs": [1, 2], "vmaf": "async"}], "jobs": jobs}
        jobs[1]["pin_pair"] = 2; jobs[3]["pin_pair"] = 2
        r = Runner(spec, dry=True); r.main()
        K = d / "K"
        assert (K / "QUEUE_COMPLETE").is_file()
        for i in range(1, 5):
            m = json.load(open(K / f"c{i}" / "run_meta.json")); tag = f"{'bad' if i == 3 else 'a'}__C2__d0__r{i}__vjohnny"
            assert m["tag"] == tag and (K / f"c{i}" / f"args_{tag}.txt").read_text().strip() == "q=53", m
            assert not list((K / f"c{i}").glob("decoded_*.y4m")), "the full-decode video should have been deleted"
        assert json.load(open(K / "c3" / "run_meta.json"))["rc"] == 5 and json.load(open(K / "c3" / "run_meta.json"))["quality_rc"] == "none"
        assert json.load(open(K / "c1" / "run_meta.json"))["quality_rc"] == 0
        assert json.load(open(K / "c2" / "run_meta.json"))["pair"] == 2 and json.load(open(K / "c4" / "run_meta.json"))["pair"] == 2, "The specified pair did not take effect"
        (K / "QUEUE_COMPLETE").unlink(); r2 = Runner(spec, dry=True); r2.main(); assert any("0 jobs" in l for l in (d / "log.txt").read_text().splitlines()[-3:])
        spec2 = dict(spec, K=str(d / "K2"), min_free_gb_home=1e6); r3 = Runner(spec2, dry=True)
        try: r3.main(); raise AssertionError("The disk gate did not block it")
        except SystemExit: pass
        assert (d / "K2" / "QUEUE_FAILED").is_file() and not list((d / "K2").glob("c*"))
        print("Scheduler v2 self-test passed (tags, queue length, pair pinning, subsampling, invalid runs, resume, disk gate)")
    finally:
        BASE = old_base; shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1] == "--selftest": selftest()
    else: Runner(json.load(open(sys.argv[1]))).main()
