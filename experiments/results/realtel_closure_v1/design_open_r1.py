import math

def features(prev, cur):
    result = [None] * 15
    prev_t01 = prev.get('T01', {})
    cur_t01 = cur.get('T01', {})
    prev_time = prev_t01.get('timestamp', 0)
    cur_time = cur_t01.get('timestamp', 0)
    time_diff = (cur_time - prev_time) / 1000  # Convert to seconds

    # Feature 1: Receiving rate (bps)
    prev_bytes = prev_t01.get('bytesReceived', 0)
    cur_bytes = cur_t01.get('bytesReceived', 0)
    if prev_bytes is not None and cur_bytes is not None and time_diff > 0:
        result[0] = (cur_bytes - prev_bytes) * 8 / time_diff
    else:
        result[0] = None

    # Feature 2: Number of received packets
    prev_packets = prev_t01.get('packetsReceived', 0)
    cur_packets = cur_t01.get('packetsReceived', 0)
    if prev_packets is not None and cur_packets is not None:
        result[1] = cur_packets - prev_packets
    else:
        result[1] = None

    # Feature 3: Received bytes
    if prev_bytes is not None and cur_bytes is not None:
        result[2] = cur_bytes - prev_bytes
    else:
        result[2] = None

    # Features 4-8: Cannot compute with given data
    result[3:9] = [None] * 6

    # Feature 9: Packet interarrival time - Not directly available
    result[8] = None

    # Feature 10: Packet jitter - Not directly available
    result[9] = None

    # Feature 11: Packet loss ratio
    audio_prev = prev.get('IT01A635131731', {})
    audio_cur = cur.get('IT01A635131731', {})
    video_prev = prev.get('IT01V1299012801', {})
    video_cur = cur.get('IT01V1299012801', {})

    lost_audio = audio_cur.get('packetsLost', 0) - audio_prev.get('packetsLost', 0)
    lost_video = video_cur.get('packetsLost', 0) - video_prev.get('packetsLost', 0)
    total_lost = lost_audio + lost_video

    received_audio = audio_cur.get('packetsReceived', 0) - audio_prev.get('packetsReceived', 0)
    received_video = video_cur.get('packetsReceived', 0) - video_prev.get('packetsReceived', 0)
    total_received = received_audio + received_video

    if total_received > 0:
        result[10] = total_lost / total_received
    else:
        result[10] = None

    # Feature 12: Average number of lost packets - Not directly available
    result[11] = None

    # Feature 13: Video packets probability
    if total_received > 0:
        result[12] = received_video / total_received
    else:
        result[12] = None

    # Feature 14: Audio packets probability
    if total_received > 0:
        result[13] = received_audio / total_received
    else:
        result[13] = None

    # Feature 15: Probing packets probability - Not available
    result[14] = None

    return result
