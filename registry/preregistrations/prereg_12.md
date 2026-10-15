<!-- Pre-registration note, translated from Chinese; motivation, scheduling and write-up sections omitted. Section and table numbers refer to the draft at the time of registration. -->
# Pre-registration: 320x240 closed loop with three sequences (content320-ch-gcc-v1, 2026-10-08)

Written before the run. Script `scripts/alphartc/deploy/content320_ch_gcc_v1.py`.

## Design
- Three sequences, labelled by mean temporal information from low to high (paper-video-source-freeze-v21): Johnny (low), Mobcal (medium), Parkrun (high). 320x240, 15 fps, video cap about 610 kbit/s. One sub-batch per sequence.
- Conditions: constant 200, 400, 1000 kbit/s, one-way 50 ms, no loss, 120 s.
- Two arms:
  - dep: deployed system, i.e. C-H seed 1, plus 5 kbps floor and probing envelope v6;
  - gcc: corrected Python GCC called every 200 ms.
- 3 runs per cell, 18 runs per sequence, 54 total; run script v29, two container pairs in parallel.

## Criteria
- Measurement only, no verdict.
- For each sequence, the utility and VMAF differences of the deployed system minus GCC are reported: three cells equally weighted, 10000 resamples within cells, seed 20261008, 90% interval.
- Also report per-cell utility, VMAF, SSIM, video rate, queueing and broken calls for each arm.
- "Holds" means only that each sequence has at least 2 valid runs per cell and arm.

## Unfavorable prediction
For high-motion Parkrun the encoder rate fluctuates greatly, and the deployed system may be worse than GCC.

