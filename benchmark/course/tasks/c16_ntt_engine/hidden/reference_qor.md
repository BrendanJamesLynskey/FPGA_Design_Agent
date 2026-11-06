# Reference QoR: p16_ntt_engine

OUT-OF-CONTEXT numbers for the reference blocks. Source and date: `results/p16_crypto_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock 200 MHz, port registers included).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 5 ns | Fmax | RAMB18 |
|---|---|---|---|---|---|---|---|
| `ntt_engine` | 17806 | 3241 | 0 | 9 | -27.502 ns | 31 MHz | 0 |

**ntt_engine: placed, not routed** (the router did not converge in 20 minutes on this block or on the multiplier inside it); the Fmax is an estimate from the placed design and the LUT count is exact.

These are the datapath block only (the shell names of `labs/p16_crypto/ooc_shells.sv`), not the whole top-level with the UART; full-flow QoR: **not run** (no board, no bitstream).
