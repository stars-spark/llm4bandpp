#!/usr/bin/env python3
"""Attach a detached bpftrace uprobe to AlphaRTC's receiver sink callback."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


SYMBOLS = {
    "core": "_ZN9Conductor15OnFrameCallbackERKN6webrtc10VideoFrameE",
    "thunk": "_ZThn24_N9Conductor15OnFrameCallbackERKN6webrtc10VideoFrameE",
}
WRITER_SYMBOL = "_ZN6webrtc4test23Y4mVideoFrameWriterImpl10WriteFrameERKNS_10VideoFrameE"


def matching_pids(fragment: str) -> list[int]:
    matches = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if "peerconnection_serverless.origin" in command and fragment in command:
            matches.append(int(entry.name))
    return sorted(matches)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-fragment", required=True)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--out-log", required=True, type=Path)
    parser.add_argument("--out-state", required=True, type=Path)
    parser.add_argument("--image", default="alphartc4band:latest")
    parser.add_argument("--symbol-role", choices=sorted(SYMBOLS), default="core")
    parser.add_argument("--probe-set", choices=("callback-only", "callback-writer"), default="callback-only")
    args = parser.parse_args()
    if args.out_log.exists() or args.out_state.exists():
        parser.error("refusing to overwrite uprobe output")

    deadline = time.monotonic() + 10
    targets = []
    while time.monotonic() < deadline:
        targets = matching_pids(args.config_fragment)
        if len(targets) == 1:
            break
        time.sleep(0.1)
    if len(targets) != 1:
        raise RuntimeError(f"expected one receiver origin process, found {targets}")
    target = targets[0]
    binary = f"/proc/{target}/root/usr/bin/peerconnection_serverless.origin"
    symbol = SYMBOLS[args.symbol_role]
    probes = [{"tag": "CALLBACK", "symbol": symbol}]
    if args.probe_set == "callback-writer":
        probes.append({"tag": "WRITER", "symbol": WRITER_SYMBOL})
    program = "\n".join(
        f'uprobe:{binary}:{probe["symbol"]} /pid == {target}/ '
        f'{{ printf("{probe["tag"]},%llu,%d,%d\\n", nsecs, pid, tid); }}'
        for probe in probes
    )
    args.out_log.parent.mkdir(parents=True, exist_ok=True)
    log_handle = args.out_log.open("xb")
    command = [
        "docker", "run", "--rm", "--name", args.container_name,
        "--privileged", "--pid=host", "-v", "/:/host:ro",
        "--tmpfs", "/host/tmp:rw,exec", args.image,
        "chroot", "/host", "/usr/bin/bpftrace", "-e", program,
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_handle.close()
    attach_deadline = time.monotonic() + 10
    attached = False
    while time.monotonic() < attach_deadline:
        if process.poll() is not None:
            break
        text = args.out_log.read_text(encoding="utf-8", errors="replace")
        if f"Attached {len(probes)} probe" in text:
            attached = True
            break
        time.sleep(0.1)
    if not attached:
        subprocess.run(["docker", "stop", "--time", "1", args.container_name], check=False, capture_output=True)
        raise RuntimeError(f"uprobe did not attach: {args.out_log.read_text(errors='replace')}")
    state = {
        "schema": "alphartc-sink-uprobe-v2",
        "target_host_pid": target,
        "target_binary": binary,
        "symbol_role": args.symbol_role,
        "symbol": symbol,
        "probe_set": args.probe_set,
        "probes": probes,
        "container_name": args.container_name,
        "docker_client_pid": process.pid,
        "bpftrace_program": program,
        "command": command,
    }
    args.out_state.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(state, sort_keys=True))


if __name__ == "__main__":
    main()
