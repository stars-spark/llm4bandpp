<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Scale-up to new real telemetry sources (realtel-scale-v1)

## New sources (fixed at registration, not selected by looking at results)

| id | source | type |
|---|---|---|
| 1 | Agora Web SDK receiver-side statistics (e.g. RemoteVideoTrackStats) | commercial SDK |
| 2 | Twilio Video JS receiver-side track statistics | commercial SDK |
| 3 | Daily (daily-js getNetworkStats) | commercial SDK |
| 4 | Jitsi (lib-jitsi-meet connection quality statistics) | open source |
| 5 | mediasoup (getStats receive stream statistics) | open source |
| 6 | Pion WebRTC (Go stats package) | open source |
| 7 | Janus (admin API in-stats) | open source |
| 8 | LiveKit (RTP statistics in protocol) | open source |
| 9 | SRT protocol (libsrt statistics) | transport protocol |
| 10 | ns-3 FlowMonitor | simulator |
| 11 | Microsoft Teams call quality dashboard (CQD) dimensions and measures | enterprise telemetry |
| 12 | Chrome legacy getStats (goog prefix) | version drift, paired with the current W3C version |

Sources for which official documentation cannot be found, or fewer than 3 fields can be transcribed from the original text, are removed before any method runs, and a note is recorded.

## Ground truth

- The official original text is fetched with curl, transcribed by an LLM and checked sentence by sentence, and the relations are labelled under the unified criterion of the third version. The criterion is the rule written in truth_v3.json of realtel-adapter-v1:
  - sender side counts as different-definition;
  - multi-field combinations and event aggregation count as different-definition;
  - judged by official feature definitions, e.g. jitter is the standard deviation of arrival intervals within a window;
  - disputed cases are assigned to "different definition".
- Two independent LLM checks verify the labels (A checks line by line against the original text, B first infers blindly, then compares). Labels both agree on are adopted; disputed ones are assigned to "different definition", i.e. not scored.
- Methods are run only after the labels are final.

## Methods and criteria (same as realtel-adapter-v1)

**LLM:** DeepSeek, using the frozen prompt of realtel-adapter-v1 (template hash d2467ef5dc35, verified before running), three field orders per source; each call records wall-clock time and token count.

**Controls:** the seven non-LLM methods of realtel-baseline-strength-v1, with thresholds kept at the values chosen on the development sources there, not re-tuned, and with the generic unit and differencing rules.

**Primary endpoint:** balanced accuracy of full scoring (fields, differencing, coefficients).

**Δ:** LLM minus the best of the seven controls.

**Interval:** block resampling by source 5000 times, 90% interval.

| conclusion | condition |
|---|---|
| holds | lower bound greater than 0 and Δ ≥ 0.15 |
| direction only | Δ > 0 |
| does not hold | Δ ≤ 0, or the LLM's mis-mapping ratio on decisions with no counterpart exceeds 15% |

## Report only

- field-only scoring;
- open-source R1 distilled 32B and 14B;
- per-source results, and the proportion of sources the LLM gets fully correct, i.e. the proportion directly usable with zero manual work;
- time and cost of each client (at DeepSeek official unit price);
- version drift: whether the LLM is correct on both the legacy Chrome source and the current W3C source.

## Unfavorable predictions

- Commercial SDK field descriptions are often very brief, and the LLM may err on units and on whether a field is cumulative.
- Among the new sources, same-quantity fields may be more common than in the previous 7, the generic rules may also get some right, and Δ may shrink.
