#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raise the sender's default video bitrate cap in the AlphaRTC binary (2026-10-05).
Why: libwebrtc's GetMaxDefaultVideoBitrateKbps returns 2500 kbps for every resolution above 960x540 (hd720-sender-ceiling-
explore measured 720p calls capped at about 2.5 Mbit/s throughout), so at 3 and 8 Mbit/s the link was not the bottleneck
of a 720p call. The binary of the testbed image, /usr/bin/peerconnection_serverless.origin (sha256 d02abb83...), inlines this
function into cricket::EncoderStreamFactory::CreateDefaultVideoStreams: at most 76800 pixels gives 600, at most 307200 gives
1700, at most 518400 gives 2000 and more gives 2500 (virtual address 0x5a5e21, mov $0x9c4,%eax, B8 C4 09 00 00), then
multiplied by 1000.
The patch only replaces the immediate 2500 of the last tier by HB_KBPS (default 20000, i.e. B8 20 4E 00 00), keeping the
instruction length; the 600, 1700 and 2000 tiers are untouched, so 320x240 and other low-resolution batches are not affected.
B8 C4 09 00 00 occurs once in the whole file; $0x9c4 occurs 9 times in the code section, and the other 8 lie in audio
processing, AGC, VP9 and AV1 rate-distortion thresholds and Opus, unrelated to the video bitrate (checked).
Usage: python3 patch_pcs_maxbitrate_v1.py ORIGINAL OUTPUT [HB_KBPS]; checks the original's hash, then the target bytes,
writes the patched binary and prints its sha256; --selftest checks only the offset conversion and the byte replacement.
"""
import hashlib, re, struct, subprocess, sys
ORIG_SHA = "d02abb8306a131809320c0ff5b1bd185a8f444020fe4aa57d3b9a27a54f88761"; VA = 0x5a5e21; OLD = bytes.fromhex("b8c4090000")


def file_offset(path, va):
    out = subprocess.run(["readelf", "-lW", path], capture_output=True, text=True, check=True).stdout
    for m in re.finditer(r"LOAD\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)", out):
        off, vaddr, fsz = int(m.group(1), 16), int(m.group(2), 16), int(m.group(4), 16)
        if vaddr <= va < vaddr + fsz: return va - vaddr + off
    raise ValueError("The address is not within any loadable segment")


def patch(b, fo, kbps):
    assert bytes(b[fo:fo + 5]) == OLD, f"Target byte mismatch: {bytes(b[fo:fo + 5]).hex()}"
    assert bytes(b).count(OLD) == 1, "The original sequence is not unique"
    new = b"\xb8" + struct.pack("<I", kbps); b[fo:fo + 5] = new; return b


def selftest():
    b = bytearray(b"\x00" * 16 + OLD + b"\x00" * 16); patch(b, 16, 20000); assert bytes(b[16:21]) == bytes.fromhex("b8204e0000")
    try: patch(bytearray(b"\x00" * 40), 16, 20000); raise SystemExit("A test case that should have been blocked passed")
    except AssertionError: pass
    print("Self-test passed: patch applied; wrong target bytes rejected")


def main():
    src, dst = sys.argv[1], sys.argv[2]; kbps = int(sys.argv[3]) if len(sys.argv) > 3 else 20000
    raw = open(src, "rb").read(); h = hashlib.sha256(raw).hexdigest(); assert h == ORIG_SHA, f"original binary hash mismatch: {h}"
    fo = file_offset(src, VA); b = patch(bytearray(raw), fo, kbps); open(dst, "wb").write(b)
    import os; os.chmod(dst, 0o755)
    print(f"File offset {fo:#x}, 2500 changed to {kbps} kbps; patched version sha256 {hashlib.sha256(bytes(b)).hexdigest()}")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
