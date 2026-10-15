#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Constant-rate UDP background flow through the shaped bottleneck; standard library only.
send emits packets carrying a sequence number and send time and logs packets and bytes each second; sink logs packets, bytes and the highest sequence number each second, for the background flow's arrival rate and loss.
Usage: bg_udp_flow_v1.py send IP PORT KBPS START_S STOP_S OUT.jsonl | sink PORT RUN_S OUT.jsonl
"""
import json, socket, struct, sys, time
PAYLOAD = 1172


def send(ip, port, kbps, start_s, stop_s, out):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); gap = (PAYLOAD + 28) * 8 / (kbps * 1000.0); t0 = time.time(); seq = 0; pad = b"\0" * (PAYLOAD - 12)
    with open(out, "w") as f:
        f.write(json.dumps({"event": "config", "kbps": kbps, "start_s": start_s, "stop_s": stop_s, "payload": PAYLOAD, "t0_ms": int(t0 * 1000)}) + "\n"); f.flush()
        time.sleep(max(0.0, start_s)); nxt = time.time(); sec = int(nxt); n = b = 0
        while time.time() - t0 < stop_s:
            now = time.time()
            if now < nxt: time.sleep(min(nxt - now, 0.01)); continue
            try: s.sendto(struct.pack("!Id", seq, now) + pad, (ip, port)); n += 1; b += PAYLOAD + 28
            except OSError: pass
            seq += 1; nxt += gap
            if nxt < now - 0.1: nxt = now
            if int(now) != sec: f.write(json.dumps({"t_ms": int(now * 1000), "sent_pkts": n, "sent_bytes": b, "seq": seq}) + "\n"); f.flush(); sec = int(now); n = b = 0
        f.write(json.dumps({"t_ms": int(time.time() * 1000), "sent_pkts": n, "sent_bytes": b, "seq": seq, "partial": True}) + "\n")
        f.write(json.dumps({"event": "end", "t_ms": int(time.time() * 1000), "seq": seq}) + "\n")


def sink(port, run_s, out):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", port)); s.settimeout(0.2); t0 = time.time(); sec = int(t0); n = b = 0; mx = -1; owd = []
    with open(out, "w") as f:
        while time.time() - t0 < run_s:
            try:
                d, _ = s.recvfrom(4096); q, ts = struct.unpack("!Id", d[:12]); n += 1; b += len(d) + 28; mx = max(mx, q); owd.append((time.time() - ts) * 1000)
            except socket.timeout: pass
            now = time.time()
            if int(now) != sec:
                f.write(json.dumps({"t_ms": int(now * 1000), "recv_pkts": n, "recv_bytes": b, "max_seq": mx, "owd_ms_median": sorted(owd)[len(owd) // 2] if owd else None}) + "\n"); f.flush(); sec = int(now); n = b = 0; owd = []
        f.write(json.dumps({"t_ms": int(time.time() * 1000), "recv_pkts": n, "recv_bytes": b, "max_seq": mx, "owd_ms_median": None, "partial": True}) + "\n")


def selftest():
    import os, tempfile, threading
    d = tempfile.mkdtemp(); so, si = os.path.join(d, "s.jsonl"), os.path.join(d, "r.jsonl")
    th = threading.Thread(target=sink, args=(39217, 5.0, si)); th.start(); time.sleep(0.3); send("127.0.0.1", 39217, 400, 0.5, 4.0, so); th.join()
    S = [json.loads(l) for l in open(so)]; R = [json.loads(l) for l in open(si)]
    sent = sum(r.get("sent_bytes", 0) for r in S); recv = sum(r.get("recv_bytes", 0) for r in R); rate = sent * 8 / 3.5 / 1000
    assert abs(rate - 400) / 400 < 0.10, f"Send bitrate deviates from the setpoint: {rate:.0f} kbps"
    assert recv >= 0.97 * sent, f"No packet loss on loopback: sent {sent} received {recv}"
    assert not (abs(rate - 800) / 800 < 0.10), "should not pass: the bitrate should not equal twice the configured value"
    print(f"Self-test passed: set 400 kbps, actually sent {rate:.0f} kbps, sent/received byte ratio {recv / sent:.3f}")


if __name__ == "__main__":
    if sys.argv[1] == "--selftest": selftest()
    elif sys.argv[1] == "send": send(sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]), sys.argv[7])
    elif sys.argv[1] == "sink": sink(int(sys.argv[2]), float(sys.argv[3]), sys.argv[4])
