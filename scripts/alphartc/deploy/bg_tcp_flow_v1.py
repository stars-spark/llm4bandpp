#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Long-lived TCP flow that shares the shaped bottleneck with the call; standard library only.
send connects at START_S, sets the congestion control (default cubic), sends at full speed until STOP_S and logs bytes sent, TCP_INFO and ss -tin each second; sink accepts one connection and logs bytes received each second, the competitor's goodput.
Usage: bg_tcp_flow_v1.py send IP PORT START_S STOP_S OUT.jsonl [CC] | sink PORT RUN_S OUT.jsonl | --selftest
"""
import json, socket, struct, subprocess, sys, time
TCP_CONGESTION = getattr(socket, "TCP_CONGESTION", 13)
TCP_INFO = getattr(socket, "TCP_INFO", 11)
CHUNK = 64 * 1024


def tcp_info(s):
    """Read struct tcp_info from socket s and return state, snd_mss, rtt, rttvar, ssthresh, snd_cwnd and total_retrans."""
    try:
        b = s.getsockopt(socket.IPPROTO_TCP, TCP_INFO, 104); u = struct.unpack("=8B24I", b[:104])
        return {"state": u[0], "ca_state": u[1], "snd_mss": u[8 + 2], "rtt_us": u[8 + 15], "rttvar_us": u[8 + 16], "snd_ssthresh": u[8 + 17], "snd_cwnd": u[8 + 18], "total_retrans": u[8 + 23]}
    except OSError as e:
        return {"error": repr(e)}


def ss_line(ip, port):
    try:
        out = subprocess.run(["ss", "-tin", "dst", f"{ip}:{port}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, timeout=2).stdout
        return " ".join(out.split())[:600]
    except Exception as e:
        return repr(e)


def send(ip, port, start_s, stop_s, out, cc="cubic"):
    t0 = time.time()
    with open(out, "w") as f:
        f.write(json.dumps({"event": "config", "ip": ip, "port": port, "start_s": start_s, "stop_s": stop_s, "cc_requested": cc, "t0_ms": int(t0 * 1000)}) + "\n"); f.flush()
        time.sleep(max(0.0, start_s - (time.time() - t0)))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try: s.setsockopt(socket.IPPROTO_TCP, TCP_CONGESTION, cc.encode())
        except OSError as e: f.write(json.dumps({"event": "cc_error", "error": repr(e)}) + "\n")
        try: got_cc = s.getsockopt(socket.IPPROTO_TCP, TCP_CONGESTION, 16).split(b"\0")[0].decode()
        except OSError: got_cc = None
        s.settimeout(5.0)
        try: s.connect((ip, port))
        except OSError as e:
            f.write(json.dumps({"event": "connect_error", "t_ms": int(time.time() * 1000), "error": repr(e)}) + "\n"); return
        f.write(json.dumps({"event": "connected", "t_ms": int(time.time() * 1000), "cc": got_cc}) + "\n"); f.flush()
        s.settimeout(0.2); buf = b"\0" * CHUNK; sec = int(time.time()); n = 0; total = 0
        while time.time() - t0 < stop_s:
            try: k = s.send(buf); n += k; total += k
            except socket.timeout: pass
            except OSError as e:
                f.write(json.dumps({"event": "send_error", "t_ms": int(time.time() * 1000), "error": repr(e)}) + "\n"); break
            now = time.time()
            if int(now) != sec:
                f.write(json.dumps({"t_ms": int(now * 1000), "sent_bytes": n, "total_bytes": total, "tcp_info": tcp_info(s), "ss": ss_line(ip, port)}) + "\n"); f.flush(); sec = int(now); n = 0
        f.write(json.dumps({"t_ms": int(time.time() * 1000), "sent_bytes": n, "total_bytes": total, "tcp_info": tcp_info(s), "partial": True}) + "\n")
        try: s.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        s.close(); f.write(json.dumps({"event": "end", "t_ms": int(time.time() * 1000), "total_bytes": total}) + "\n")


def sink(port, run_s, out):
    t0 = time.time(); ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM); ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("0.0.0.0", port)); ls.listen(1); ls.settimeout(0.5); c = None
    with open(out, "w") as f:
        f.write(json.dumps({"event": "config", "port": port, "run_s": run_s, "t0_ms": int(t0 * 1000)}) + "\n"); f.flush()
        while c is None and time.time() - t0 < run_s:
            try: c, addr = ls.accept(); f.write(json.dumps({"event": "accepted", "t_ms": int(time.time() * 1000), "peer": addr[0]}) + "\n"); f.flush()
            except socket.timeout: pass
        if c is None: f.write(json.dumps({"event": "no_connection"}) + "\n"); return
        c.settimeout(0.2); sec = int(time.time()); n = 0; total = 0
        while time.time() - t0 < run_s:
            try:
                d = c.recv(1 << 20)
                if not d: f.write(json.dumps({"event": "peer_closed", "t_ms": int(time.time() * 1000)}) + "\n"); break
                n += len(d); total += len(d)
            except socket.timeout: pass
            now = time.time()
            if int(now) != sec: f.write(json.dumps({"t_ms": int(now * 1000), "recv_bytes": n, "total_bytes": total}) + "\n"); f.flush(); sec = int(now); n = 0
        f.write(json.dumps({"t_ms": int(time.time() * 1000), "recv_bytes": n, "total_bytes": total, "partial": True}) + "\n"); c.close()


def selftest():
    import os, tempfile, threading
    d = tempfile.mkdtemp(); so, si = os.path.join(d, "s.jsonl"), os.path.join(d, "r.jsonl")
    th = threading.Thread(target=sink, args=(39251, 4.0, si)); th.start(); time.sleep(0.3); send("127.0.0.1", 39251, 0.5, 3.0, so); th.join()
    S = [json.loads(l) for l in open(so)]; R = [json.loads(l) for l in open(si)]
    sent = sum(r.get("sent_bytes", 0) for r in S); recv = sum(r.get("recv_bytes", 0) for r in R)
    con = [r for r in S if r.get("event") == "connected"]
    assert con and con[0]["cc"] == "cubic", f"Congestion control is not cubic: {con}"
    assert sent > 1_000_000 and recv >= 0.99 * sent, f"Send and receive on loopback should be nearly equal: sent {sent} received {recv}"
    assert any("tcp_info" in r and r["tcp_info"].get("snd_cwnd", 0) > 0 for r in S), "TCP_INFO did not read the congestion window"
    assert not (recv < 0.5 * sent), "should not pass: received bytes should not be less than half of sent"
    so2 = os.path.join(d, "s2.jsonl"); send("127.0.0.1", 39252, 0.0, 1.0, so2); S2 = [json.loads(l) for l in open(so2)]
    assert any(r.get("event") == "connect_error" for r in S2) and sum(r.get("sent_bytes", 0) for r in S2) == 0, "should record connection failure"
    print(f"Self-test passed: cubic, loopback sends {sent / 1e6:.1f} MB and receives {recv / 1e6:.1f} MB; a port with no listener is recorded as a connection failure")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "--selftest": selftest()
    elif a[0] == "send": send(a[1], int(a[2]), float(a[3]), float(a[4]), a[5], a[6] if len(a) > 6 else "cubic")
    elif a[0] == "sink": sink(int(a[1]), float(a[2]), a[3])
