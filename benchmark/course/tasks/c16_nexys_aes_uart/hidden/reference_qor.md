# Reference QoR: p16_nexys_aes_uart

OUT-OF-CONTEXT numbers for the reference blocks. Source and date: `results/p16_crypto_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock 200 MHz, port registers included).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 5 ns | Fmax | RAMB18 |
|---|---|---|---|---|---|---|---|
| `aes_iter` | 620 | 652 | 0 | 0 | -1.808 ns | 147 MHz | 10 |

These are the datapath block only (the shell names of `labs/p16_crypto/ooc_shells.sv`), not the whole top-level with the UART; full-flow QoR: **not run** (no board, no bitstream).
