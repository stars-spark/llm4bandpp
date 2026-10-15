<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Closed-loop collector v2: sliding window and cadence (switch-deploy-collector-v2)

**Written 2026-09-18, before the run. The criteria are not relaxed after this point.**

## Changes (`scripts/alphartc/deploy/spec_collector.py` adds `SlidingCollector`, switch_nn uses it; the v1 class is kept for reproduction)
- The request instant T uses the receiver wall clock (same host clock as packet arrival times). Short window slot i is [T − 60(i+1), T − 60i), long window slot i is [T − 600(i+1), T − 600i), in milliseconds.
- f0 is bytes within the window × 8 ÷ window length (0.06 or 0.6 seconds). The remaining features are computed as in v1: the delay origin is set to 200 at the first packet, f5 is the global running minimum shared across slots,
  64-second wraparound is handled, f11 is the number of lost packets, and the packet-type proportions are overridden with constants.
- Cadence: the run script adds `STALENESS_BWE_FEEDBACK_MS` to override `bwe_feedback_duration` at both sender and receiver; when it is unset, behavior is unchanged. The target is a nominal 60 milliseconds.

## Tests (the closed-loop performance experiment is released only if all pass)
**W1 synthetic**: packets at known instants fall into the correct window at request instant T; long window slot 0 contains short window slots 0 to 4; the v1 wraparound, f0 unit, first packet 200, f5 monotonicity and identity tests are retained.
**W2 replay** (the same 43 logs as v1, request instants equally spaced at 60 milliseconds):
- The packet count of long window slot 0 is no less than the sum of short window slots 0 to 4: **100%** (offline is 100%);
- The median ratio of the packet count of long-window slot 0 to the summed packet count of the 5 short-window slots must fall within the offline 5% to 95% quantile range **[1.667, 2.274]**;
- The number of the 150 dimensions whose median is out of the offline range is reported, with no gate.
**W3 cadence**: fixed_env on the existing `real_03`, settings 50, 55 and 60, 3 runs each. The noise σ is the pooled sample standard deviation of the median intervals of the 3 repetitions for each configuration,
the tolerance is τ = max(3σ, 0.5 milliseconds); a fit g = a + b × setting gives c* = round((60 − a) / b), restricted to the range 30 to 60. σ, τ, c* are entered into the registry after being computed.
**W4 closed loop**: switch_nn runs `switch_plumb_140.profile` with c* (`STALENESS_CONTROL_SLACK_S=100`), and must satisfy all of the following:
all validity checks of the run script pass; the measured median interval differs from 60 by no more than τ; the long window contains the short window in 100% of steps; the median packet count ratio falls within [1.667, 2.274];
at least one wraparound with the f3 median difference no more than 50 milliseconds in the 1 second before and after; at least 40 arm selections.

## Known limitations
The actual offline request cadence is irregular and cannot be inferred from observations, so 60 milliseconds is a nominal value; the sliding window request instant uses the wall clock, which may differ from AlphaRTC's internal timestamps by less than a millisecond.
