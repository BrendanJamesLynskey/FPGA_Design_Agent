# Reference QoR: P13-2

The course's single-pass labeller (`solutions/p13l08_ccl/ccl.sv`) is a behavioural reference (integer arrays, a one-clock root resolve loop); it is **not synthesisable as written to
meet a pixel clock**, so no QoR was measured. A pipelined resolve is the agent's design task (lesson 8). Full-flow and OOC QoR: **not run**. The re-scoped reference (v1.1) adds a small
selection and centroid block (`blob_report.sv`, a divider on 20-bit sums) around it; simulated only.


## Whole-board reference build (course v1.3, brief 07a1c)

`tools/ref_build.py`, Vivado 2025.2, xc7a100tcsg324-1, 100 MHz, test shell included; gates all pass (the flow's standards check v1.0 still fails, as for every reference). Numbers from `results/c13_nexys_blob_tracker__vivado.json`.

| WNS at 100 MHz | LUT | FF | RAMB36/18 tiles | DSP48 | Power |
|---|---|---|---|---|---|
| +0.465 ns | 2,794 | 2,098 | 0 | 0 | 0.139 W |

The first reference (integer arrays, two unrolled 64-step union-find searches per pixel) did not finish in 60 minutes. Now a state machine with sized registers, a few clocks per pixel, and a bit-serial centroid division.
