#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The rt_getstats foreign schema (obsschema-closedloop-llm4bandpp-v1), built on the naming and unit conventions of WebRTC getStats and webrtc-internals.
Field names carry the stats type prefix (inbound-rtp, transport), times are in seconds (as jitter and roundTripTime in getStats), loss is a fraction from 0 to 1, and the rate follows the webrtc-internals quantity bytesReceived_in_bits/s.
The fields still mean the 15 interface features; they are not data exported by a real client (real getStats values are mostly cumulative counters that need differencing, beyond per-field scaling). All factors are within obsschema_v1.FACTORS, which keeps the comparison fair to the statistical methods.
Importing this module adds rt_getstats to obsschema_v1.SCHEMAS (append only, existing schemas unchanged).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsschema_v1 as S  # noqa: E402

RT = [("inbound-rtp.bytesReceived_in_bits/s", 1), ("inbound-rtp.packetsReceived", 1), ("inbound-rtp.bytesReceived", 1), ("transport.queuingDelay", 1e-3),
      ("inbound-rtp.oneWayDelay", 1e-3), ("inbound-rtp.minOneWayDelay", 1e-3), ("inbound-rtp.oneWayDelayToMinRatio", 1), ("inbound-rtp.oneWayDelayAboveMin", 1e-3),
      ("inbound-rtp.packetInterArrivalTime", 1e-3), ("inbound-rtp.jitter", 1e-3), ("inbound-rtp.packetsLostFraction", 1), ("inbound-rtp.packetsLostPerLossEvent", 1),
      ("inbound-rtp[kind=video].packetFraction", 1), ("inbound-rtp[kind=audio].packetFraction", 1), ("transport.probePacketFraction", 1)]
assert len(RT) == 15 and all(f in S.FACTORS for _, f in RT)
S.SCHEMAS.setdefault("rt_getstats", RT); S.PHASE.setdefault("rt_getstats", "test_rt")
