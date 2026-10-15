#!/usr/bin/env python3
"""Unit-aware name matcher: a rule-based non-LLM baseline for interface adaptation.
match(names, stats, ref) returns 15 entries {"source": j, "scale": a}, meaning interface feature k = source field j times a.
Field names are split into words (camel case, separators, case-sensitive units, dictionary word breaking, CJK names through a small lexicon), mapped to concept tags and scored per feature by fixed rules.
Unit words give dimension and scale, restricted to an allowed set. Each (feature, field) pair also gets an asinh-log distance between field quantiles and the reference, plus scale-free checks (sign, fraction bound, long/short ratio, share of zeros).
Cost = -name score + W_DIST x distribution cost; a Hungarian assignment uses each field once (with a fallback when there are fewer than 15 fields).
Needs only numpy and hungarian.py; names that cannot be parsed fall back to the distribution cost.
"""
import math
import re
import unicodedata

import numpy as np

from hungarian import assign_min

N_FEAT = 15
ALLOWED = (1.0, 1000.0, 0.001, 1e6, 1e-6, 8.0, 0.125, 100.0, 0.01, 125.0, 0.008, 1024.0, 1.0 / 1024)

TIME_F = (3, 4, 5, 7, 8, 9)
FRAC_F = (10, 12, 13, 14)
OFFSET_F = (4, 5)
UNITLESS_RATIO_F = (6,)

W_DIST = 2.0
W_LS = 0.7
W_MAX = 0.3
W_ZERO = 1.0
STRONG_MISTRUST = 3.0
WEAK_MISTRUST = 0.7

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_LEX_SRC = {
    "RECV": "recv received receive receiving receiver rcv rcvd recvd rx rcvr incoming inbound ingress down dl "
            "downlink downstream arrived delivered delivery got",
    "SEND": "tx sent send sending sender outgoing egress uplink ul",
    "RATE": "bitrate bitrates throughput throughputs tput thru thruput thrpt thpt xput goodput gput bandwidth bw "
            "speed datarate br:0.6 avail:0.3 available:0.3",
    "RATEW": "rate rates",
    "PKT": "packet packets pkt pkts pck pcks pckt pckts pak paks datagram datagrams dgram dgrams pk pks "
           "segment:0.6 segments:0.6 pps",
    "COUNT": "count counts cnt num number nr nb n total tot sum qty quantity amount",
    "BYTE": "byte bytes octet octets bytecount",
    "BIT": "bit bits",
    "VOL": "volume vol payload data traffic size:0.6 sz:0.6",
    "QUEUE": "queue queues queuing queueing queued q qdelay qdel qd qdly queuedelay queueingdelay queuingdelay "
             "buffer buffering buf bufferbloat bloat sojourn standing backlog congestion:0.7 qdelayms",
    "DELAY": "delay delays dly latency latencies lat transit lag owd owds qdelay qdel qdly queuedelay "
             "queueingdelay queuingdelay basedelay ipdv:0.5 sojourn:0.5 e2e:0.5",
    "OWD": "owd owds oneway 1way fwd:0.6 forward:0.6 unidirectional ow:0.6 owl:0.5",
    "RTT": "rtt rtts srtt minrtt rttvar",
    "MIN": "min minimum mins mn lowest lower:0.6 floor least smallest best:0.6 minrtt",
    "BASE": "base baseline basedelay propagation intrinsic static:0.6 unloaded idle:0.6 noload",
    "MAX": "max maximum mx peak highest worst",
    "MEAN": "mean means avg average averaged av mu ewma smoothed smooth srtt typical expected median med p50 mid:0.5 "
            "mbl",
    "RATIO": "ratio ratios norm normalized normalised normalize rel:0.6 relative:0.6 factor quotient multiple "
             "multiplier mult inflation inflated inflate stretch div plr:0.5 lossrate rat:0.6 over:0.5",
    "EXCESS": "excess above over:0.6 minus diff difference delta extra surplus beyond added increase increment rise "
              "exceed exceeding excursion less:0.6 sub:0.6 subtract residual rel:0.6 relative:0.6 overhead:0.6 "
              "variable:0.6 range:0.6 xs:0.6",
    "WIN": "win window windowed wnd local intra inwin current cur instant inst instantaneous",
    "SOFAR": "sofar global running hist historical history overall session:0.5 cumulative cum since ever alltime "
             "lifetime tracked:0.5",
    "IAT": "iat iats interarrival interarrivals ia ipg ipgs ipt spacing gap gaps interpacket dispersion "
           "interframe:0.5 dt:0.6",
    "INTER": "inter",
    "ARRIVAL": "arrival arrivals arr arrive",
    "INTERVAL": "interval intervals period",
    "TIME": "time times duration dur",
    "BETWEEN": "between",
    "JITTER": "jitter jitters jit jtr jitt pdv ipdv wobble",
    "STD": "std stdev stddev sd sigma dev deviation var variance variability variation spread:0.6 mad rttvar",
    "LOSS": "loss losses lost lose losing drop drops dropped dropping discard discarded discards missing miss "
            "missed plr erasure erasures ploss lossrate mbl lpe",
    "LOSTCNT": "lost dropped drops discarded discards missed erasures lpe nlost",
    "EVENT": "event events ev evt episode episodes occurrence occurrences burst bursts streak cluster clusters mbl "
             "incident incidents lpe",
    "LEN": "length len depth",
    "VIDEO": "video vid vdo cam camera visual vp8 vp9 h264 h265 hevc av1",
    "AUDIO": "audio aud voice opus sound speech voip mic",
    "PROBE": "probe probes probing prb padding pad padded probed",
    "SHARE": "share shares frac fraction fractional proportion portion part pct percent percentage perc mix "
             "composition",
    "PER": "per",
    "ONE": "one",
    "WAY": "way",
    "SO": "so",
    "FAR": "far",
    "SEEN": "seen",
    "OF": "of",
    "TO": "to",
    "VS": "vs versus",
    "RUN": "run runs",
    "PROB": "prob",
    "PROP": "prop",
    "_": "media stream streams flow flows value val values stat stats metric metrics field feature feat client "
         "the a an and at by for from with est estimate estimated measured meas observed obs sample samples level "
         "state info net network link path conn connection call calls all on is per_ last this "
         "since_start x y z rtc webrtc quic tcp udp rtp rtcp pkt_ ts timestamp count_ host remote local_ "
         "ratio_ value_ raw total_ window_ windows sliding short long status focus bonus campus virus census "
         "items terms plus thus previous various",
}

_UNIT = {}


def _u(kind, words, *payload):
    for w in words.split():
        _UNIT[w] = (kind,) + payload


_u("time", "ms msec msecs millis millisec millisecs millisecond milliseconds milli", 1.0, True)
_u("time", "sec secs second seconds", 1000.0, True)
_u("time", "s", 1000.0, False)
_u("time", "us usec usecs micros microsec microsecs microsecond microseconds", 0.001, True)
_u("time", "ns nsec nsecs nanos nanosec nanosecond nanoseconds", 1e-6, True)
_u("data", "bit bits", [("bit", 1.0)], True)
_u("data", "b", [("bit", 1.0), ("byte", 1.0)], False)
_u("data", "kbit kbits kilobit kilobits", [("bit", 1e3)], True)
_u("data", "kb", [("bit", 1e3), ("byte", 1e3)], False)
_u("data", "mbit mbits megabit megabits", [("bit", 1e6)], True)
_u("data", "mb", [("bit", 1e6), ("byte", 1e6)], False)
_u("data", "gbit gbits gigabit gigabits", [("bit", 1e9)], True)
_u("data", "byte bytes octet octets", [("byte", 1.0)], True)
_u("data", "kbyte kbytes kilobyte kilobytes", [("byte", 1e3)], True)
_u("data", "kib kibibyte kibibytes", [("byte", 1024.0)], True)
_u("data", "mbyte mbytes megabyte megabytes", [("byte", 1e6)], True)
_u("data", "mib mebibyte mebibytes", [("byte", 1048576.0)], True)
_u("data", "kibit kibits kibibit kibibits", [("bit", 1024.0)], True)
_u("rate", "bps bitps bitspersec", [("bit", 1.0)], 1.0, True)
_u("rate", "kbps kbitps kbitspersec", [("bit", 1e3)], 1.0, True)
_u("rate", "mbps mbitps", [("bit", 1e6)], 1.0, True)
_u("rate", "gbps gbitps", [("bit", 1e9)], 1.0, True)
_u("rate", "kibps", [("bit", 1024.0)], 1.0, True)
_u("frac", "pct percent percentage perc", 0.01, True)
_u("frac", "permille permil promille pml", 0.001, True)
_u("frac", "ppm", 1e-6, True)
_u("frac", "frac fraction fractional ratio share proportion", 1.0, False)

_CASE_UNITS = [
    ("KiloBytes", "kbyte"), ("KiloBits", "kbit"), ("MegaBytes", "mbyte"), ("MegaBits", "mbit"),
    ("KBytes", "kbyte"), ("kBytes", "kbyte"), ("MBytes", "mbyte"), ("KBits", "kbit"), ("kBits", "kbit"),
    ("MBits", "mbit"), ("Kbits", "kbit"), ("Mbits", "mbit"), ("MilliSeconds", "milliseconds"),
    ("MicroSeconds", "microseconds"), ("NanoSeconds", "nanoseconds"),
    ("KiBps", "qqkibpsqq"), ("KiB/s", "qqkibpsqq"),
    ("MBps", "qqmbyteps"), ("KBps", "qqkbyteps"), ("kBps", "qqkbyteps"), ("Bps", "qqbyteps"),
    ("MB/s", "qqmbyteps"), ("KB/s", "qqkbyteps"), ("kB/s", "qqkbyteps"), ("B/s", "qqbyteps"),
    ("Kbps", "kbps"), ("Mbps", "mbps"), ("Gbps", "gbps"),
    ("KiB", "kib"), ("MiB", "mib"), ("Kibit", "kibit"), ("Kib", "kibit"),
    ("kbit", "kbit"), ("Kbit", "kbit"), ("Mbit", "mbit"),
    ("kB", "kbyte"), ("KB", "kbyte"), ("MB", "mbyte"), ("GB", "qqgbyte"),
    ("Kb", "kbit"), ("Mb", "mbit"),
]
_UNIT["qqkibpsqq"] = ("rate", [("byte", 1024.0)], 1.0, True)
_UNIT["qqmbyteps"] = ("rate", [("byte", 1e6)], 1.0, True)
_UNIT["qqkbyteps"] = ("rate", [("byte", 1e3)], 1.0, True)
_UNIT["qqbyteps"] = ("rate", [("byte", 1.0)], 1.0, True)
_UNIT["qqgbyte"] = ("data", [("byte", 1e9)], True)
_UNIT["qqbigb"] = ("data", [("byte", 1.0)], True)

_ZH = [
    ("receive rate", "recv rate"), ("receive bitrate", "recv bitrate"), ("bitrate", "bitrate"), ("bitrate", "bitrate"),
    ("Rate", "rate"), ("throughput", "throughput"), ("throughput", "throughput"), ("Bandwidth", "bandwidth"),
    ("per second", "per sec"), ("receive", "recv"), ("received", "recv"), ("packet count", "packets count"), ("packets", "packets"),
    ("group", "packets"), ("packet", "packets"), ("kilobyte", "kbyte"), ("bytes", "bytes"), ("kilobit", "kbit"),
    ("megabit", "mbit"), ("bit", "bits"), ("queueing latency", "queue delay"), ("queueing delay", "queue delay"),
    ("queue", "queue"), ("queue", "queue"), ("one-way latency", "one way delay"), ("one-way delay", "one way delay"),
    ("delay ratio", "delay ratio"), ("delay", "delay"), ("Delay", "delay"), ("Delay", "delay"), ("one-way", "one way"),
    ("minimum value", "min"), ("minimum", "min"), ("lowest", "min"), ("baseline", "base"), ("base", "base"), ("Average", "mean"),
    ("mean", "mean"), ("ratio", "ratio"), ("ratio", "ratio"), ("exceed", "excess"), ("higher than", "excess"),
    ("subtract", "minus"), ("Difference", "diff"), ("in-window", "window"), ("window", "window"), ("to date", "so far"),
    ("history", "historical"), ("inter-arrival time", "interarrival"), ("Packet interval", "interarrival"), ("Interval", "interval"),
    ("jitter", "jitter"), ("packet loss rate", "loss ratio"), ("packet loss", "loss"), ("loss", "lost"), ("event", "event"),
    ("burst", "burst"), ("Video", "video"), ("audio", "audio"), ("voice", "voice"), ("probing", "probe"),
    ("proportion", "share"), ("ratio", "share"), ("share", "share"), ("ratio", "ratio"), ("millisecond", "ms"),
    ("microseconds", "us"), ("nanoseconds", "ns"), ("Percentage", "pct"), ("per mille ratio", "permille"), ("per mille", "permille"),
    ("seconds", "sec"), ("count", "count"), ("count", "count"), ("quantity", "count"), ("each time", "per"), ("each", "per"),
    ("packet", "packets"), ("rate", "rate"), ("ratio", "ratio"),
]
_ZH.sort(key=lambda p: -len(p[0]))


def _build_lex():
    lex = {}
    for tag, words in _LEX_SRC.items():
        for w in words.split():
            wt = 1.0
            if ":" in w:
                w, wt = w.split(":")
                wt = float(wt)
            d = lex.setdefault(w, {})
            if tag != "_":
                d[tag] = max(d.get(tag, 0.0), wt)
    return lex


_LEX = _build_lex()
_WB_VOCAB = {w for w in list(_LEX) + list(_UNIT) if len(w) >= 3 and w.isalnum() and not w.startswith("qq")}
_WB_VOCAB |= {"rx", "ms", "us", "ns", "qd", "bw", "tx"}


def _known(tok):
    return tok in _LEX or tok in _UNIT


def _wordbreak(s):
    """Split an unseparated lowercase string into known words; return (characters covered, words), with unknown runs kept and prefixed by ~."""
    n = len(s)
    if n == 0:
        return 0, []
    best = [None] * (n + 1)
    best[0] = (0, 0, [])
    maxw = 16
    for i in range(n):
        if best[i] is None:
            continue
        cov, nw, seg = best[i]
        cand = (cov, nw - 1, seg + [("?", s[i])])
        if best[i + 1] is None or cand[:2] > best[i + 1][:2]:
            best[i + 1] = cand
        for j in range(i + 2, min(n, i + maxw) + 1):
            w = s[i:j]
            if w in _WB_VOCAB:
                cand = (cov + len(w), nw - 1, seg + [("w", w)])
                if best[j] is None or cand[:2] > best[j][:2]:
                    best[j] = cand
    cov, _, seg = best[n]
    words = []
    buf = ""
    for kind, w in seg:
        if kind == "?":
            buf += w
        else:
            if buf:
                words.append(buf)
                buf = ""
            words.append(w)
    if buf:
        words.append(buf)
    return cov, [w if w in _WB_VOCAB else "~" + w for w in words]


def _camel(run):
    r = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", run)
    r = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", r)
    r = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", r)
    r = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", r)
    return r.split()


def _piece_tokens(piece):
    """Tokenize one camel-case piece in its original case; return (characters covered, lowercase words)."""
    if piece == "B":
        return 1, ["qqbigb"]
    low = piece.lower()
    if _known(low) or low.isdigit():
        return len(low), [low]
    cov, words = _wordbreak(low)
    if cov >= 0.8 * len(low):
        return cov, words
    return 0, [low]


def _translate_cjk(s):
    if not re.search("[\u3400-\u9fff]", s):
        return s
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if "\u3400" <= ch <= "\u9fff":
            for zh, en in _ZH:
                if s.startswith(zh, i):
                    out.append(" " + en + " ")
                    i += len(zh)
                    break
            else:
                out.append(" ")
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


_TIME_RE = r"(?:s|sec|secs|second|seconds|ms|msec|millisecond|milliseconds|us|usec|microsecond|microseconds|ns)"


def tokenize(name):
    """Turn a field name into lowercase tokens, including unit placeholder tokens."""
    try:
        s = unicodedata.normalize("NFKC", str(name))
    except Exception:
        return []
    s = s.replace("μs", " us ").replace("µs", " us ").replace("μ", "u").replace("µ", "u")
    s = s.replace("%", " pct ").replace("‰", " permille ").replace("#", " num ")
    s = _translate_cjk(s)
    all_caps = not re.search(r"[a-z]", s)
    if not all_caps:
        for pat, rep in _CASE_UNITS:
            if "/" in pat:
                s = re.sub(r"(?<![A-Za-z])" + re.escape(pat) + r"(?![A-Za-z])", " " + rep + " ", s)
            else:
                left = r"(?:(?<![A-Za-z])|(?<=[a-z0-9]))" if pat[0].isupper() else r"(?<![A-Za-z])"
                right = r"(?![A-Za-z])" if pat[-1].isupper() else r"(?![a-z])"
                s = re.sub(left + re.escape(pat) + right, " " + rep + " ", s)
    s = re.sub(r"/\s*(?=" + _TIME_RE + r"(?![A-Za-z]))", " per ", s, flags=re.I)
    s = s.replace("/", " div ")
    s = re.sub(r"\s[-−–]\s", " minus ", s)
    s = s.replace("−", " minus ")
    toks = []
    for run in re.split(r"[^A-Za-z0-9]+", s):
        if not run:
            continue
        if all_caps:
            run_l = run.lower()
            if _known(run_l):
                toks.append(run_l)
                continue
            cov, words = _wordbreak(run_l)
            toks.extend(words if cov >= 0.8 * len(run_l) else [run_l])
            continue
        pieces = _camel(run)
        cam_cov, cam_toks = 0, []
        for p in pieces:
            c, t = _piece_tokens(p)
            cam_cov += c
            cam_toks.extend(t)
        low = run.lower()
        if _known(low):
            toks.append(low)
            continue
        wb_cov, wb_toks = _wordbreak(low)
        if wb_cov > cam_cov and wb_cov >= 0.8 * len(low):
            toks.extend(wb_toks)
        else:
            toks.extend(cam_toks)
    return [t for t in toks if t]


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def concepts(toks):
    c = {}

    def add(tag, w=1.0):
        c[tag] = max(c.get(tag, 0.0), w)

    for t in toks:
        for tag, w in _LEX.get(t, {}).items():
            add(tag, w)
    for a, b in zip(toks, toks[1:]):
        if a in ("one", "1") and b == "way":
            add("OWD")
        if a == "inter" and b in ("arrival", "arrivals", "packet", "packets", "pkt", "gap", "spacing", "time"):
            add("IAT")
        if a == "so" and b == "far":
            add("SOFAR")
        if a == "per" and b in ("event", "events", "burst", "bursts", "episode", "evt", "ev", "occurrence"):
            add("EVENT")
        if a in ("bit", "data") and b in ("rate", "rates"):
            add("RATE")
        if a in ("arrival", "arrivals", "arr") and b in ("gap", "interval", "spacing", "delta", "diff",
                                                         "difference", "time", "times", "period", "dt"):
            add("IAT")
        if a in ("time", "times") and b == "between":
            add("IAT")
        if a == "of" and b in ("total", "all"):
            add("SHARE")
    if "INTER" in c and ("ARRIVAL" in c or "TIME" in c or "INTERVAL" in c or "PKT" in c):
        add("IAT")
    if "ARRIVAL" in c and ("INTERVAL" in c or "EXCESS" in c):
        add("IAT")
    loss = "LOSS" in c
    delayish = any(k in c for k in ("DELAY", "OWD", "RTT", "QUEUE"))
    if "PROB" in c:
        add("SHARE" if loss else "PROBE", 1.0 if loss else 0.7)
    if "PROP" in c:
        add("BASE" if delayish else "SHARE")
    if "RUN" in c:
        add("EVENT" if loss else "SOFAR", 1.0 if loss else 0.5)
    if "LEN" in c and not loss and "EVENT" not in c:
        add("VOL", 0.5)
    if loss and "RATEW" in c:
        add("RATIO")
        c.pop("RATEW", None)
    if loss and "IAT" in c and not any(k in c for k in ("ARRIVAL", "INTER")):
        c.pop("IAT", None)
        add("EVENT", 0.6)
    if "TIME" in c and "PKT" in c and "INTERVAL" in c:
        add("IAT")
    if "INTERVAL" in c and not loss:
        add("IAT", 0.6)
    if ("SHARE" in c or "RATIO" in c) and not any(k in c for k in ("VIDEO", "AUDIO", "PROBE", "LOSS", "DELAY")):
        for t, tag, w in (("v", "VIDEO", 0.8), ("a", "AUDIO", 0.8), ("p", "PROBE", 0.6)):
            if t in toks:
                add(tag, w)
    return c


_PREFIX = {"kilo": "k", "k": "k", "mega": "m", "m": "m", "kibi": "ki", "ki": "ki", "milli": "milli",
           "micro": "micro", "u": "micro", "nano": "nano"}
_PREFIX_JOIN = {("k", "byte"): "kbyte", ("k", "bytes"): "kbytes", ("k", "bit"): "kbit", ("k", "bits"): "kbits",
                ("m", "byte"): "mbyte", ("m", "bytes"): "mbytes", ("m", "bit"): "mbit", ("m", "bits"): "mbits",
                ("ki", "byte"): "kib", ("ki", "bytes"): "kib", ("k", "b"): "kb", ("m", "b"): "mb",
                ("milli", "second"): "ms", ("milli", "seconds"): "ms", ("milli", "sec"): "ms", ("milli", "s"): "ms",
                ("micro", "second"): "us", ("micro", "seconds"): "us", ("micro", "sec"): "us", ("micro", "s"): "us",
                ("nano", "second"): "ns", ("nano", "seconds"): "ns", ("nano", "sec"): "ns", ("nano", "s"): "ns",
                ("k", "bps"): "kbps", ("m", "bps"): "mbps"}


def _merge_prefixes(toks):
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in _PREFIX and i + 1 < len(toks) and (_PREFIX[t], toks[i + 1]) in _PREFIX_JOIN:
            out.append(_PREFIX_JOIN[(_PREFIX[t], toks[i + 1])])
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def parse_units(toks):
    """Parse unit tokens into a dict with time (factor, strong), data ([(kind, factor)], strong), per (per-second factor) and frac (factor, strong)."""
    info = {}
    toks = _merge_prefixes(toks)
    n = len(toks)
    used = set()
    for i, t in enumerate(toks):
        u = _UNIT.get(t)
        if u is None:
            continue
        kind = u[0]
        if kind == "rate":
            info["data"] = (u[1], u[3])
            info["per"] = u[2]
            used.add(i)
        elif kind == "data":
            nxt = toks[i + 1] if i + 1 < n else None
            nxt2 = toks[i + 2] if i + 2 < n else None
            per = None
            if nxt is not None and _UNIT.get(nxt, ("",))[0] == "time":
                per = 1000.0 / _UNIT[nxt][1]
                used.add(i + 1)
            elif nxt in ("per", "p") and nxt2 is not None and _UNIT.get(nxt2, ("",))[0] == "time":
                per = 1000.0 / _UNIT[nxt2][1]
                used.add(i + 2)
            elif nxt in ("ps", "persec", "psec"):
                per = 1.0
                used.add(i + 1)
            if "data" not in info or u[2] or not info["data"][1]:
                info["data"] = (u[1], u[2])
            if per is not None:
                info["per"] = per
            used.add(i)
    for i, t in enumerate(toks):
        if i in used:
            continue
        u = _UNIT.get(t)
        if u is None:
            continue
        if u[0] == "time":
            prev = toks[i - 1] if i > 0 else None
            if prev == "per":
                info["per_time_only"] = 1000.0 / u[1]
                continue
            if "time" not in info or u[2] or not info["time"][1]:
                info["time"] = (u[1], u[2])
        elif u[0] == "frac":
            if "frac" not in info or (u[2] and not info["frac"][1]):
                info["frac"] = (u[1], u[2])
    if "data" in info and "per" not in info and "per_time_only" in info:
        info["per"] = info["per_time_only"]
    return info


def _snap(x):
    for a in ALLOWED:
        if abs(x / a - 1.0) < 1e-6:
            return a
    return None


def unit_candidates(info, k, c):
    """Return the scale candidates for feature k implied by the name's units and whether they are strong; ([], False) if there are none."""
    cands = []
    strong = True
    if k == 0:
        if "data" in info:
            per = info.get("per", 1.0)
            for kind, m in info["data"][0]:
                cands.append(m * (8.0 if kind == "byte" else 1.0) * per)
            strong = info["data"][1]
    elif k == 2:
        if "data" in info and "per" not in info:
            for kind, m in info["data"][0]:
                cands.append(m / 8.0 if kind == "bit" else m)
            strong = info["data"][1]
    elif k in TIME_F:
        if "time" in info:
            cands.append(1.0 * info["time"][0])
            strong = info["time"][1]
    elif k in FRAC_F or k in UNITLESS_RATIO_F:
        if "frac" in info:
            cands.append(info["frac"][0])
            strong = info["frac"][1]
        elif c.get("RATIO", 0) >= 0.9 or c.get("SHARE", 0) >= 0.9:
            cands.append(1.0)
            strong = False
    out = []
    for x in cands:
        a = _snap(x)
        if a is not None and a not in out:
            out.append(a)
    return out, (strong and len(out) == 1)


def name_dimension(info, c):
    if "data" in info:
        return "rate" if "per" in info else "volume"
    if "time" in info:
        return "time"
    if "frac" in info and info["frac"][0] != 1.0:
        return "fracunit"
    return None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def name_scores(name):
    toks = tokenize(name)
    c = concepts(toks)
    info = parse_units(toks)
    g = lambda *tags: max([c.get(t, 0.0) for t in tags] + [0.0])
    s = np.zeros(N_FEAT)

    video, audio, probe = g("VIDEO"), g("AUDIO"), g("PROBE")
    media = max(video, audio, probe)
    loss = g("LOSS")
    delay = max(g("DELAY", "OWD"), 0.8 * g("RTT"))
    queue = g("QUEUE")
    iat = g("IAT")
    jitter = g("JITTER")
    std = g("STD")
    ratio = g("RATIO")
    excess = g("EXCESS")
    minl = g("MIN")
    base = g("BASE")
    win = g("WIN")
    sofar = g("SOFAR")
    mean = g("MEAN")
    event = max(g("EVENT"), 0.8 * g("LEN") if loss else 0.0)
    share = g("SHARE")
    pkt = g("PKT")
    count = g("COUNT")
    vol = max(g("BYTE"), g("BIT"), g("VOL"))
    rate = g("RATE")
    ratew = g("RATEW")
    recv = g("RECV")
    dim = name_dimension(info, c)
    fracunit = "frac" in info

    s[12] += 9 * video
    s[13] += 9 * audio
    s[14] += 9 * probe

    if loss and not media:
        ratio_like = max(ratio, share, 1.0 if fracunit else 0.0)
        lostcnt = g("LOSTCNT")
        if event:
            s[11] += 8 * max(event, loss) * loss
            s[10] += 1
        elif ratio_like:
            s[10] += 8 * loss
            s[11] += 1
        elif lostcnt and (mean or pkt or count):
            s[11] += 6 * loss
            s[10] += 2 * loss
        elif mean or lostcnt:
            s[10] += 4 * loss
            s[11] += 4 * loss
        else:
            s[10] += 6 * loss
            s[11] += 2 * loss
    elif event and not media:
        s[11] += 4 * event

    if iat and not media:
        s[8] += 8 * iat
        if std:
            s[9] += 3 * std
    if not media and not loss:
        if jitter:
            s[9] += 9 * jitter
        elif std and (delay or queue):
            s[9] += 7 * std
        elif std and not iat:
            s[9] += 4 * std

    if queue and not media and not loss:
        s[3] += 8 * queue
        s[7] += 2 * queue
        if win and not sofar:
            s[7] += 5 * win
            s[3] -= 2 * win
        if ratio and not excess:
            s[6] += 4 * ratio

    core = delay and not (media or loss or jitter or iat or queue)
    if core or (not delay and (excess and (minl or base)) and not (media or loss or queue or iat)):
        d = delay if delay else 0.6
        minlike = max(minl, base)
        if ratio >= 0.9 or (ratio and not excess):
            s[6] += 8 * d * ratio
            if excess:
                s[7] += 2 * d
        elif excess:
            s[7] += 7 * d * excess
            s[3] += 4 * d * excess
            if (sofar or base) and not win:
                s[3] += 3 * max(sofar, base)
                s[7] -= 1
            if win:
                s[7] += 2 * win
                s[3] -= 2 * win
            if ratio:
                s[6] += 3 * ratio
        elif minlike:
            s[5] += 8 * d * minlike
            s[4] += 1
        elif g("MAX"):
            s[4] += 3 * d
            s[5] += 1
        else:
            s[4] += 6 * d + 2 * mean
            s[5] += 1
    elif delay and std and not (media or loss):
        pass
    elif not delay and ratio and not (media or loss or share) and not fracunit:
        s[6] += 3 * ratio
    elif not delay and (minl or base) and not (media or loss or vol or pkt or rate or ratew):
        s[5] += 3 * max(minl, base)

    blocked = media or loss or delay or queue or iat or jitter
    if not blocked:
        if rate:
            s[0] += 8 * rate
        if ratew and not pkt:
            s[0] += 6 * ratew
        elif ratew and pkt:
            s[0] += 3
            s[1] += 3
        if dim == "rate":
            s[0] += 4
        if pkt and not (vol or rate or (ratew and not count)):
            s[1] += 7 * pkt + 1 * count + 0.5 * recv
        elif count and not (vol or rate or ratew):
            s[1] += 3 * count
        if (vol or dim == "volume") and not (rate or ratew or dim == "rate"):
            s[2] += 7 * max(vol, 1.0 if dim == "volume" else 0.0) + 0.5 * recv
        if recv and not (pkt or vol or rate or ratew or count or dim):
            s[0] += 1
            s[1] += 1
            s[2] += 1
        if vol and (rate or ratew) and dim != "rate" and not pkt:
            s[0] += 1
    if dim == "time":
        for k in range(N_FEAT):
            s[k] += 2 if k in TIME_F else -4
    elif dim == "rate":
        for k in range(N_FEAT):
            s[k] += 2 if k == 0 else -4
    elif dim == "volume":
        for k in range(N_FEAT):
            if k == 2:
                s[k] += 2
            elif k == 0:
                s[k] += 0 if (rate or ratew) else -2
            else:
                s[k] -= 4
    elif dim == "fracunit":
        for k in range(N_FEAT):
            s[k] += 1 if (k in FRAC_F or k in UNITLESS_RATIO_F) else -4
    return s, info, c, toks


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _prior(k):
    if k == 0:
        p = {1.0: 0.0, 1000.0: 0.2, 1e6: 0.4, 8.0: 0.4, 1024.0: 1.2, 0.001: 1.5}
    elif k == 1:
        p = {1.0: 0.0, 1000.0: 1.5}
    elif k == 2:
        p = {1.0: 0.0, 0.125: 0.4, 1000.0: 0.4, 1024.0: 0.8, 125.0: 0.8, 1e6: 0.8}
    elif k in TIME_F:
        p = {1.0: 0.0, 1000.0: 0.2, 0.001: 0.3, 1e-6: 1.0}
    elif k == 6:
        p = {1.0: 0.0, 0.01: 0.4, 0.001: 1.5}
    elif k in FRAC_F:
        p = {1.0: 0.0, 0.01: 0.2, 0.001: 0.6, 1e-6: 1.5}
    else:
        p = {1.0: 0.0}
    return {a: p.get(a, 2.5) for a in ALLOWED}


_PRIORS = [_prior(k) for k in range(N_FEAT)]


def _vec(st):
    """Turn a stats entry into a 10-vector (5 short-window, then 5 long-window quantiles); return None on bad input."""
    try:
        if isinstance(st, dict):
            sh = st.get("short", st.get("s"))
            lo = st.get("long", st.get("l"))
            if sh is None and lo is None:
                return None
            sh = list(sh) if sh is not None else list(lo)
            lo = list(lo) if lo is not None else list(sh)
            v = np.array([float(x) if x is not None else np.nan for x in sh[:5] + lo[:5]], float)
        else:
            v = np.array([float(x) if x is not None else np.nan for x in st], float).ravel()
        if v.size == 0:
            return None
        if v.size < 10:
            v = np.resize(v, 10)
        v = v[:10]
        if np.all(~np.isfinite(v)):
            return None
        fill = np.nanmedian(v[np.isfinite(v)])
        v = np.where(np.isfinite(v), v, fill)
        return v
    except Exception:
        return None


def _ls_ratio(v):
    """Return the median log10 ratio of long to short window quantiles (25th, 50th, 75th), which separates per-window counts from rates."""
    sh, lo = v[:5], v[5:]
    r = [math.log10(lo[i] / sh[i]) for i in (1, 2, 3) if sh[i] > 0 and lo[i] > 0]
    return float(np.median(r)) if r else None


class _Ref:
    def __init__(self, ref):
        self.v = []
        self.tau = []
        self.ls = []
        for k in range(N_FEAT):
            st = None
            if isinstance(ref, dict):
                st = ref.get(str(k), ref.get(k))
            elif isinstance(ref, (list, tuple)) and k < len(ref):
                st = ref[k]
            v = _vec(st) if st is not None else None
            self.v.append(v)
            if v is not None:
                nz = np.abs(v[np.abs(v) > 0])
                tau = 0.05 * float(np.median(nz)) if nz.size else 1e-3
                self.tau.append(max(tau, 1e-9))
                self.ls.append(_ls_ratio(v))
            else:
                self.tau.append(1.0)
                self.ls.append(None)


def _T(x, tau):
    return np.arcsinh(x / tau) / math.log(10.0)


def dist_cost(x, k, a, R):
    """Return the distance in decades between field quantiles x times scale a and the reference quantiles of feature k."""
    r = R.v[k]
    if r is None or x is None:
        return 0.0
    tau = R.tau[k]
    y = a * x
    d = float(np.mean(np.abs(_T(y, tau) - _T(r, tau))))
    # Scale term on the largest quantile: mostly-zero features (loss, shares) show their scale only in the upper tail.
    my, mr = float(np.max(np.abs(y))), float(np.max(np.abs(r)))
    if my > 0 and mr > 0:
        d += W_MAX * min(abs(math.log10(my / mr)), 3.0)
    if k in OFFSET_F:
        d *= 0.5
    if k in FRAC_F:
        mx = float(np.max(y))
        if mx > 1.02:
            d += 1.5 + math.log10(mx)
    return d


def invariant_cost(x, k, R):
    """Return scale-free penalties: negative values outside features 4 and 5, long/short ratio mismatch and share of zeros."""
    if x is None or R.v[k] is None:
        return 0.0
    c = 0.0
    scale = float(np.max(np.abs(x))) or 1.0
    neg = x < -1e-9 * scale
    if neg.any() and k not in OFFSET_F:
        c += 2.0 + 3.0 * float(np.mean(neg))
    a, b = _ls_ratio(x), R.ls[k]
    if a is not None and b is not None and k not in OFFSET_F:
        c += W_LS * min(abs(a - b), 1.5)
    # The share of exact zeros is scale-free: loss and probe shares are mostly zero, small delays in seconds rarely are.
    c += W_ZERO * abs(float(np.mean(x == 0)) - float(np.mean(R.v[k] == 0)))
    return c


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _get_stat(stats, j, name):
    try:
        if isinstance(stats, dict):
            for key in (j, str(j), name):
                if key in stats:
                    return stats[key]
            return None
        return stats[j]
    except Exception:
        return None


def score_tables(names, stats, ref):
    names = list(names) if names is not None else []
    n = len(names)
    R = _Ref(ref)
    N = np.zeros((N_FEAT, n))
    D = np.zeros((N_FEAT, n))
    A = np.ones((N_FEAT, n))
    FIXED = np.zeros((N_FEAT, n), bool)
    for j, nm in enumerate(names):
        try:
            s, info, c, toks = name_scores(nm)
        except Exception:
            s, info, c = np.zeros(N_FEAT), {}, {}
        N[:, j] = s
        x = _vec(_get_stat(stats, j, nm))
        for k in range(N_FEAT):
            try:
                cands, strong = unit_candidates(info, k, c)
            except Exception:
                cands, strong = [], False
            inv = invariant_cost(x, k, R)
            best, besta = float("inf"), 1.0
            mistrust = (STRONG_MISTRUST if strong else WEAK_MISTRUST) if cands else 0.0
            for a in ALLOWED:
                if a in cands:
                    pen = 0.0
                else:
                    pen = _PRIORS[k][a] + mistrust
                d = dist_cost(x, k, a, R) + pen
                if d < best - 1e-12:
                    best, besta = d, a
            D[k, j] = best + inv
            A[k, j] = besta
            FIXED[k, j] = bool(cands) or (x is not None and float(np.max(np.abs(x))) > 0)
    return N, D, A, FIXED


def match(names, stats, ref):
    try:
        names = list(names) if names is not None else []
    except Exception:
        names = []
    n = len(names)
    if n == 0:
        return [{"source": 0, "scale": 1.0} for _ in range(N_FEAT)]
    N, D, A, FIXED = score_tables(names, stats, ref)
    C = -N + W_DIST * D
    m = max(N_FEAT, n)
    big = float(np.max(np.abs(C))) * 4 + 100.0
    Csq = np.full((m, m), big)
    Csq[:N_FEAT, :n] = C
    if n > N_FEAT:
        Csq[N_FEAT:, :] = 0.0
    rows, cols = assign_min(Csq)
    out = []
    for k in range(N_FEAT):
        j = int(cols[k])
        if j >= n:
            j = int(np.argmin(C[k]))
        out.append({"source": j, "scale": float(A[k, j])})
    # Fraction fields with all-zero data and no unit in the name borrow the most common scale of the client's other fraction fields.
    fixed = [out[k]["scale"] for k in FRAC_F if out[k]["source"] < n and FIXED[k, out[k]["source"]]]
    if fixed:
        vals, cnts = np.unique(np.array(fixed), return_counts=True)
        mode = float(vals[np.argmax(cnts)])
        for k in FRAC_F:
            j = out[k]["source"]
            if j < n and not FIXED[k, j]:
                out[k]["scale"] = mode
    return out


if __name__ == "__main__":
    import sys
    for nm in sys.argv[1:]:
        s, info, c, toks = name_scores(nm)
        print(nm, toks, {k: round(v, 2) for k, v in c.items()}, info)
        print("   ", np.round(s, 1))
