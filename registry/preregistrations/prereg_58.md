<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: Unlocking the one-token LLM variant online (llm4bandpp-online-unlock-v1, evening of 2026-09-19, before launch)

## Three fixes (none touch model weights)
- A: collector v6, which restores the unreported audio stream (receiving rate plus 41 kbps, packet and byte counts increased accordingly). This is a schema correction: the rate-type features of the training data include audio.
- B: probing envelope v4 wrapped around the one-token LLM variant (probing upward at GCC's pace when there is no sign of congestion).
- C: A and B stacked.
Control: the one-token LLM variant with collector v5 and without envelope, rerun in the same batch. One conference-version group with collector v6 is also run, to see whether the schema correction helps or hurts the conference version.

## Configuration
Tiers `lowbw_400`, `lowbw_1000`, `paper_high_2000`, 3 runs per cell, randomized order within each repetition, slack 80, obs trace on. Four configurations of the one-token LLM variant, 36 runs, and one LLM4Band configuration, 9 runs, 45 in total. Before launch, one smoke run not counted in the results (configuration C, lowbw_1000), whose gate checks only the mechanism: collector marked v6, envelope v4, estimate finite and positive, model raw output recorded in the trace.

## Criteria (fixed before running)
Utility recomputed with source cap 610 kbps, threshold 5.27, readings relative to the control configuration in the same batch.
- A fix "unlocks" if all three hold: at both 1000 and 2000 kbps, the cell-mean video bitrate is at least 300 kbps (about 116 when locked); utility at both tiers is better; the 400 kbps condition is not worse.
- Verdict: holds if at least one of the three fixes unlocks; does not hold if none does and the cell-mean video bitrate at both tiers is below 200 kbps; otherwise inconclusive (for example unlocked but the 400 kbps condition worsens).
- Report only: gaps between each configuration and the conference version (previous batch 85.5, 91.1, and this batch's LLM4Band plus v6); queueing delay, packet loss, arrival frame rate, and freeze proxy metrics; fraction of steps rewritten by the envelope; per-step compute time and request interval.
- The rule for recommending a fix is also fixed in advance: among the fixes that unlock, the one with the highest mean utility across the three tiers is taken; if A alone unlocks, A is preferred, because it is a schema correction rather than an added controller.

## Predictions unfavorable to us
After audio is restored, the one-token LLM variant may only move from 150 to a new stable point in the 200s of kbps (the valley remains), and video bitrate will not pass 300; the envelope can push the bitrate up, but the credit goes to the envelope, and in that case we can only claim that "the one-token LLM variant needs a probing envelope to track capacity online." The LLM4Band plus v6 may overestimate more and queue longer.

