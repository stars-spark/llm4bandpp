#!/usr/bin/env python3
"""tcp_info source of realtel-e2e: a loopback TCP sender at a fixed rate; the receiver reads getsockopt(TCP_INFO) every
100 ms and writes JSONL. The struct tcp_info offsets were checked against data/real_telemetry_specs_v1/raw/linux_tcp.h
(probes 3, lost 32, last_data_recv 52, rtt 68, rttvar 72, bytes_received 128, min_rtt 148, data_segs_in 152,
delivery_rate 160). Usage: tcpinfo_pair.py OUT.jsonl SECONDS BITRATE
"""
import json, socket, struct, sys, threading, time
OUT, DUR, RATE = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); PORT = 6000; CHUNK = 1400
F = {"tcpi_probes": ("B", 3), "tcpi_lost": ("I", 32), "tcpi_last_data_recv": ("I", 52), "tcpi_rtt": ("I", 68), "tcpi_rttvar": ("I", 72),
     "tcpi_bytes_received": ("Q", 128), "tcpi_min_rtt": ("I", 148), "tcpi_data_segs_in": ("I", 152), "tcpi_delivery_rate": ("Q", 160)}
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", PORT)); srv.listen(1)
def send():
    c = socket.create_connection(("127.0.0.1", PORT)); buf = b"x" * CHUNK; gap = CHUNK * 8 / RATE; t = time.time(); end = t + DUR
    while time.time() < end:
        c.sendall(buf); t += gap; d = t - time.time()
        if d > 0: time.sleep(d)
    c.close()
threading.Thread(target=send, daemon=True).start()
conn, _ = srv.accept(); stop = False; got = [0]
def reader():
    while True:
        b = conn.recv(65536)
        if not b: break
        got[0] += len(b)
th = threading.Thread(target=reader, daemon=True); th.start()
with open(OUT, "w") as f:
    while th.is_alive():
        raw = conn.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 232); rec = {"t": time.time(), "app_bytes_read": got[0]}
        for k, (fmt, off) in F.items(): rec[k] = struct.unpack_from("<" + fmt, raw, off)[0]
        f.write(json.dumps(rec) + "\n"); time.sleep(0.1)
open(OUT + ".DONE", "w").write("1")
