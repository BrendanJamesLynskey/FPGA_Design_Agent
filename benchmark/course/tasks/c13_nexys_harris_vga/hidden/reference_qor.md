# Reference QoR: P13-1

OUT-OF-CONTEXT numbers for the course's pipelined Harris response block only (`labs/p13_vision/harris_resp.sv`); the course's behavioural `harris.sv` and the re-scoped reference's glue
(`harris_detect.sv`: picture store, window scan, corner list) were not built. Source and date: `results/p13_vision_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock 150 MHz).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 6.667 ns | Fmax |
|---|---|---|---|---|---|---|
| `harris_resp.sv` (pipelined, 5 x 5 window) | 3419 | 1171 | 0 | 4 | -7.694 ns | 70 MHz (shell registers included in FF) |

Full-flow QoR of the re-scoped system: **not run**.
