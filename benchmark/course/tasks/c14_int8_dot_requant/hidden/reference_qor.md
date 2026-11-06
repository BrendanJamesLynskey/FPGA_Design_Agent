# Reference QoR: P14-2

OUT-OF-CONTEXT numbers for the reference block (`dot_requant`, N = 8). Source and date: `results/p14_ml_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock 200 MHz, port registers included).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 5 ns | Fmax |
|---|---|---|---|---|---|---|
| `dot_requant` N = 8 | 882 | 265 | 0 | 2 | -26.957 ns | 31 MHz (one combinational stage; needs pipeline registers for 100 MHz) |

Full-flow QoR: **not run**.
