<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Closed-loop collector correction and switcher deployment (switch-deploy-collector-v1)

**Written 2026-09-18, before the run. The criteria are not relaxed after this point.**

## 1 Fixes (new module `estimator/spec_collector.py`; the default behavior of the old path is unchanged)

1. **Slot order**: the most recent monitoring interval goes to slot 0 (`b0-slot-order-audit-v1`: offline right-shift 5397 vs left-shift 41).
2. **Delay definition**: f3 to f7 use the canonical formula already verified in `collector_spec_overlay_v1.py`.
3. **Absolute delay**: the two testbed containers share the host clock; within a session, the minimum "receive minus send" is the origin, scaled by the profile's known injection baseline delay D, so that f5 equals the true minimum one-way delay. D is passed via environment variable `BWE_BASE_DELAY_MS`; if unset, startup is refused, no silent fallback. **This holds only on the testbed and cannot be used in a real cross-machine deployment.**
4. **64-second wraparound**: when the send timestamp falls back by more than 32000 milliseconds, 64000 is added. None of the 811 historical receiver logs ever crossed 64 seconds, so this was never triggered.
5. **f0 unit**: bit/s, consistent with training data (the interval duration is in milliseconds, so it must be divided by 1000).
6. **Packet type ratios f12 to f14**: the online estimator only receives RED-encapsulated video packets (payload type 125), and cannot see audio. **The old implementation's override with training-set mean constants is kept**, while the faithfully computed values are written to disk separately. This is a known definitional bias.

## 2 Switcher estimator (new module `estimator/switcher.py`)

Four arms infer in parallel at each step: Pioneer, Schaferct(public), Schaferct(retrained) each maintain their own LSTM state via ONNX, and MLP_seed0 is loaded from checkpoint. Every 50 requests (one every 60 milliseconds, i.e. 3 seconds), the switcher network runs on the 22 observable features of the previous block to select an arm; block 0 uses Schaferct(public). **The switcher network used for deployment is trained on all 870 calls with the same recipe as NN_SAME_OBJ**; it is used only in closed loop, and no offline scores are reported for it. Entry point `BandwidthEstimator.py` gains a `BWE_ESTIMATOR=switch_nn` branch; all other branches are unchanged character for character, backed up before modification with hashes recorded.

## 3 Validation (all must pass before any closed-loop performance experiment may be registered)

**V1 Synthetic unit checks**: slot order (new packet enters slot 0, old packets shift right); wraparound (construct send timestamps crossing 64000, receive-minus-send is continuous, no 64000 jump); f0 unit (known bytes and duration yield bit/s); the canonical identity f3 − f4 + f5 = 200 holds in absolute units with relative error no more than 1e-9; after D scaling, f5 equals D.

**V2 Real packet stream replay**: per-packet records from historical receiver logs are replayed into the old and the new collector:
- The new collector's f0, f1, f2 at slot 0 must match value for value the old collector's corresponding values at slot 4 (confirming on real packets that the slot order was inverted and has been corrected);
- Value ranges: in the new collector, f6 no less than 1, f5 no less than 0 and f3 no less than 0 each hold in 100% of steps (only for runs with a baseline delay of no less than 20 milliseconds);
- Distribution: for each of the 150 dimensions, it is checked whether the online median falls between the 1% and 99% quantiles of that dimension in the offline data; **the new collector must have fewer out-of-range dimensions than the old collector**; all per-dimension results are reported, so that totals do not mask individual dimensions.

**V3 Switcher offline equivalence**: the observation sequences of the offline data are fed directly into `switcher.py` without the collector; its per-block selections and outputs must match the offline simulation (same deployment network, same feature construction) bit for bit. This shows that the deployment code and the evaluation code compute the same thing.

**V4 Short closed loop**: one closed-loop call of no less than 130 seconds with a baseline delay of 20 milliseconds, `BWE_ESTIMATOR=switch_nn`, with online observations written to disk:
- At least one send timestamp wraparound occurs, and f3 shows no jump across the wraparound (the median difference of f3 over the 1 second before and after the wraparound is no more than 50 milliseconds);
- The measured median request interval is between 55 and 65 milliseconds;
- Online observations undergo the same distribution comparison as in V2 and are reported;
- The switcher completes at least 40 arm selections with no abnormal exit.

## 4 What is not done

This note evaluates no closed-loop performance and no visual quality; that is the next experiment and must be pre-registered separately.
