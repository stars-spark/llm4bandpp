<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Interface adaptation on real client telemetry (realtel-adapter-v1)

## Data

Field names and official description text from seven real sources were taken from `data/real_telemetry_specs_v1/`, fetched with curl, transcribed by an LLM and checked sentence by sentence. The seven sources are W3C webrtc-stats, Chrome webrtc-internals, RFC 3550 and 3611, QUIC qlog, iperf3 JSON, Linux tcp_info, GStreamer rtpmanager. The transcription was made without knowledge of the weaknesses of any comparison method.

Materials given to the method under test:
- Source descriptions;
- Real field names;
- The object containing the field;
- Original text from specifications, RFCs, source code, or manuals.

No numeric values are given. The reason is that fields without a counterpart have no numeric values in our data, and giving numeric values only to fields with a counterpart would leak the answer.

Each source is presented three times: the first in transcription order, the other two with field order shuffled by a fixed seed.

## Ground truth

The relations given by the transcription, based on the original text, are used; the criteria were fixed before the run, with one change.

- **Same quantity (16 decisions):** The mapping must be correct; field, whether differencing is needed, and coefficient must all be correct; coefficient relative error must not exceed 2%.
- **No counterpart (56 decisions):** The method must answer missing.
- **Same category but different definition (33 decisions):** Not scored, reported only.

**One change:** W3C's fractionLost is attached to RTCRemoteInboundRtpStreamStats and is the peer-reported loss of the stream we sent. Our estimator is at the receiver side; per the transcription's own criterion ("sender rather than receiver" counts as different-definition), this is changed to "different definition" and not scored. The change was made before seeing any method output.

**Two special conventions:**
- RFC 3611's mean_jitter is in RTP timestamp units. The source description states a video clock of 90 kHz, so the standard coefficient is 1000/90000.
- RFC 3550's fraction lost is an 8-bit fixed-point number, so the standard coefficient is 1/256.

## Methods

**LLM arm (primary):** DeepSeek (deepseek-flash reasoning mode, temperature 0, at most 48000 tokens), called once per source per presentation.
- The prompt is newly written; the output space is "mapping (field, whether differencing is needed, coefficient) or missing".
- At most two rounds on the two development sources; the test sources are run only after freezing, and the template hash is checked before testing.
- The development sources are dev_acme_sdk and dev_netmon, which we wrote based on common telemetry conventions; they do not contain the special formats of the test sources, namely fixed-point numbers and NTP 16.16.

**Non-LLM comparisons:** Two general methods; thresholds are chosen by balanced accuracy on the development sources only.
- **NAME:** Literal similarity between field names and feature names, using difflib.
- **TFIDF:** Names plus descriptions, retrieval similarity against feature descriptions.

Both share the same unit and differencing rules:
- Units are converted from common notations in names and descriptions (nanoseconds, microseconds, milliseconds, seconds, percent, kbit, Mbit, bytes to bits);
- When the description contains "total", "sum of" or "since start", the field is treated as cumulative and differenced.

**Disclosure:** These rules were written by us after reading the test source descriptions, using only common conventions and not containing fixed-point numbers, NTP format, or clock rates. The original unit-aware matcher relied on numeric distributions to determine units; this experiment gives no numeric values, so it cannot run and is not used as a comparison.

## Criteria (confirmatory tier template)

- **Primary endpoint:** Balanced accuracy BA = 0.5 × accuracy on same quantity + 0.5 × accuracy on answering missing for no counterpart. For the LLM, the pooled value over the three presentations is used; the comparison methods are independent of field order and use one presentation.
- **Δ:** LLM BA minus the better BA of the two comparison methods. The better one is chosen post hoc and compared only on the mean.
- **Interval:** Block resampling by source, 5000 times, 90% interval.

| Conclusion | Condition |
|---|---|
| holds | Interval lower bound greater than 0 and Δ ≥ 0.15 |
| direction only | Δ > 0 |
| does not hold | Δ ≤ 0, or safety line breached |

- **Safety line:** The LLM's rate of false mapping on no-counterpart decisions must not exceed 15%. A false mapping is attaching a field to a quantity that does not exist at all, which after deployment would feed wrong data to the estimator.
- **Parse failure:** Counted as all missing.

## Unfavorable prediction

- Real field names are mostly self-explanatory, e.g. packetsReceived, bytes, lost_percent, and with the general unit rules, the comparison methods may also do well on same quantity.
- The LLM may force different-definition fields onto features, e.g. roundTripTime onto one-way delay, triggering the safety line.
- The LLM may also answer missing for same quantity because the prompt is strict.
- Fixed-point numbers (1/256) and mean_jitter in RTP timestamp units may stump the LLM.
- With only seven sources, the interval will be wide; even if the point estimate is large, the lower bound may not exceed 0.

## Report only

- Per-source results.
- Each method's choices on different-definition decisions.
- Open-source R1 distilled 32B replication: run on gpu-server-1, using the same prompt.
- Token count per call.

## Files

- Script: `scripts/coldstart/realtel_adapter_v1.py`
- Artifacts: `experiments/results/realtel_adapter_v1/`
