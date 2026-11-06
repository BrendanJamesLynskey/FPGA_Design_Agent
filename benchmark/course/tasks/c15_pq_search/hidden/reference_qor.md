# Reference QoR: p15_pq_search

OUT-OF-CONTEXT numbers for the two blocks the reference top-level joins (the top-level itself was not run). Source: `results/p15_ai_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, 200 MHz, port registers included).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 5 ns | Fmax |
|---|---|---|---|---|---|---|
| `pq_adc` 8 x 16, 20-bit | 331 (224 as memory) | 109 | 0 | 0 | -2.662 ns | 131 MHz |
| `topk` K=8 | 528 | 698 | 0 | 0 | -0.066 ns | 197 MHz |

Full-flow QoR: **not run**.
