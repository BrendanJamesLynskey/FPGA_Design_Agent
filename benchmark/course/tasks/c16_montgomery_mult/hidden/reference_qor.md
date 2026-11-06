# Reference QoR: p16_montgomery_mult

OUT-OF-CONTEXT numbers for the reference blocks. Source and date: `results/p16_crypto_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock 200 MHz, port registers included).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 5 ns | Fmax | RAMB18 |
|---|---|---|---|---|---|---|---|
| `mont64` | 268 | 590 | 0 | 0 | -2.127 ns | 140 MHz | 0 |

These are the datapath block only (the shell names of `labs/p16_crypto/ooc_shells.sv`), not the whole top-level with the UART; full-flow QoR: **not run** (no board, no bitstream).
