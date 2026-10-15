# -*- coding: utf-8 -*-
"""Build field_transcription.json and field_transcription.md for the 12 held-out client stacks of the designer scale test (realtel-scale-v1: the 12-stack rows of Table IV, Fig. 3(a))
and check every quote and field name against the cached official documents in raw/. raw/ holds the documents that may be redistributed; data/real_telemetry_specs_raw_NOTICE.md
lists the URLs of the others, which a full rerun of the check needs.
Version 2 of the transcriptions: a new builder for new sources (data/real_telemetry_specs_v1/build.py covers the seven specifications of realtel-adapter-v1) that adds the quote
check and records for each feature the relation (same quantity, same kind with another definition, none), with diff and scale.
"""
import json, os, re, html, glob
from bs4 import BeautifulSoup

OUT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(OUT, 'raw')

SAME, SIM, NONE = 'same quantity', 'different definition', 'none'
NF = 'not found'

def F(name, context, unit, cum, rel, quote, url, reason, diff=None, scale=None):
    word, _, basis = cum.partition(',')
    assert word in ('cumulative', 'interval', 'instantaneous', 'per event', 'not applicable'), cum
    if basis:
        reason = reason + f'Regarding the judgment on {word}, {basis}.'
    d = dict(name=name, context=context, unit=unit, cumulative=word, relation=rel,
             quote=quote, url=url, reason=reason)
    if rel == SAME:
        assert diff is not None and scale is not None, name
        d['diff'] = diff
        d['scale'] = scale
    return d

def NOF(url, reason):
    return F(NF, 'n/a', 'not applicable', 'not applicable', NONE, '', url, reason)

S = {}   # source name -> dict
PREFIX = {}

# ---------------------------------------------------------------- 1 Agora
AG = 'https://api-ref.agora.io/en/video-sdk/web/4.x/interfaces/'
AGV, AGA, AGC, AGN = AG + 'remotevideotrackstats.html', AG + 'remoteaudiotrackstats.html', AG + 'agorartcstats.html', AG + 'networkquality.html'
td_q = 'The delay (ms) between a remote client sending the video and the local client receiving the video.'
td_ctx = 'RemoteVideoTrackStats (AgoraRTCClient.getRemoteVideoStats); RemoteAudioTrackStats has the same field'
S['Agora Web SDK'] = dict(
    header='Agora Web SDK, statistics of remote video and audio tracks and of the call on the receiving side, polled periodically',
    status='kept', reason_if_dropped='',
    features={
        '0': F('RecvBitrate', 'AgoraRTCStats (AgoraRTCClient.getRTCStats)', 'bps, original text states "bitrate (bps)"', 'instantaneous', SAME,
               'The total bitrate (bps) of the received audio and video, represented by an instantaneous value.', AGC + '#recvbitrate',
               'All audio and video bitrate received by this end; the original text says it is an instantaneous value and does not state how long the statistical window is, so different window lengths are acceptable under the definition. The single-track RemoteVideoTrackStats.receiveBitrate counts video only and is less close than this field.', False, 1),
        '1': F('receivePackets', 'RemoteAudioTrackStats / RemoteVideoTrackStats', 'Packets, audio track original text says "total packets"', 'cumulative', SAME,
               'The total packets of the received audio.', AGA + '#receivepackets',
               'For the per-track cumulative received packet count, subtracting two readings gives the received packet count within the window, covering only this one track. The description of the video track field with the same name is written as "The total bytes of the received video.", which does not match the field name; it looks like a documentation typo, and here the original text of the audio track is taken as authoritative.', True, 1),
        '2': F('RecvBytes', 'AgoraRTCStats (AgoraRTCClient.getRTCStats)', 'bytes, original text "total number of bytes"', 'cumulative', SAME,
               'The total number of bytes received, represented by an aggregate value.', AGC + '#recvbytes',
               'Total bytes received over the entire call; the source states it is a cumulative value, so subtracting two readings gives the bytes within the window.', True, 1),
        '3': F('transportDelay', td_ctx, 'ms, original text "Transmission delay (ms)"', 'instantaneous', SIM, td_q, AGV + '#transportdelay',
               'This is the one-way delay from when the sender sends it to when this end receives it; the original text does not say whether it is the average within a window or a single measurement. The queuing delay also requires subtracting the minimum delay so far, so the historical minimum must be tracked manually.'),
        '4': F('transportDelay', td_ctx, 'ms, original text "Transmission delay (ms)"', 'instantaneous', SIM, td_q, AGV + '#transportdelay',
               'One-way transmission delay, the quantity is correct, but it must be averaged over the window and then have the fixed 200 ms baseline subtracted; subtracting a constant is not a unit conversion, so it is labelled a different definition.'),
        '5': F('transportDelay', td_ctx, 'ms, original text "Transmission delay (ms)"', 'instantaneous', SIM, td_q, AGV + '#transportdelay',
               'The SDK does not provide a minimum delay; the minimum of successive transportDelay readings must be tracked manually.'),
        '6': F('transportDelay', td_ctx, 'ms, original text "Transmission delay (ms)"', 'instantaneous', SIM, td_q, AGV + '#transportdelay',
               'Each reading gives only one delay value; the in-window minimum must be approximated from multiple readings within the window, and a per-packet minimum cannot be obtained. Whether it can be labelled a different definition is disputed; it is labelled a different definition by measure.'),
        '7': F('transportDelay', td_ctx, 'ms, original text "Transmission delay (ms)"', 'instantaneous', SIM, td_q, AGV + '#transportdelay',
               'Same as feature 6, both the window mean and the window minimum must be approximated from multiple readings, disputed, judged same quantity.'),
        '8': F('receivePackets', 'RemoteVideoTrackStats / RemoteAudioTrackStats', 'packet', 'cumulative', SIM,
               'The total packets of the received audio.', AGA + '#receivepackets',
               'There is no inter-arrival field. The window length divided by the number of packets received within the window approximates the average inter-arrival time, which is an averaging operation.'),
        '9': F('downlinkNetworkQuality', 'NetworkQuality (AgoraRTCClient.on("network-quality"), every two seconds)', 'level 0 to 6, dimensionless', 'instantaneous', NONE,
               'It is calculated based on the downlink transmission bitrate, downlink packet loss rate, RTT (round-trip time) and jitter.', AGN + '#downlinknetworkquality',
               'There is no jitter field in the receiver statistics. The description of this downlink quality level mentions jitter, which is easily mistaken for jitter, but it only gives a composite level from 0 to 6 and no jitter value can be extracted, so it does not count.'),
        '10': F('currentPacketLossRate', 'RemoteVideoTrackStats (also RemoteAudioTrackStats)', 'the original text does not state the unit or value range', 'interval', SIM,
                'The packet loss rate of the received video in 400ms.', AGV + '#currentpacketlossrate',
                'The video packet loss rate within a 400 ms window at the receiver is by definition the packet loss rate within the window. But the original text does not state whether the value is 0 to 1 or a percentage; on the same page freezeRate is written as [0.0,1.0], this field is not, so the conversion factor cannot be determined, and per the dispute it is judged same quantity. It only covers a single track.'),
        '11': F('receivePacketsLost', 'RemoteVideoTrackStats / RemoteAudioTrackStats', 'packet', 'cumulative', NONE,
                'The total number of lost video packets that should be received.', AGV + '#receivepacketslost',
                'Only the cumulative number of lost packets, no count of loss events, so the average number of packets lost per loss event cannot be computed. Similar name, listed for reference.'),
        '12': F('receivePackets', 'RemoteVideoTrackStats (video) combined with RemoteAudioTrackStats', 'packet', 'cumulative', SIM,
                'The total bytes of the received video.', AGV + '#receivepackets',
                'The video packet proportion is obtained only by dividing the difference in received packet count of the video track by the sum of the differences in received packet counts of the video track and the audio track; it is a multi-field combination. The quotation is the original description of the video track receivePackets, written as bytes, see the note for feature 1.'),
        '13': F('receivePackets', 'RemoteAudioTrackStats (audio) combined with RemoteVideoTrackStats', 'packet', 'cumulative', SIM,
                'The total packets of the received audio.', AGA + '#receivepackets',
                'The difference in received packet count of the audio track divided by the sum of the differences in received packet counts of the audio and video tracks; a multi-field combination.'),
        '14': NOF(AGV, 'The remote track statistics, call statistics, and network quality interfaces contain no probing packet related fields.'),
    })
PREFIX['Agora Web SDK'] = 'agora_'

# ---------------------------------------------------------------- 2 Twilio
TW = 'https://sdk.twilio.com/js/video/releases/2.36.0/docs/'
TWRR = 'https://github.com/twilio/twilio-video.js/blob/master/lib/stats/receiverreport.js'
cum_tw = 'cumulative, Not documented; based on the SDK source lib/stats/receiverreport.js, bitrate and received packet count are computed from the difference of two readings'
rtt_ctx = 'LocalTrackStats (LocalAudioTrackStats / LocalVideoTrackStats in StatsReport)'
rtt_q = 'Round trip time in milliseconds'
S['Twilio Video JS'] = dict(
    header='Twilio Video JavaScript SDK, track statistics returned by Room.getStats() on a client that subscribes to remote audio and video tracks, polled periodically',
    status='kept', reason_if_dropped='',
    features={
        '0': F('bytesReceived', 'RemoteTrackStats (RemoteVideoTrackStats / RemoteAudioTrackStats)', 'bytes, original text "Number of bytes received"', cum_tw, SIM,
               'Number of bytes received', TW + 'RemoteTrackStats.html',
               'The track statistics do not contain the received bitrate; it must be computed as the byte difference between two readings divided by the timestamp difference and then multiplied by 8, which is a rate computation. NetworkQualityBandwidthStats.actual says "the actual bandwidth used, in bits per second", but it belongs to a network quality event, and the documentation does not say where or over what window it is computed, so it is not selected.'),
        '1': F('packetsReceived', 'RemoteTrackStats (RemoteVideoTrackStats / RemoteAudioTrackStats)', 'Packets, original text "Number of packets received"', cum_tw, SAME,
               'Number of packets received', TW + 'RemoteTrackStats.html',
               'The per-track received packet count is a cumulative count; subtracting two readings gives the received packet count within the window, covering only a single track.', True, 1),
        '2': F('bytesReceived', 'RemoteTrackStats (RemoteVideoTrackStats / RemoteAudioTrackStats)', 'bytes', cum_tw, SAME,
               'Number of bytes received', TW + 'RemoteTrackStats.html',
               'The per-track cumulative received bytes; subtracting two readings gives the bytes within the window.', True, 1),
        '3': F('roundTripTime', rtt_ctx, 'ms, original text "in milliseconds"', 'instantaneous', SIM, rtt_q, TW + 'LocalTrackStats.html',
               'There is no delay field in the receive track statistics, only the round-trip delay of the locally published track, which is in the send direction and computed from peer feedback. Queueing delay also requires tracking the historical minimum and subtracting.'),
        '4': F('roundTripTime', rtt_ctx, 'ms, original text "in milliseconds"', 'instantaneous', SIM, rtt_q, TW + 'LocalTrackStats.html',
               'round trip rather than one way, and it belongs to the local send direction track, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('roundTripTime', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, TW + 'LocalTrackStats.html',
               'There is no minimum delay field; the minimum must be tracked by oneself from the round-trip time readings, and the definition is also round-trip.'),
        '6': F('roundTripTime', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, TW + 'LocalTrackStats.html',
               'Each reading gives only one round-trip delay; the in-window minimum can only be approximated from multiple readings, and it is again a round-trip measure, which is disputed, so it is labelled a different definition.'),
        '7': F('roundTripTime', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, TW + 'LocalTrackStats.html',
               'Same feature 6; disputed; labelled a different definition.'),
        '8': F('packetsReceived', 'RemoteTrackStats', 'packet', cum_tw, SIM, 'Number of packets received', TW + 'RemoteTrackStats.html',
               'There is no inter-arrival field; the window length divided by the number of packets received within the window approximates the average inter-arrival time, which is averaging.'),
        '9': F('jitter', 'RemoteTrackStats', 'ms, original text "Jitter in milliseconds"', 'instantaneous', SIM, 'Jitter in milliseconds', TW + 'RemoteTrackStats.html',
               'The documentation gives only the unit, not the algorithm. The SDK source getstats.js computes it by multiplying the browser statistic jitter by 1000 and truncating, not the standard deviation of within-window arrival intervals, labelled a different definition.'),
        '10': F('packetsLost', 'TrackStats (inherited by RemoteTrackStats)', 'Packets, original text "The number of packets lost"', cum_tw, SIM,
                'The number of packets lost', TW + 'TrackStats.html',
                'There is no ready-made packet loss rate; it requires the packet loss count difference divided by the sum of the packet loss count difference and the received packet count difference, which is a multi-field combination. NetworkQualityFractionLostStats.fractionLost only writes "packets lost", and neither the value range nor the calculation location is written, so it is not selected.'),
        '11': F('packetsLost', 'TrackStats', 'packet', cum_tw, NONE, 'The number of packets lost', TW + 'TrackStats.html',
                'Only the cumulative number of lost packets, no count of loss events, so the average number of packets lost per event cannot be computed. Similar name, listed for reference.'),
        '12': F('packetsReceived', 'StatsReport.remoteVideoTrackStats[] combined with remoteAudioTrackStats[]', 'packet', cum_tw, SIM,
                'List of RemoteVideoTrackStats', TW + 'StatsReport.html',
                'The report splits the video track and audio track into two lists; the difference in received packet count for the video track divided by the sum of the received packet count differences for all tracks gives the video packet proportion, a multi-field combination.'),
        '13': F('packetsReceived', 'StatsReport.remoteAudioTrackStats[] combined with remoteVideoTrackStats[]', 'packet', cum_tw, SIM,
                'List of RemoteAudioTrackStats', TW + 'StatsReport.html',
                'The difference in received packet count of the audio track divided by the sum of the differences in received packet counts of all tracks; a multi-field combination.'),
        '14': NOF(TW + 'RemoteTrackStats.html', 'Neither the track statistics nor the network quality statistics contain any probing packet related fields.'),
    })
PREFIX['Twilio Video JS'] = 'twilio_'

# ---------------------------------------------------------------- 3 Daily
DY = 'https://docs.daily.co/reference/daily-js/instance-methods/get-network-stats'
lat = 'DailyNetworkStats.stats.latest'
rtt_q = 'Average round trip time across all connections.'
rtt_u = 'Not stated in the source; inferred as seconds from the example return value 0.02'
cum_lat = 'interval, original text "the most recent reporting interval (~2s)"'
S['Daily (daily-js)'] = dict(
    header="Daily (daily-js), network statistics returned by getNetworkStats() on a call participant's client, polled periodically",
    status='kept', reason_if_dropped='',
    features={
        '0': F('recvBitsPerSecond', lat, 'bit/s, original text "bits per second"', cum_lat, SAME, 'Total incoming bits per second (audio + video).', DY,
               'The total audio and video bitrate received by this end in the most recent approximately 2-second statistics interval, which is the receive rate; a different interval length is acceptable.', False, 1),
        '1': NOF(DY, 'Only bitrate, packet loss, round-trip time, and jitter are given; there is no received packet count field.'),
        '2': F('recvBitsPerSecond', lat, 'bit/s', cum_lat, SIM, 'Total incoming bits per second (audio + video).', DY,
               'There is no byte count; the bitrate must be multiplied by the interval duration and then divided by 8, and the interval duration can be obtained from the difference of two timestamps, not by multiplying a constant.'),
        '3': F('networkRoundTripTime', lat, rtt_u, cum_lat, SIM, rtt_q, DY,
               'Only round-trip time, and it is averaged over all connections. Queueing delay also requires tracking the historical minimum and subtracting, and the definition is not one-way either.'),
        '4': F('networkRoundTripTime', lat, rtt_u, cum_lat, SIM, rtt_q, DY,
               'round trip rather than one way, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('networkRoundTripTime', lat, rtt_u, cum_lat, SIM, rtt_q, DY,
               'There is no minimum delay field; the minimum must be tracked by oneself from the round-trip time readings. averageNetworkRoundTripTime is the overall average, and is also not the minimum.'),
        '6': F('networkRoundTripTime', lat, rtt_u, cum_lat, SIM, rtt_q, DY,
               'One round-trip time mean about every 2 seconds; the minimum within the window can only be approximated from multiple readings; disputed; labelled a different definition.'),
        '7': F('networkRoundTripTime', lat, rtt_u, cum_lat, SIM, rtt_q, DY, 'Same feature 6; disputed; labelled a different definition.'),
        '8': NOF(DY, 'There is neither packet count nor arrival time, so the average inter-arrival time cannot be derived.'),
        '9': F('videoRecvJitter', lat, 'Not stated in the source; inferred as seconds from the example return value 0.036', cum_lat, SIM, 'Average jitter across inbound video streams.', DY,
               'It is the average of the jitter of each inbound video stream; the algorithm follows the WebRTC statistic and is not written as the standard deviation of arrival intervals; audioRecvJitter is also given separately for audio. labelled a different definition.'),
        '10': F('totalRecvPacketLoss', lat, 'The audio and video sub-items say "packet loss percentage" in the original text, but the example value is 0.1167, so the units conflict', cum_lat, SIM,
                'Overall estimated packet loss for all incoming media.', DY,
                'The inbound packet loss per reporting interval at the receiver is correct in quantity. But the subfield says it is a percentage, while the example values look like a ratio from 0 to 1, so the conversion factor cannot be pinned down, and the source also uses estimated, so it is labelled a different definition by dispute.'),
        '11': NOF(DY, 'There is no field for the number of loss events or the length of consecutive losses.'),
        '12': F('videoRecvBitsPerSecond', lat, 'bit/s', cum_lat, SIM, 'Incoming video payload bits per second.', DY,
                'One can only divide the video bitrate by the total bitrate to get a bit-based proportion, not a packet-based proportion; the definitions differ, it is disputed, labelled a different definition.'),
        '13': F('audioRecvBitsPerSecond', lat, 'bit/s', cum_lat, SIM, 'Incoming audio payload bits per second.', DY,
                'Same feature 12; only the bit-based audio ratio can be obtained; labelled a different definition.'),
        '14': NOF(DY, 'There are no probing packet related fields.'),
    })
PREFIX['Daily (daily-js)'] = 'daily_'

# ---------------------------------------------------------------- 4 Jitsi
JSHA = '7afa6544e90516ce68d06f5bd64af01779d8d02f'
JR = f'https://github.com/jitsi/lib-jitsi-meet/blob/{JSHA}/modules/statistics/RTPStatsCollector.js'
cs = 'StatisticsEvents.CONNECTION_STATS payload (also copied into ConnectionQuality local stats)'
cum_js = 'interval, Between two adjacent getStats polls'
br_q = 'bitrateKbps = Math.round((bytesProcessed * 8) / timeMs);'
rtt_q = 'rtt: now.currentRoundTripTime * 1000,'
rtt_ctx = 'CONNECTION_STATS payload, transport[] entry (also jvbRTT in ConnectionQuality local stats)'
S['Jitsi (lib-jitsi-meet)'] = dict(
    header='lib-jitsi-meet (Jitsi Meet client library), connection statistics emitted by its statistics module on a conference participant\'s client',
    status='kept', reason_if_dropped='',
    features={
        '0': F('bitrate.download', cs, 'kbps, based on source bytesProcessed*8/timeMs, bytes times 8 divided by milliseconds', cum_js, SAME, br_q, JR,
               'This end takes the bytesReceived difference between two adjacent polls for all inbound-rtp streams, divides by the time difference to obtain the downlink bitrate in kbps, and multiplying by 1000 gives bps. bandwidth.download is an available bandwidth estimate, not the measured receive rate, so it is not selected.', False, 1000),
        '1': F('packetsTotal', 'SsrcStats.loss (internal state of StatsCollector, not emitted)', 'packet', cum_js, SIM,
               'packetsTotal: packetsDiff + packetsLostDiff', JR,
               'the external event has no received packet count. The internal packetsTotal is the number of received packets plus the number of lost packets between two polls, that is, the expected number of packets, and it is also an internal variable; the actual received packet count packetsDiff is only a local variable. Both reasons point to the same quantity.'),
        '2': F('bitrate.download', cs, 'kbps', cum_js, SIM, br_q, JR,
               'the number of bytes is not sent externally; it must be inferred by multiplying the downlink bitrate by 1000, then by the polling interval, and dividing by 8, not by multiplying a constant.'),
        '3': F('rtt', rtt_ctx, 'ms, based on the source code currentRoundTripTime * 1000', 'instantaneous', SIM, rtt_q, JR,
               'This is the current round-trip delay of the ICE candidate pair, obtained from STUN checks, not the one-way delay of media packets. The queuing delay also requires tracking the minimum value and then subtracting it.'),
        '4': F('rtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, JR, 'round trip rather than one way, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('rtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, JR, 'There is no minimum delay field; the minimum must be tracked by oneself from the round-trip time readings.'),
        '6': F('rtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, JR, 'Each poll gives only one round-trip delay; the in-window minimum can only be approximated from multiple readings, which is disputed, so it is labelled a different definition.'),
        '7': F('rtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, JR, 'Same feature 6; disputed; labelled a different definition.'),
        '8': F('packetsTotal', 'SsrcStats.loss (internal, not emitted)', 'packet', cum_js, SIM, 'packetsTotal: packetsDiff + packetsLostDiff', JR,
               'The polling interval divided by the expected packet count can only roughly approximate the average arrival interval, and it is an internal variable, which is disputed, so it is judged as the same quantity.'),
        '9': NOF(JR, 'The statistics module neither reads nor emits jitter, and the connection quality module does not have it either.'),
        '10': F('packetLoss.download', cs, 'Percentage rounded, based on source code Math.round(... * 100)', cum_js, SAME,
                'return Math.round(lostPackets / totalPackets * 100);', JR,
                'For all downlink streams, divide the lost packet count difference between two polls by the received packet count difference plus the lost packet count difference; this is exactly the in-window loss rate, multiply by 0.01 to convert to a ratio from 0 to 1, with precision only to 1%.', False, 0.01),
        '11': NOF(JR, 'It is computed internally only as the number of lost packets between two polls; there is no loss event count, and it is not emitted externally either.'),
        '12': F('bitrate.video.download', cs, 'kbps', cum_js, SIM, 'videoBitrateDownload += ssrcBitrateDownload;', JR,
                'Splitting the downlink bitrate into audio and video by track type only yields the video proportion by bits, not the proportion by packets; this is disputed, judged as same quantity.'),
        '13': F('bitrate.audio.download', cs, 'kbps', cum_js, SIM, 'audioBitrateDownload += ssrcBitrateDownload;', JR,
                'Same feature 12; only the bit-based audio ratio can be obtained; labelled a different definition.'),
        '14': NOF(JR, 'There are no probing packet related fields.'),
    })
PREFIX['Jitsi (lib-jitsi-meet)'] = 'jitsi_'

# ---------------------------------------------------------------- 5 mediasoup
MD = 'https://mediasoup.org/documentation/v3/mediasoup/rtc-statistics/'
MSG = 'https://github.com/versatica/mediasoup/blob/v3/'
tctx = 'WebRtcTransport.getStats() (same field in PlainTransport / PipeTransport / DirectTransport stats)'
pctx = 'Producer.getStats() entry with type "inbound-rtp" (one per RTP stream received)'
rtt_q = 'this->rttMs > 0.0f ? this->rttMs : 0,'
rtt_u = 'ms, based on the source code field name rttMs and the conversion CompactNtpRttToTimeUs(...) / 1000'
S['mediasoup v3'] = dict(
    header='mediasoup v3 (server-side SFU library), statistics returned by getStats() of a transport and of the producers whose RTP streams it receives from an endpoint, polled periodically',
    status='kept', reason_if_dropped='',
    features={
        '0': F('recvBitrate', tctx, 'bps, the documentation only gives example values; based on the source RateCalculator default scale 8000, that is, bytes per millisecond multiplied by 8000', 'interval, default 1000 ms sliding window', SAME,
               'static_cast<uint64_t>(this->recvTransmission.GetRate(nowMs).value_or(0)),', MSG + 'worker/src/RTC/Transport.cpp',
               'The receive bitrate computed by the transport layer over all data received, with the window taken as the RateCalculator default of 1000 ms, which after unit conversion is bps. The official documentation lists only example JSON with no field descriptions, so the unit and window are taken from the official source code.', False, 1),
        '1': F('packetCount', pctx, 'packet', 'cumulative, based on the comment in source code RtpDataCounter', SAME,
               'Total packets accounted for, which nothing bounds either.', MSG + 'worker/include/RTC/RateCalculator.hpp',
               'Cumulative received packet count per receiving stream; subtracting two readings gives the received packet count within the window, covering only a single stream.', True, 1),
        '2': F('bytesReceived', tctx, 'bytes', 'cumulative, based on source code RateCalculator::GetBytes returns the cumulative total', SAME,
               'this->recvTransmission.GetBytes(),', MSG + 'worker/src/RTC/Transport.cpp',
               'The transport layer accumulates the length each time a piece of data is received, and subtracting two readings gives the number of bytes in the window. There is also rtpBytesReceived, which counts only RTP.', True, 1),
        '3': F('roundTripTime', pctx, rtt_u, 'instantaneous', SIM, rtt_q, MSG + 'worker/src/RTC/RTP/RtpStream.cpp',
               'The round-trip delay of the receiving stream is computed from the DLRR in the sender report, and is round-trip not one-way; the queueing delay also requires tracking the minimum and then subtracting.'),
        '4': F('roundTripTime', pctx, rtt_u, 'instantaneous', SIM, rtt_q, MSG + 'worker/src/RTC/RTP/RtpStream.cpp',
               'round trip rather than one way, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('roundTripTime', pctx, rtt_u, 'instantaneous', SIM, rtt_q, MSG + 'worker/src/RTC/RTP/RtpStream.cpp',
               'There is no minimum delay field; the minimum must be tracked by oneself from the round-trip time readings.'),
        '6': F('roundTripTime', pctx, rtt_u, 'instantaneous', SIM, rtt_q, MSG + 'worker/src/RTC/RTP/RtpStream.cpp',
               'Each reading gives one round-trip delay; the in-window minimum can only be approximated from multiple readings, which is disputed, so it is labelled a different definition.'),
        '7': F('roundTripTime', pctx, rtt_u, 'instantaneous', SIM, rtt_q, MSG + 'worker/src/RTC/RTP/RtpStream.cpp', 'Same feature 6; disputed; labelled a different definition.'),
        '8': F('packetCount', pctx, 'packet', 'cumulative', SIM, 'Total packets accounted for, which nothing bounds either.', MSG + 'worker/include/RTC/RateCalculator.hpp',
               'There is no inter-arrival field; the window length divided by the number of packets received within the window approximates the average inter-arrival time, which is averaging.'),
        '9': F('jitter', pctx, 'RTP timestamp units, converted from arrival time by the stream clock frequency according to the source code, then differenced', 'instantaneous', SIM,
               'this->jitter += (1. / 16.) * (static_cast<float>(d) - this->jitter);', MSG + 'worker/src/RTC/RTP/RtpStreamRecv.cpp',
               'Exponentially smoothed with a 1/16 gain per RFC 3550 on the transmission time difference, it is a smoothed estimate, and the quantity is also not the standard deviation of arrival intervals; the unit also varies with the encoding clock, labelled a different definition.'),
        '10': F('fractionLost', pctx, '8-bit fixed point, full scale 256, based on source lostInterval << 8', 'interval, Between two adjacent generated receive reports', SAME,
                'const double fraction = std::round(static_cast<double>(lostInterval << 8) / expectedInterval);', MSG + 'worker/src/RTC/RTP/RtpStreamRecv.cpp',
                'When mediasoup acts as the receiver and generates RTCP reception reports, it computes the packet loss ratio from the difference between the expected number of packets and the actually received number of packets in this interval, stores it as an 8-bit fixed-point value, and dividing by 256 gives the in-window packet loss rate; the window length is the interval between two reception reports. It covers only a single stream.', False, 0.00390625),
        '11': F('nackPacketCount', pctx, 'packet', 'cumulative', SIM, 'this->nackPacketCount += numPacketsRequested;', MSG + 'worker/src/RTC/RTP/RtpStreamRecv.cpp',
                'nackPacketCount divided by nackCount gives the average number of packets requested per NACK, which can roughly substitute for the average number of lost packets per loss event. However, one NACK does not equal one loss event, and there are also batches and retransmissions, so it is disputed; judged as same quantity.'),
        '12': F('packetCount', pctx + ', split by "kind"', 'packet', 'cumulative', SIM,
                "The producer's statistics contain an entry for each RTP stream being received.", MD,
                'One item per receiving stream with a kind field; the sum of received packet count differences for video streams divided by the sum of received packet count differences for all streams gives the video packet proportion; multi-field combination.'),
        '13': F('packetCount', pctx + ', split by "kind"', 'packet', 'cumulative', SIM,
                "The producer's statistics contain an entry for each RTP stream being received.", MD,
                'Same feature 12; sum over streams with kind equal to audio and then divide; multi-field combination.'),
        '14': F('probationBytesSent', tctx, 'bytes', 'cumulative', SIM, 'this->sendProbationTransmission.GetBytes(),', MSG + 'worker/src/RTC/Transport.cpp',
                'These are the probing bytes that mediasoup itself sends out, belonging to the sender-side measurement, counted by bytes rather than by packets, and must also be combined with the total to compute a ratio; there is no probing count in the receive direction, and rtxBytesReceived mixes retransmissions and probing together. It is judged as the same quantity according to the sender-side measured category, which is disputed.'),
    })
PREFIX['mediasoup v3'] = 'mediasoup_'

# ---------------------------------------------------------------- 6 Pion
PD = 'https://pkg.go.dev/github.com/pion/webrtc/v4'
PS = 'https://github.com/pion/webrtc/blob/master/stats.go'
ib = 'InboundRTPStreamStats'
cp = 'ICECandidatePairStats'
rtt_q = 'CurrentRoundTripTime represents the latest round trip time measured in seconds,'
S['Pion WebRTC'] = dict(
    header='Pion WebRTC (Go), statistics report returned by PeerConnection.GetStats() on the receiving peer, polled periodically',
    status='kept', reason_if_dropped='',
    features={
        '0': F('BytesReceived', ib, 'bytes', 'cumulative, original text "total number"', SIM, 'BytesReceived is the total number of bytes received for this SSRC.', PD + '#InboundRTPStreamStats',
               'There is no received bitrate field; it requires the difference of two readings divided by the time difference and multiplied by 8, which is computing a rate. ICECandidatePairStats.AvailableIncomingBitrate is the available bandwidth computed by congestion control, not a measured rate.'),
        '1': F('PacketsReceived', ib, 'packet', 'cumulative, original text "total number"', SAME, 'PacketsReceived is the total number of RTP packets received for this SSRC.', PD + '#InboundRTPStreamStats',
               'Cumulative received packet count per SSRC; subtracting two readings gives the received packet count within the window. TransportStats.PacketsReceived is documented, but the source code icetransport.go only fills in the byte count, so it is not selected.', True, 1),
        '2': F('BytesReceived', ib, 'bytes', 'cumulative', SAME, 'BytesReceived is the total number of bytes received for this SSRC.', PD + '#InboundRTPStreamStats',
               'Cumulative received byte count per SSRC; subtracting two readings gives the byte count within the window; RTP headers and padding are counted separately in HeaderBytesReceived.', True, 1),
        '3': F('CurrentRoundTripTime', cp, 'seconds, original text "measured in seconds"', 'instantaneous', SIM, rtt_q, PD + '#ICECandidatePairStats',
               'Only the round-trip time measured by the STUN check, not the one-way delay of media packets; queueing delay also requires tracking the minimum and subtracting. RemoteOutboundRTPStreamStats.RoundTripTime is defined, but the receiver side does not fill it in the source code.'),
        '4': F('CurrentRoundTripTime', cp, 'seconds', 'instantaneous', SIM, rtt_q, PD + '#ICECandidatePairStats', 'round trip rather than one way, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('CurrentRoundTripTime', cp, 'seconds', 'instantaneous', SIM, rtt_q, PD + '#ICECandidatePairStats', 'There is no minimum delay field; the minimum must be tracked by oneself from the round-trip time readings.'),
        '6': F('CurrentRoundTripTime', cp, 'seconds', 'instantaneous', SIM, rtt_q, PD + '#ICECandidatePairStats', 'The in-window minimum can only be approximated from multiple readings, which is disputed; judged as same quantity.'),
        '7': F('CurrentRoundTripTime', cp, 'seconds', 'instantaneous', SIM, rtt_q, PD + '#ICECandidatePairStats', 'Same feature 6; disputed; labelled a different definition.'),
        '8': F('PacketsReceived', ib, 'packet', 'cumulative', SIM, 'PacketsReceived is the total number of RTP packets received for this SSRC.', PD + '#InboundRTPStreamStats',
               'Dividing the window length by the in-window received packet count approximates the mean arrival interval, which is averaging; LastPacketReceivedTimestamp only gives the time of the last packet.'),
        '9': F('Jitter', ib, 'seconds, original text "measured in seconds"', 'instantaneous', SIM, 'Jitter is the packet jitter measured in seconds for this SSRC', PD + '#InboundRTPStreamStats',
               'The source does not give the algorithm; the field is filled in by the interceptor\'s receive statistics, not the standard deviation of inter-arrival intervals within the window, so it is labelled a different definition.'),
        '10': F('PacketsLost', ib, 'packet', 'cumulative, original text "total number"', SIM, 'PacketsLost is the total number of RTP packets lost for this SSRC.', PD + '#InboundRTPStreamStats',
                'There is no receiver-side packet loss rate field; it requires the packet loss count difference divided by the sum of the packet loss count difference and the received packet count difference, which is a multi-field combination; the original text also states that it is an estimate and can be negative.'),
        '11': F('BurstPacketsLost', ib, 'packet', 'cumulative, original text "cumulative number"', SIM, 'BurstPacketsLost is the cumulative number of RTP packets lost during loss bursts.', PD + '#InboundRTPStreamStats',
                'Dividing by BurstLossCount gives the average number of lost packets per packet loss burst; it is a multi-field combination aggregated by event; a burst is defined by a threshold such as RFC 3611 and is not equal to each packet loss event. In addition, populateInboundStats in the source file rtpreceiver.go does not fill these two fields, so the actual reading is always 0.'),
        '12': F('PacketsReceived', ib + ', split by Kind', 'packet', 'cumulative', SIM, 'Kind is either "audio" or "video"', PD + '#InboundRTPStreamStats',
                'Sum the received packet count differences for streams whose Kind is video, then divide by the sum of the received packet count differences for all inbound streams, a multi-field combination.'),
        '13': F('PacketsReceived', ib + ', split by Kind', 'packet', 'cumulative', SIM, 'Kind is either "audio" or "video"', PD + '#InboundRTPStreamStats',
                'Same feature 12; sum over streams with Kind equal to audio and then divide; multi-field combination.'),
        '14': F('HeaderBytesReceived', ib, 'bytes', 'cumulative', NONE, 'HeaderBytesReceived is the total number of RTP header and padding bytes received for this SSRC.', PD + '#InboundRTPStreamStats',
                'The name contains padding, which easily suggests padding probing, but it mixes the header bytes and padding bytes of all packets together, counted in bytes, cannot distinguish probing packets, and does not count as corresponding.'),
    })
PREFIX['Pion WebRTC'] = 'pion_'

# ---------------------------------------------------------------- 7 Janus
JA = 'https://janus.conf.meetecho.com/docs/admin.html'
JG = 'https://github.com/meetecho/janus-gateway/blob/master/src/'
inctx = 'handle_info response, webrtc media[].stats.in'
rctx = 'handle_info response, webrtc media[].rtcp.main'
rtt_q = 'Estimated round-trip time'
rtt_u = 'ms, based on the source code comment "We need milliseconds"'
S['Janus WebRTC Server'] = dict(
    header="Janus WebRTC Server, per-medium statistics of a handle's PeerConnection returned by the Admin API handle_info request, polled periodically",
    status='kept', reason_if_dropped='',
    features={
        '0': F('bytes_lastsec', inctx, 'bytes per second, original text "Bytes ... in the last second"', 'interval, most recent 1 second', SAME, 'Bytes sent or received in the last second', JG + 'ice.h',
               'As the receiver, Janus counts the bytes received in the last second for each inbound media stream, multiplies by 8 to get bps, with a window length of 1 second. The management API documentation says this contains "bytes per seconds"; the field definition is taken from the source code ice.h.', False, 8),
        '1': F('packets', inctx, 'packet', 'cumulative, based on source code ice.c packets++ for each packet received', SAME, 'Packets sent or received', JG + 'ice.h',
               'The cumulative number of packets received for each inbound media stream; subtracting two readings gives the number of packets received within the window.', True, 1),
        '2': F('bytes', inctx, 'bytes', 'cumulative, based on source code ice.c bytes += buflen', SAME, 'Bytes sent or received', JG + 'ice.h',
               'The cumulative number of bytes received for each inbound media stream; subtracting two readings gives the number of bytes within the window.', True, 1),
        '3': F('rtt', rctx, rtt_u, 'instantaneous', SIM, rtt_q, JG + 'rtcp.h',
               'The round-trip delay computed from the LSR and DLSR reported by RTCP, not one-way; queueing delay also requires tracking the minimum and subtracting.'),
        '4': F('rtt', rctx, rtt_u, 'instantaneous', SIM, rtt_q, JG + 'rtcp.h', 'round trip rather than one way, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('rtt', rctx, rtt_u, 'instantaneous', SIM, rtt_q, JG + 'rtcp.h', 'There is no minimum delay field; the minimum must be tracked by oneself from the round-trip time readings.'),
        '6': F('rtt', rctx, rtt_u, 'instantaneous', SIM, rtt_q, JG + 'rtcp.h', 'The in-window minimum can only be approximated from multiple readings, which is disputed; judged as same quantity.'),
        '7': F('rtt', rctx, rtt_u, 'instantaneous', SIM, rtt_q, JG + 'rtcp.h', 'Same feature 6; disputed; labelled a different definition.'),
        '8': F('packets', inctx, 'packet', 'cumulative', SIM, 'Packets sent or received', JG + 'ice.h', 'Dividing the window length by the in-window received packet count approximates the mean arrival interval, which is averaging.'),
        '9': F('jitter-local', rctx, 'ms, based on the source code jitter / (tb/1000)', 'instantaneous', SIM, 'RFC 3550 A.8 Interarrival Jitter', JG + 'rtcp.h',
               'The arrival jitter computed locally by Janus using the smoothing in RFC 3550 Appendix A.8, converted to milliseconds, is not the standard deviation of arrival intervals within the window; it is judged as the same quantity.'),
        '10': F('lost', rctx, 'packet', 'cumulative', SIM, 'Method to retrieve the total number of lost packets from an existing RTCP context', JG + 'rtcp.h',
                'The cumulative packet loss count computed locally by Janus must be combined with stats.in.packets to compute the within-window ratio. in-link-quality is a quality score obtained by filtering the interval packet loss ratio, and can also only be judged as the same quantity.'),
        '11': F('nacks', 'handle_info response, webrtc media[].stats.out (also stats.in)', 'packet', 'cumulative', NONE, 'Number of NACKs sent or received', JG + 'ice.h',
                'stats.out.nacks accumulates the number of packets Janus requests retransmission for via NACK for inbound streams, counted by packet, not the number of NACK messages, and there is no count of loss events, so the average number of lost packets per event cannot be derived; stats.in.nacks is the NACK sent by the peer, the opposite direction. Similar names, listed for reference.'),
        '12': F('packets', inctx + ', with media[].type', 'packet', 'cumulative', SIM, 'json_object_set_new(m, "type", json_string("video"));', JG + 'janus.c',
                'Each media stream has a type field; the difference in packets received for video media divided by the sum of the differences in packets received across all media gives the video packet share, a multi-field combination.'),
        '13': F('packets', inctx + ', with media[].type', 'packet', 'cumulative', SIM, 'json_object_set_new(m, "type", json_string("audio"));', JG + 'janus.c',
                'Same feature 12; sum over media with type equal to audio and then divide; multi-field combination.'),
        '14': NOF(JA, 'There are no probing-packet-related fields in either the inbound statistics or the RTCP statistics.'),
    })
PREFIX['Janus WebRTC Server'] = 'janus_'

# ---------------------------------------------------------------- 8 LiveKit
LP = 'https://github.com/livekit/protocol/blob/main/protobufs/livekit_models.proto'
LS = 'https://github.com/livekit/livekit/blob/master/pkg/sfu/rtpstats/'
rs = 'RTPStats message'
rtt_q = 'uint32 rtt_current = 31;'
rtt_u = 'the original text does not state it, the proto has no comment, and the server source code also does not state the unit'
S['LiveKit protocol'] = dict(
    header='LiveKit protocol, RTPStats protobuf message describing one RTP stream as tracked by the LiveKit media server, for example a track received from a publisher',
    status='kept', reason_if_dropped='',
    features={
        '0': F('bitrate', rs, 'bps, proto has no comment; based on bytes*8/elapsed in the server source rtpstats_base_lite.go', 'interval, the entire segment from start_time to end_time', SIM, 'double bitrate = 7;', LP,
               'proto has no comments; the units and algorithm are taken from the LiveKit server source code. It is the average bitrate over the entire statistics period, not the rate within a window; the rate can also be computed from the difference between two readings of bytes, but bytes does not include pure padding packets. Judge as same quantity.'),
        '1': F('packets', rs, 'packet', 'cumulative, based on server source code Packets, take packetsSeenMinusPadding', SIM, 'uint32 packets = 4;', LP,
               'The server source code fills in received packets minus padding-only packets; padding packets are counted separately in packets_padding; the two must be summed to get the total received packet count, a multi-field combination.'),
        '2': F('bytes', rs, 'bytes', 'cumulative, based on server source code rtpstats_receiver.go', SIM, 'uint64 bytes = 6;', LP,
               'The server source code only accumulates bytes on non-duplicate, non-padding-only packets; padding and duplicate packet bytes are counted separately in bytes_padding and bytes_duplicate; all received bytes must be summed, a multi-field combination.'),
        '3': F('rtt_current', rs, rtt_u, 'instantaneous', SIM, rtt_q, LP,
               'Only round-trip time, no one-way delay; queueing delay also requires tracking the minimum and subtracting.'),
        '4': F('rtt_current', rs, rtt_u, 'instantaneous', SIM, rtt_q, LP, 'round trip rather than one way, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('rtt_current', rs, rtt_u, 'instantaneous', SIM, rtt_q, LP, 'Only the current value and rtt_max, no minimum, must be tracked manually.'),
        '6': F('rtt_current', rs, rtt_u, 'instantaneous', SIM, rtt_q, LP, 'The in-window minimum can only be approximated from multiple readings, which is disputed; judged as same quantity.'),
        '7': F('rtt_current', rs, rtt_u, 'instantaneous', SIM, rtt_q, LP, 'Same feature 6; disputed; labelled a different definition.'),
        '8': F('packet_rate', rs, 'packets per second, based on the server source code packetsSeenMinusPadding / elapsed', 'interval, entire segment', SIM, 'double packet_rate = 5;', LP,
               'Average packet rate over the entire segment; only its reciprocal gives the average arrival interval, and it excludes pure padding packets, labelled a different definition.'),
        '9': F('jitter_current', rs, 'microseconds, based on the server source jitter / clockRate * 1e6', 'instantaneous', SIM, 'double jitter_current = 22;', LP,
               'The server applies 1/16 smoothing to the transmission time difference per RFC 3550, then converts to microseconds; it is not the standard deviation of arrival intervals, so it is labelled a different definition.'),
        '10': F('packet_loss_percentage', rs, 'Percentage, based on server source code packetsLost / packetsExpected * 100', 'interval, entire segment', SIM, 'float packet_loss_percentage = 10;', LP,
                'Cumulative packet loss percentage over the entire segment, not a within-window value, and differencing ratios does not give the within-window ratio either; the difference between packets_lost and packets must be recombined, labelled a different definition.'),
        '11': F('gap_histogram', rs, 'The key is the number of consecutively missing packets in one gap, the value is the count, based on the server source code updateGapHistogram', 'cumulative', SIM, 'map<int32, uint32> gap_histogram = 24;', LP,
                'Each time a sequence number gap appears, record once by the number of missing packets; the key-weighted average is the average number of packets lost per gap, which is event-based aggregation; the last bin is capped, and reordering is also recorded as a gap. labelled a different definition.'),
        '12': F('packets', 'RTPStats per track, with TrackInfo.type (AUDIO / VIDEO)', 'packet', 'cumulative', SIM, 'TrackType type = 2;', LP,
                'RTPStats itself carries no media type; it must be combined with the type of the TrackInfo for the same track, then the video track packet count difference is compared with all tracks, a multi-field combination.'),
        '13': F('packets', 'RTPStats per track, with TrackInfo.type (AUDIO / VIDEO)', 'packet', 'cumulative', SIM, 'TrackType type = 2;', LP,
                'Same feature 12; sum over tracks with type equal to AUDIO and then divide.'),
        '14': F('packets_padding', rs, 'packet', 'cumulative', SIM, 'uint32 packets_padding = 15;', LP,
                'The server source code records packets with a payload of 0 as padding packets; probing commonly uses such packets, but padding packets are not necessarily all probing, and they must also be combined with the total received packet count into a ratio; this is disputed, so it is labelled a different definition.'),
    })
PREFIX['LiveKit protocol'] = 'livekit_'

# ---------------------------------------------------------------- 9 SRT
SD = 'https://github.com/Haivision/srt/blob/master/docs/API/statistics.md'
sctx = 'SRT_TRACEBSTATS (srt_bstats / srt_bistats), receiver'
rtt_q = "Smoothed round-trip time (SRTT), an exponentially-weighted moving average (EWMA) of an endpoint's RTT samples, in milliseconds."
S['SRT'] = dict(
    header='SRT (Secure Reliable Transport) library, socket statistics retrieved on the receiving socket with srt_bstats() or srt_bistats(), polled periodically',
    status='kept', reason_if_dropped='',
    features={
        '0': F('mbpsRecvRate', sctx, 'Mbps', 'interval', SAME, 'Receiving rate in Mbps. Receiver side.', SD + '#mbpsRecvRate',
               'The receive rate within the reporting interval at the receiver; multiplying by 10^6 gives bps.', False, 1000000),
        '1': F('pktRecvTotal', sctx, 'packet', 'cumulative', SAME, 'The total number of received DATA packets, including retransmitted packets', SD + '#pktRecvTotal',
               'The cumulative packets received at the receiver, including retransmissions; subtracting two readings gives the packets received within the window; the interval-type pktRecv with reset reads can also be used.', True, 1),
        '2': F('byteRecvTotal', sctx, 'bytes, including the IPv4, UDP and SRT headers', 'cumulative', SAME,
               'Same as [pktRecvTotal](#pktRecvTotal), but expressed in bytes, including payload and all the headers (20 bytes IPv4 + 8 bytes UDP + 16 bytes SRT). Available for receiver.', SD + '#byteRecvTotal',
               'The cumulative bytes received at the receiver; subtracting two readings gives the bytes within the window, including headers, and by definition no distinction is made.', True, 1),
        '3': F('msRTT', 'SRT_TRACEBSTATS, sender and receiver', 'ms', 'instantaneous', SIM, rtt_q, SD + '#msRTT',
               'Only the exponentially smoothed round-trip time, not the average one-way delay within the window; queueing delay also requires tracking the minimum and subtracting.'),
        '4': F('msRTT', 'SRT_TRACEBSTATS, sender and receiver', 'ms', 'instantaneous', SIM, rtt_q, SD + '#msRTT',
               'round trip, smoothed, and subtract the 200 ms fixed baseline, labelled a different definition. msRcvTsbPdDelay is the configured playout delay, not a measured delay, not selected.'),
        '5': F('msRTT', 'SRT_TRACEBSTATS, sender and receiver', 'ms', 'instantaneous', SIM, rtt_q, SD + '#msRTT', 'There is no minimum delay field; the minimum must be tracked by oneself from the smoothed round-trip time readings.'),
        '6': F('msRTT', 'SRT_TRACEBSTATS, sender and receiver', 'ms', 'instantaneous', SIM, rtt_q, SD + '#msRTT', 'The in-window minimum can only be approximated from multiple readings, and the readings are smoothed values, which is disputed; judged as same quantity.'),
        '7': F('msRTT', 'SRT_TRACEBSTATS, sender and receiver', 'ms', 'instantaneous', SIM, rtt_q, SD + '#msRTT', 'Same feature 6; disputed; labelled a different definition.'),
        '8': F('pktRecvTotal', sctx, 'packet', 'cumulative', SIM, 'The total number of received DATA packets, including retransmitted packets', SD + '#pktRecvTotal',
               'Dividing the window length by the in-window received packet count approximates the mean arrival interval. usPktSndPeriod is the sender\'s minimum packet sending interval, which is a pacing setting rather than a measured arrival interval, so it is not selected.'),
        '9': NOF(SD, 'There is no jitter field in the statistics table; pktRcvAvgBelatedTime is the cumulative difference of late packets relative to the playout time and is unrelated to inter-arrival time.'),
        '10': F('pktRcvLoss', sctx, 'packet', 'interval', SIM, 'Same as [pktRcvLossTotal](#pktRcvLossTotal), but for a specified interval.', SD + '#pktRcvLoss',
                'Only gives the number of missing packets within the interval, must be combined with pktRecv to compute the ratio, and the original text says missing includes packets that have not arrived out of order, the definition is wide, judged same quantity.'),
        '11': F('pktRcvLossTotal', sctx, 'packet', 'cumulative', SIM,
                'Once the sequence discontinuity is detected, its size `s - next_exp` is added to `pktRcvLossTotal` statistic.', SD + '#pktRcvLossTotal',
                'The number of missing packets is accumulated per sequence number gap, but the number of gaps itself is not output; using the NAK packet count pktSentNAKTotal sent by the receiver as the denominator can roughly approximate it, but NAK also has periodic retransmissions, which is disputed; judged same quantity.'),
        '12': NOF(SD, 'SRT carries only a byte stream, and its statistics do not distinguish audio from video.'),
        '13': NOF(SD, 'SRT carries only a byte stream, and its statistics do not distinguish audio from video.'),
        '14': F('mbpsBandwidth', 'SRT_TRACEBSTATS, sender only', 'Mbps', 'instantaneous', NONE, 'The estimation is based on the time between two probing DATA packets.', SD + '#mbpsBandwidth',
                'The description mentions probing packets, which can easily be mistaken for a probe count, but it is the link bandwidth estimated from probing packet pairs, and no field counts the number of probing packets.'),
    })
PREFIX['SRT'] = 'srt_'

# ---------------------------------------------------------------- 10 ns-3
ND = 'https://www.nsnam.org/docs/models/html/flow-monitor.html'
NH = 'https://gitlab.com/nsnam/ns-3-dev/-/blob/master/src/flow-monitor/model/flow-monitor.h'
fs = 'FlowMonitor::FlowStats (per flow, also serialized to XML)'
tu = 'ns-3 Time object, XML output in nanoseconds, based on the source code As(Time::NS)'
S['ns-3 FlowMonitor'] = dict(
    header='ns-3 network simulator, FlowMonitor per-flow statistics (FlowStats) collected at the IP level and read during or after a simulation run',
    status='kept', reason_if_dropped='',
    features={
        '0': F('rxBytes', fs, 'bytes, including the IP header', 'cumulative', SIM, 'Total number of received bytes for the flow', NH,
               'There is no received rate field; it requires the difference of two readings divided by the time difference and multiplied by 8, which is computing a rate.'),
        '1': F('rxPackets', fs, 'packet', 'cumulative', SAME, 'Total number of received packets for the flow', NH,
               'Cumulative number of packets received per stream at the receiving end node; subtracting two readings gives the received packet count within the window.', True, 1),
        '2': F('rxBytes', fs, 'bytes, the original text says the probe counts the IP header', 'cumulative', SAME, 'rxBytes, rxPackets: total number of received bytes / packets for the flow;', ND,
               'Cumulative received byte count per stream; subtracting two readings gives the byte count within the window.', True, 1),
        '3': F('delaySum', fs, tu, 'cumulative', SIM, 'delaySum: the sum of all end-to-end delays for all received packets of the flow;', ND,
               'The in-window mean delay is obtained by dividing the delaySum difference by the rxPackets difference, and only after subtracting minDelay is it the queuing delay; a combination of three fields. The delay is the true one-way delay under the simulation global clock.'),
        '4': F('delaySum', fs, tu, 'cumulative', SIM, 'delaySum: the sum of all end-to-end delays for all received packets of the flow;', ND,
               'Sum of one-way delays; to average within a window it must be combined with rxPackets, and the fixed 200 ms baseline must also be subtracted.'),
        '5': F('minDelay', fs, tu, 'cumulative', SAME, 'Contains the smallest measured delay of a received packet', NH + '#L84',
               'The smallest one-way delay among packets received since self-monitoring began is the minimum delay so far, read directly without subtraction. Multiply the nanosecond value output by XML by 1e-6 to get milliseconds; if the Time millisecond interface is called directly in C++, the coefficient is 1.', False, 0.000001),
        '6': F('delayHistogram', fs, 'seconds, histogram default bucket width 0.001 s', 'cumulative', SIM,
               'delayHistogram, jitterHistogram, packetSizeHistogram: histogram versions for the delay, jitter, and packet sizes, respectively;', ND,
               'Subtracting the delay histograms of two readings gives the delay distribution within the window; the lowest non-empty bucket approximates the minimum within the window, which is then divided by the average within the window obtained from the delaySum difference divided by the rxPackets difference, a multi-field combination limited by the bucket width.'),
        '7': F('delayHistogram', fs, 'seconds, histogram default bucket width 0.001 s', 'cumulative', SIM,
               'delayHistogram, jitterHistogram, packetSizeHistogram: histogram versions for the delay, jitter, and packet sizes, respectively;', ND,
               'Same feature 6; within-window mean minus within-window minimum; requires combining the histogram difference and the delaySum difference; labelled a different definition.'),
        '8': F('timeLastRxPacket', fs, tu, 'instantaneous', SIM, 'timeLastRxPacket: when the last packet in the flow was received;', ND,
               'The difference between the timeLastRxPacket of two readings divided by the difference in rxPackets gives the average arrival interval within the window, a multi-field combination.'),
        '9': F('jitterSum', fs, tu, 'cumulative', SIM, 'jitterSum: the sum of all end-to-end delay jitter (delay variation) values for all received packets of the flow, as defined in RFC 3393;', ND,
               'What is accumulated is the absolute value of the difference in one-way delay between two adjacent packets, that is, the delay variation of RFC 3393, not the standard deviation of inter-arrival times; judged same quantity.'),
        '10': F('lostPackets', fs, 'packet', 'cumulative', SIM, 'lostPackets: total number of packets that are assumed to be lost (not reported over 10 seconds);', ND,
                'The cumulative packet loss count must be combined with rxPackets to compute a ratio, and loss is only judged when nothing is seen for more than 10 seconds; losses within the window are counted with a lag; judged same quantity.'),
        '11': F('lostPackets', fs, 'packet', 'cumulative', NONE, 'lostPackets: total number of packets that are assumed to be lost (not reported over 10 seconds);', ND,
                'Only the total number of lost packets, no count of loss events, so the average number of packets lost per event cannot be computed. Similar name, listed for reference.'),
        '12': NOF(ND, 'FlowMonitor classifies flows by 5-tuple and has no concept of media type.'),
        '13': NOF(ND, 'FlowMonitor classifies flows by 5-tuple and has no concept of media type.'),
        '14': NOF(ND, 'There are no probing packet related fields.'),
    })
PREFIX['ns-3 FlowMonitor'] = 'ns3_'

# ---------------------------------------------------------------- 11 Teams CQD
TM = 'https://learn.microsoft.com/en-us/microsoftteams/dimensions-and-measures-available-in-call-quality-dashboard'
rt_q = 'Average network propagation round-trip time computed as specified in RFC3550 in milliseconds.'
S['Microsoft Teams CQD'] = dict(
    header='Microsoft Teams Call Quality Dashboard (CQD), per-stream dimensions and measures for each call, built from quality reports sent by the endpoints',
    status='kept', reason_if_dropped='',
    features={
        '0': F('First Video Bit Rate Avg', 'Stream dimension (Second Video Bit Rate Avg for the other endpoint)', 'labeled Range (kbps), but the description says "kilobytes-per-second", self-contradictory', 'interval, entire call', SIM,
               'Average bit rate in kilobytes-per-second of video on the first endpoint.', TM,
               'Average video bitrate over the entire call, video only, bucketed by range, unit notation inconsistent, and the source does not say whether it is receive or send. First Video Bitrate Max explicitly says inbound but takes the maximum. labelled a different definition.'),
        '1': F('Packet Utilization', 'Stream dimension', 'packet', 'interval, entire session', SIM, 'Number of Real-Time Transport Protocol (RTP) packets sent in the session.', TM,
               'the number of RTP packets sent in the entire session, which is the send direction, with whole-session granularity, labelled a different definition.'),
        '2': F('First Video Bit Rate Avg', 'Stream dimension', 'labeled Range (kbps), but the description says "kilobytes-per-second"', 'interval, entire call', SIM,
               'Average bit rate in kilobytes-per-second of video on the first endpoint.', TM,
               'There is no byte count, so the whole-session byte count can only be back-derived from the whole-session average bitrate times the duration, which does not give a within-window value; this is disputed, labelled a different definition.'),
        '3': F('AppSharing Relative OneWay Average', 'Stream dimension, application sharing streams only', 'seconds, original text "in seconds"', 'interval, entire call', SIM,
               'Average relative one-way delay between the endpoints in seconds for application sharing streams.', TM,
               'The whole-session average of relative one-way delay is the same class of quantity as queuing delay, but the source does not say relative to what baseline, covers only the screen-sharing stream, and has whole-session granularity, so it is classified as similar.'),
        '4': F('Round Trip', 'Stream dimension', 'ms', 'interval, entire call', SIM, rt_q, TM,
               'Average round-trip time over the whole session, not the one-way delay within the window, and a fixed 200 ms baseline must also be subtracted, labelled a different definition.'),
        '5': F('Round Trip', 'Stream dimension', 'ms', 'interval, entire call', NONE, rt_q, TM,
               'Each stream has only one average and one maximum per call, with no minimum, and the running minimum so far cannot be tracked mid-call. The name is related; listed for reference.'),
        '6': F('Round Trip', 'Stream dimension', 'ms', 'interval, entire call', NONE, rt_q, TM,
               'Only a single average over the whole session, no within-window minimum can be obtained, so the within-window ratio cannot be composed.'),
        '7': F('Round Trip', 'Stream dimension', 'ms', 'interval, entire call', NONE, rt_q, TM, 'Same feature 6; one value for the whole session; the within-window mean minus within-window minimum cannot be computed.'),
        '8': F('Avg Packet Utilization', 'Measure', 'packets per second', 'interval, entire session', SIM, 'Average number of Real-Time Transport Protocol (RTP) packets sent per second in the session.', TM,
               'Average send rate over the whole session; taking the reciprocal approximates the average interval, but it is a send-side measure, labelled a different definition.'),
        '9': F('Jitter', 'Stream dimension', 'ms', 'interval, entire call', SIM, 'Average jitter for stream in milliseconds.', TM,
               'The whole-session average jitter reported by the receiver; the description of the metric Avg Jitter states it is arrival jitter, not the standard deviation of within-window arrival intervals, judged same quantity.'),
        '10': F('Packet Loss Rate', 'Stream dimension', 'ratio, 0.1 means 10%', 'interval, entire call', SIM,
                'Average packet loss rate for stream. Values grouped by range. 0.1 indicates 10% packet loss.', TM,
                'The whole-session average packet loss rate reported by the receiver; the metric Avg Packet Loss Rate states it is computed over 5-second intervals and then averaged, and then binned by range, not a within-window value, judged same quantity.'),
        '11': NOF(TM, 'There is no packet loss event count or consecutive loss length in the dimensions and metrics.'),
        '12': F('Packet Utilization', 'Stream dimension, grouped by the Media Type dimension', 'packet', 'interval, entire session', SIM,
                'Type of media (video, audio, app sharing, A/V stream, or video based screen sharing).', TM,
                'Group and sum the Packet Utilization of each stream by Media Type and then compare, which gives the video packet proportion for the whole session, but that is sent packet count and the granularity is the whole session, labelled a different definition.'),
        '13': F('Packet Utilization', 'Stream dimension, grouped by the Media Type dimension', 'packet', 'interval, entire session', SIM,
                'Type of media (video, audio, app sharing, A/V stream, or video based screen sharing).', TM,
                'Same feature 12; group by Media Type equal to Audio; labelled a different definition.'),
        '14': NOF(TM, 'There is no probing packet related dimension or metric.'),
    })
PREFIX['Microsoft Teams CQD'] = 'teams_'

# ---------------------------------------------------------------- 12 Chrome legacy goog stats
CB = 'https://webrtc.googlesource.com/src/+/refs/heads/main/'
CC = CB + 'pc/legacy_stats_collector.cc'
ss = 'legacy StatsReport of type "ssrc", receive direction'
cum_ch = 'cumulative, Source code not commented; based on webrtc_video_engine.cc taken from the rtp_stats.packet_counter counter'
rtt_q = 'report->AddInt64(StatsReport::kStatsValueNameRtt, info.rtt_ms);'
rtt_ctx = 'legacy StatsReport of type "ssrc", send direction only'
S['Chrome legacy getStats (goog)'] = dict(
    header='Chrome legacy (non-standard, callback-based) WebRTC getStats(), per-SSRC and bandwidth-estimation reports with goog-prefixed values on the receiving peer, polled periodically',
    status='kept', reason_if_dropped='',
    features={
        '0': F('bytesReceived', ss, 'bytes, in non-standard mode includes header and padding bytes', cum_ch, SIM, 'report->AddInt64(StatsReport::kStatsValueNameBytesReceived, bytes_received);', CC,
               'The ssrc report has no receive bitrate; take the difference of two readings divided by the time difference and multiply by 8. googAvailableReceiveBandwidth in the VideoBwe report is the output of the bandwidth estimator, not the measured receive rate, so it is not selected.'),
        '1': F('packetsReceived', ss, 'packet', cum_ch, SAME,
               '{.name = StatsReport::kStatsValueNamePacketsReceived, .value = info.packets_received},', CC,
               'Cumulative received packet count per receiving SSRC; subtracting two readings gives the received packet count within the window. The legacy statistics have no per-field description; the meaning is taken from the source code.', True, 1),
        '2': F('bytesReceived', ss, 'bytes', cum_ch, SAME, 'report->AddInt64(StatsReport::kStatsValueNameBytesReceived, bytes_received);', CC,
               'Cumulative received byte count per receiving SSRC; subtracting two readings gives the byte count within the window; whether headers are included changes with the standard mode switch, and the definition does not distinguish.', True, 1),
        '3': F('googRtt', rtt_ctx, 'ms, based on the source code info.rtt_ms', 'instantaneous', SIM, rtt_q, CC,
               'Round-trip delay is reported only in the ssrc report for the send direction; the receive direction has no delay field; queuing delay also requires tracking the minimum and subtracting it. googCurrentDelayMs is the playback-side buffering plus decoding delay, not network delay, so it is not selected.'),
        '4': F('googRtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, CC, 'round trip, send direction, and subtract the 200 ms fixed baseline, labelled a different definition.'),
        '5': F('googRtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, CC, 'There is no minimum delay field; the minimum must be tracked by oneself from the round-trip time readings.'),
        '6': F('googRtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, CC, 'The in-window minimum can only be approximated from multiple readings, which is disputed; judged as same quantity.'),
        '7': F('googRtt', rtt_ctx, 'ms', 'instantaneous', SIM, rtt_q, CC, 'Same feature 6; disputed; labelled a different definition.'),
        '8': F('packetsReceived', ss, 'packet', cum_ch, SIM, '{.name = StatsReport::kStatsValueNamePacketsReceived, .value = info.packets_received},', CC,
               'Dividing the window length by the in-window received packet count approximates the mean arrival interval, which is averaging.'),
        '9': F('googJitterReceived', ss + ', audio receivers', 'ms, based on the source code info.jitter_ms', 'instantaneous', SIM,
               '{.name = StatsReport::kStatsValueNameJitterReceived, .value = info.jitter_ms},', CC,
               'Only the audio receive report carries this value, from the arrival jitter of the RTP receive statistics, not the standard deviation of arrival intervals within the window, judged same quantity.'),
        '10': F('packetsLost', ss, 'packet', 'cumulative', SIM, '{.name = StatsReport::kStatsValueNamePacketsLost, .value = info.packets_lost},', CC,
                'Only the cumulative number of lost packets, must be combined with packetsReceived to compute the within-window ratio, judged same quantity.'),
        '11': F('googNacksSent', ss + ', video receivers', 'NACK packets, based on the source code rtcp_packet_type_counts.nack_packets', 'cumulative', SIM,
                'info.nacks_sent = stats.rtcp_packet_type_counts.nack_packets;', CB + 'media/engine/webrtc_video_engine.cc',
                'The difference of packetsLost divided by the difference of googNacksSent can roughly substitute for the average number of lost packets per loss event; however, one NACK does not equal one loss event, and there are also batches and retransmissions, so it is disputed; judged as same quantity.'),
        '12': F('packetsReceived', ss + ', split by mediaType', 'packet', cum_ch, SIM, 'report->AddString(StatsReport::kStatsValueNameMediaType, "video");', CC,
                'Each ssrc report carries mediaType; sum the received packet count differences for video and compare with all receiving SSRCs; multi-field combination.'),
        '13': F('packetsReceived', ss + ', split by mediaType', 'packet', cum_ch, SIM, 'report->AddString(StatsReport::kStatsValueNameMediaType, "audio");', CC,
                'Same feature 12; sum over audio and then divide; multi-field combination.'),
        '14': NOF(CC, 'The legacy report has no separate count of probe packets or padding packets; header and padding bytes are merged directly into bytesReceived in non-standard mode.'),
    })
PREFIX['Chrome legacy getStats (goog)'] = 'chrome_'

FEAT = ['receive rate', 'in-window received packet count', 'in-window received byte count', 'queueing latency', 'delay minus fixed baseline', 'minimum delay so far', 'delay ratio',
        'in-window mean minus in-window minimum', 'Average packet arrival interval', 'packet jitter', 'packet loss rate', 'mean lost packets per loss event', 'video packet share', 'audio packet share', 'probing packet share']

# ---------------------------------------------------------------- self-check
def norm(s):
    return re.sub(r'\s+', '', s)

def corpus(prefix):
    parts = []
    for p in sorted(glob.glob(os.path.join(RAW, prefix + '*'))):
        if p.endswith('.txt') and os.path.exists(p[:-4] + '.html'):
            continue  # derived text; re-derive from html below
        raw = open(p, encoding='utf-8', errors='replace').read()
        if p.endswith('.html'):
            s = re.sub(r'<wbr\s*/?>', '', raw)
            soup = BeautifulSoup(s, 'lxml')
            for t in soup(['script', 'style', 'noscript']):
                t.decompose()
            parts.append(soup.get_text(' '))
            parts.append(html.unescape(raw))
        else:
            parts.append(raw)
    return norm('\n'.join(parts))

checks = []
for src, d in S.items():
    assert len(d['features']) == 15
    cp_ = corpus(PREFIX[src])
    for k in range(15):
        f = d['features'][str(k)]
        assert f['relation'] in (SAME, SIM, NONE)
        if f['relation'] == SAME:
            assert isinstance(f['diff'], bool) and isinstance(f['scale'], (int, float))
        if f['quote']:
            ok = norm(f['quote']) in cp_
            checks.append((src, k, 'quote', f['quote'], ok))
        if f['name'] != NF:
            comps = [c for c in re.split(r'[.\[\]]+', f['name']) if c]
            ok = all(norm(c) in cp_ for c in comps)
            checks.append((src, k, 'name', f['name'], ok))
        else:
            assert f['relation'] == NONE

json.dump(S, open(os.path.join(OUT, 'field_transcription.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- markdown
def esc(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')

def cnt(d):
    c = {SAME: [], SIM: [], NONE: []}
    for k in range(15):
        c[d['features'][str(k)]['relation']].append(k)
    return c

L = []
L.append('# Transcription of real client telemetry fields, 12 sources against 15 interface features\n')
L.append('Transcription date 2026-10-02. All original text was fetched with curl from official documentation or official source repositories, cached in the raw/ directory, not filled in from memory, and no LLM interface was called. Write "not found" for anything that cannot be found. Feature definitions are taken from data/audit_bench_v1/official_feature_spec.txt, numbered from 0.\n')
L.append('## A few additional practices settled at adjudication time\n')
L.append('The conventions follow the task description; the items below are the practices uniformly adopted when the description does not cover a situation, applied equally to all twelve sources.\n')
L.append('- For counts computed per single stream or single track, as long as they are measured at the receiver on the incoming stream, they are regarded as "measured at the receiver on the incoming stream" and judged the same quantity, with the reason noting that it covers only that stream.')
L.append('- When the source has only a latency field with one periodic reading, features 3 and 5 must track the historical minimum and are labelled a different definition; features 6 and 7 require the per-packet minimum within the window and can only be approximated by multiple readings within the window, handled as "contested, labelled a different definition". When the source gives only one summary value per call, 6 and 7 as well as the minimum so far cannot be computed, and are judged none.')
L.append('- Feature 4 must subtract a fixed baseline of 200 ms; subtracting a constant is not unit conversion, so any latency field can only be labelled a different definition for feature 4.')
L.append('- Feature 11 requires the number of loss events. When there is only a cumulative loss count, judge none; when there is a burst count or gap histogram, label it a different definition; when only the number of NACK or NAK messages can be used as the denominator, handle as "contested, labelled a different definition".')
L.append('- For ratio fields where the documentation does not clearly state the value range or unit, making the conversion coefficient impossible to determine, handle them as "contested, labelled a different definition" and do not force a scale.')
L.append('- When there is only example code, an internal variable, or a source constant and no textual explanation, quote transcribes the original sentence or original line from the official source code. The basis for the unit is written in the unit column; the cumulative column contains only one of cumulative, interval, instantaneous, per-event, and the basis for the judgment is appended to the end of reason.')
L.append('- When the field name cannot be found, name is written as "not found", unit and cumulative are written as "not applicable", and quote is left empty.')
L.append('- The meaning of scale is interface value = field value or difference between two readings × scale; diff being true means two readings must be subtracted.\n')

L.append('## Summary\n')
L.append('| # | source | status | same quantity | different definition | none |')
L.append('|---|---|---|---|---|---|')
for i, (src, d) in enumerate(S.items(), 1):
    c = cnt(d)
    fmt = lambda xs: f'{len(xs)} ({", ".join(map(str, xs))})' if xs else '0'
    L.append(f'| {i} | {src} | {d["status"]} | {fmt(c[SAME])} | {fmt(c[SIM])} | {fmt(c[NONE])} |')
L.append('\nAll 12 sources are retained. The LiveKit proto has no comments, the mediasoup documentation has only example JSON, and the Chrome legacy stats have no per-field description; the meaning and units for these three come from their respective official source code, and the fields whose original text can be copied far exceed 3, so they do not meet the exclusion criterion.\n')

for i, (src, d) in enumerate(S.items(), 1):
    L.append(f'## {i}. {src}\n')
    L.append(f'header: {d["header"]}\n')
    L.append(f'Status: {d["status"]}' + (f', exclusion reason: {d["reason_if_dropped"]}' if d['reason_if_dropped'] else '') + '\n')
    L.append('| feature | name | context | unit | cumulative | relation | diff | scale | quote | url | reason |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|')
    for k in range(15):
        f = d['features'][str(k)]
        diff = str(f['diff']).lower() if 'diff' in f else ''
        scale = f['scale'] if 'scale' in f else ''
        L.append('| ' + ' | '.join(esc(x) for x in [f'{k} {FEAT[k]}', f['name'], f['context'], f['unit'], f['cumulative'], f['relation'], diff, scale,
                                                   f['quote'], f['url'], f['reason']]) + ' |')
    L.append('')

L.append('## Original text cache\n')
L.append('Under raw/ stored by source prefix: agora_, twilio_, daily_, jitsi_, mediasoup_, pion_, janus_, livekit_, srt_, ns3_, teams_, chrome_. HTML pages are additionally saved as tag-stripped .txt for reading; source files are saved as is. For fixed versions see jitsi_commit_sha.txt, mediasoup_tree_sha.txt, chrome_commit.txt, pion_commit_sha.txt; Twilio documentation uses version 2.36.0, and documentation URLs for 2.37.0 and later return 403.\n')

nq = sum(1 for c in checks if c[2] == 'quote'); nqok = sum(1 for c in checks if c[2] == 'quote' and c[4])
nn = sum(1 for c in checks if c[2] == 'name'); nnok = sum(1 for c in checks if c[2] == 'name' and c[4])
L.append('## Self-check results\n')
L.append('The approach is to concatenate all cached files under each source prefix, take two copies for HTML: tag-stripped text and unescaped source code, then remove all whitespace characters; for quote, likewise remove whitespace and then do a substring search. name is split by dots and square brackets into several segments, and each segment must appear in the original text.\n')
L.append(f'- quote has {nq} entries in total, {nqok} found.')
L.append(f'- There are {nn} names that are not "not found", {nnok} found.')
bad = [c for c in checks if not c[4]]
if bad:
    L.append('- The entries that did not pass are as follows.')
    for c in bad:
        L.append(f'  - {c[0]} feature {c[1]} of {c[2]}: {c[3]}')
else:
    L.append('- All passed.')
open(os.path.join(OUT, 'field_transcription.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')

print('quotes', nqok, '/', nq, 'names', nnok, '/', nn)
for c in bad:
    print('FAIL', c)
for src, d in S.items():
    c = cnt(d)
    print(src, len(c[SAME]), len(c[SIM]), len(c[NONE]))
