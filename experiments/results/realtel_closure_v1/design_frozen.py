def features(prev, cur):
    def get_ts(stats):
        for s in stats.values():
            if 'timestamp' in s:
                return s['timestamp']
        return None

    prev_ts = get_ts(prev)
    cur_ts = get_ts(cur)
    delta_t = None
    if prev_ts is not None and cur_ts is not None and cur_ts > prev_ts:
        delta_t = (cur_ts - prev_ts) / 1000.0

    def sum_delta(prev, cur, stat_type, fields):
        total = {f: 0 for f in fields}
        found = False
        for sid, cs in cur.items():
            if cs.get('type') == stat_type:
                if sid not in prev:
                    return None
                ps = prev[sid]
                for f in fields:
                    if f not in cs or f not in ps:
                        return None
                    total[f] += cs[f] - ps[f]
                found = True
        if not found:
            return None
        return total

    transport = sum_delta(prev, cur, 'transport', ['bytesReceived', 'packetsReceived'])
    if transport is None:
        transport = sum_delta(prev, cur, 'candidate-pair', ['bytesReceived', 'packetsReceived'])

    rate = None
    num_packets = None
    bytes_received = None
    if transport is not None:
        num_packets = transport['packetsReceived']
        bytes_received = transport['bytesReceived']
        if delta_t is not None and delta_t > 0:
            rate = (transport['bytesReceived'] * 8) / delta_t

    inbound_ids = [sid for sid, s in cur.items() if s.get('type') == 'inbound-rtp']
    total_received = None
    total_lost = None
    video_packets = None
    audio_packets = None
    if inbound_ids:
        all_present = True
        for sid in inbound_ids:
            if sid not in prev:
                all_present = False
                break
        if all_present:
            total_received = 0
            total_lost = 0
            video_packets = 0
            audio_packets = 0
            for sid in inbound_ids:
                cs = cur[sid]
                ps = prev[sid]
                if 'packetsReceived' not in cs or 'packetsReceived' not in ps:
                    total_received = None
                    break
                if 'packetsLost' not in cs or 'packetsLost' not in ps:
                    total_lost = None
                    break
                delta_recv = cs['packetsReceived'] - ps['packetsReceived']
                delta_lost = cs['packetsLost'] - ps['packetsLost']
                total_received += delta_recv
                total_lost += delta_lost
                kind = cs.get('kind')
                if kind == 'video':
                    video_packets += delta_recv
                elif kind == 'audio':
                    audio_packets += delta_recv

    loss_ratio = None
    if total_received is not None and total_lost is not None:
        denom = total_received + total_lost
        if denom > 0:
            loss_ratio = total_lost / denom

    video_prob = None
    audio_prob = None
    if video_packets is not None and audio_packets is not None:
        denom = video_packets + audio_packets
        if denom > 0:
            video_prob = video_packets / denom
            audio_prob = audio_packets / denom

    return [
        rate,                 # 1 Receiving rate
        num_packets,          # 2 Number of received packets
        bytes_received,       # 3 Received bytes
        None,                 # 4 Queuing delay
        None,                 # 5 Delay
        None,                 # 6 Minimum seen delay
        None,                 # 7 Delay ratio
        None,                 # 8 Delay average minimum difference
        None,                 # 9 Packet interarrival time
        None,                 # 10 Packet jitter
        loss_ratio,           # 11 Packet loss ratio
        None,                 # 12 Average number of lost packets
        video_prob,           # 13 Video packets probability
        audio_prob,           # 14 Audio packets probability
        None                  # 15 Probing packets probability
    ]
