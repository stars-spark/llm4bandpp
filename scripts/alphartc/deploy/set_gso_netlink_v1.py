#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn off segmentation offload in the sender container (compete-flow-v1, item 8 of registry/preregistrations/prereg_08.md;
hd720-closedloop-v1 uses the same setting so that both batches share it).
The container's iproute2 (ss180129, 2018) does not know gso_max_segs, and the host could not use sudo, so this script sends
an rtnetlink RTM_NEWLINK from inside the container with the standard library and sets IFLA_GSO_MAX_SEGS of eth0 to 1 (and
IFLA_GSO_MAX_SIZE if needed). TCP then puts one MSS per skb, and netem, which counts packets, no longer treats a 64 KB
segment as one packet. WebRTC sends UDP packet by packet without UDP segmentation offload and is not affected. A container
restart resets the value, so it is checked before every batch and inside the run script.
Usage (on the host): docker exec -i -u root SENDER_CONTAINER python3 - set eth0 1 [gso_max_size] < set_gso_netlink_v1.py;
read it back with get eth0.
--selftest checks only the message encoding (length, alignment, attribute numbers), touches no interface, and includes a
case that must fail.
"""
import os, socket, struct, sys

RTM_NEWLINK = 16
NLM_F_REQUEST, NLM_F_ACK = 1, 4
NLMSG_ERROR = 2
IFLA_GSO_MAX_SEGS, IFLA_GSO_MAX_SIZE = 40, 41


def rtattr_u32(kind, value):
    return struct.pack("=HHI", 8, kind, value)


def build(ifindex, segs=None, size=None, seq=1):
    body = struct.pack("=BxHiII", socket.AF_UNSPEC, 0, ifindex, 0, 0)
    if segs is not None: body += rtattr_u32(IFLA_GSO_MAX_SEGS, segs)
    if size is not None: body += rtattr_u32(IFLA_GSO_MAX_SIZE, size)
    return struct.pack("=IHHII", 16 + len(body), RTM_NEWLINK, NLM_F_REQUEST | NLM_F_ACK, seq, 0) + body


def send(msg):
    s = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 0)     # NETLINK_ROUTE
    s.bind((0, 0)); s.send(msg); data = s.recv(65536); s.close()
    ln, typ = struct.unpack("=IH", data[:6])
    if typ != NLMSG_ERROR: raise RuntimeError(f"Unexpected reply type {typ}")
    err = struct.unpack("=i", data[16:20])[0]
    if err != 0: raise OSError(-err, os.strerror(-err))


def read_link(dev):
    """Read the values from /sys; gso_max_segs and gso_max_size are missing from sysfs on newer kernels and are read with ip -d link."""
    import subprocess
    out = subprocess.run(["ip", "-d", "link", "show", dev], stdout=subprocess.PIPE, universal_newlines=True, check=True).stdout.split()
    get = lambda k: int(out[out.index(k) + 1]) if k in out else None
    return {"dev": dev, "gso_max_size": get("gso_max_size"), "gso_max_segs": get("gso_max_segs"), "mtu": get("mtu")}


def selftest():
    m = build(7, segs=1)
    assert len(m) == 16 + 16 + 8 and struct.unpack("=I", m[:4])[0] == len(m)
    assert struct.unpack("=HHI", m[32:40]) == (8, IFLA_GSO_MAX_SEGS, 1)
    m2 = build(7, segs=1, size=1500)
    assert struct.unpack("=HHI", m2[40:48]) == (8, IFLA_GSO_MAX_SIZE, 1500)
    bad = build(7, size=1500)
    assert struct.unpack("=HHI", bad[32:40])[1] != IFLA_GSO_MAX_SEGS
    print("Message encoding self-test passed (including one case that should not match)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest": selftest(); sys.exit(0)
    dev = a[1]
    if a[0] == "get": print(read_link(dev)); sys.exit(0)
    if a[0] == "set":
        segs = int(a[2]); size = int(a[3]) if len(a) > 3 else None
        idx = socket.if_nametoindex(dev); before = read_link(dev)
        send(build(idx, segs=segs, size=size)); after = read_link(dev)
        print({"before": before, "after": after})
        ok = after["gso_max_segs"] == segs and (size is None or after["gso_max_size"] == size)
        sys.exit(0 if ok else 3)
