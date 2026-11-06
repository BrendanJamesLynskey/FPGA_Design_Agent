# Reference QoR: P14-1

OUT-OF-CONTEXT numbers for the course's whole tiny CNN core (`tiny_cnn.sv`, one MAC, memories as arrays) only; the loader, UART and the board top (`cnn_system.sv`, `cnn_nexys_top_ref.sv`) were simulated but not built. Source and date: `results/p14_ml_ooc.md` (2026-11-05, Vivado 2025.2, xc7a100tcsg324-1, clock constraint 200 MHz).

| Block | LUT | FF | RAMB36 | DSP48 | WNS at 5 ns | Fmax |
|---|---|---|---|---|---|---|
| `tiny_cnn.sv` | 2484 (594 as memory) | 1016 | 0 | 7 | -14.017 ns | 53 MHz (does not meet 100 MHz as written) |

Full-flow QoR of the complete design (WNS at 100 MHz, power, Tj): **not run**. Simulation: 7941 clocks per image.
