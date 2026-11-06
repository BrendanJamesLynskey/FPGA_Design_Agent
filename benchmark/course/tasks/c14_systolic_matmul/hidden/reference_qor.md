# Reference QoR: P14-3

OUT-OF-CONTEXT numbers for the reference block (`matmul4_rows`: the array plus input skew and output de-skew registers). Source and date: `results/p14_ml_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock 200 MHz, port registers included). For the array alone (`systolic4`) see the same file: 1096 LUT, 677 FF, 2 DSP, 133 MHz.

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 5 ns | Fmax |
|---|---|---|---|---|---|---|
| `matmul4_rows` | 1122 (24 as memory) | 774 | 0 | 2 | -2.556 ns | 132 MHz (meets 100 MHz) |

Full-flow QoR: **not run**. Note that Vivado placed the 16 int8 multipliers mostly in LUTs (2 DSP48).
