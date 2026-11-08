# Reference QoR: P13-1

OUT-OF-CONTEXT numbers for the course's pipelined Harris response block only (`labs/p13_vision/harris_resp.sv`); the course's behavioural `harris.sv` and the re-scoped reference's glue
(`harris_detect.sv`: picture store, window scan, corner list) were not built. Source and date: `results/p13_vision_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock 150 MHz).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 6.667 ns | Fmax |
|---|---|---|---|---|---|---|
| `harris_resp.sv` (pipelined, 5 x 5 window) | 3419 | 1171 | 0 | 4 | -7.694 ns | 70 MHz (shell registers included in FF) |

Full-flow QoR of the re-scoped system: **not run**.


## Whole-board reference build (course v1.3, brief 07a1c)

`tools/ref_build.py`, Vivado 2025.2, xc7a100tcsg324-1, 100 MHz, test shell included; gates all pass (the flow's standards check v1.0 still fails, as for every reference). Numbers from `results/c13_nexys_harris_vga__vivado.json`.

| WNS at 100 MHz | LUT | FF | RAMB36/18 tiles | DSP48 | Power |
|---|---|---|---|---|---|
| +0.485 ns | 11,267 | 5,019 | 14 | 9 | 0.49 W |

The first v1.1 reference (picture and 7 x 7 window as logic, nine responses in parallel) needed about 106,000 LUTs and did not fit (63,400). Now: seven block-RAM picture copies, gradients, products and sums pipelined, one shared response unit (about 17 clocks per pixel).
