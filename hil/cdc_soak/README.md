# CDC soak rig (brief 11b, phase 2a)

A Nexys A7-100T bitstream that runs many copies of correct and deliberately broken clock-domain crossings side by
side, counts every error each copy's checker sees, and reports the counts over the USB-UART. It builds the
phase-1 design (brief 11, kept with the planner's notes). Phase 2a is RTL, simulation and Vivado builds only:
**no board run has been made**; the board plan is in [RUNBOOK.md](RUNBOOK.md). Nothing here is benchmark material.

What it can and cannot show: broken crossings failing (skew, lost pulses, reset races; seconds to minutes), so a
grader (`report_cdc`, simulation with injection) can be checked against hardware. It cannot prove a correct crossing:
0 errors in T copy-hours supports only "MTBF > T/3 per copy at 95 % confidence".

## Clock domains

| Domain | Source | Notes |
|---|---|---|
| a | 100 MHz board oscillator | control, UART, XADC, storm generator |
| b | STARTUPE2 CFGMCLK (internal ring oscillator, typ. 65 MHz, +-50 %) | truly asynchronous; constrained at 10.26 ns; measured by the rig (kHz in each `E` line) |
| c | MMCM output, 100 MHz, dynamic fine phase shift stepped continuously | phase slides through every offset against a |
| f | MMCM output, 250 MHz | source of M6b/M6c only |

Each variant is instantiated for a->b, b->a and a->c (copy k: direction k mod 3, placement class (k + k/3) mod 3:
far X0Y0->X1Y3, near X0Y2 or X1Y2, boundary X0Y1->X1Y1).

## Variants

| ID | Crossing | ID | Mutant |
|---|---|---|---|
| C1 / C2 | hand 2FF / 3FF level synchroniser | M1 | 2 flops, no ASYNC_REG, stages in far pblocks |
| C3a / C3b | xpm_cdc_single, 2 / 4 stages | M1b | one flop, no synchroniser |
| C4 | hand toggle pulse crossing | M2 | one asynchronous bit into two flops, compared |
| C5 | xpm_cdc_pulse | M3 | 12-bit binary counter crossed bit by bit |
| C6 | hand Gray 12-bit + max_delay + bus_skew | M4 | XOR of two coincident toggles before the synchroniser |
| C7 | xpm_cdc_gray 12-bit | M5 | one-cycle pulse into a level synchroniser |
| C8 | hand 4-phase handshake, 16 bits | M6a | Gray without bus_skew/max_delay, bits launched far apart |
| C9 | xpm_cdc_handshake, 16 bits | M6b / M6c | 250 MHz Gray, odd bits padded with 4 / 8 route-through LUTs |
| C10 | hand Cummings async FIFO 16x16 (LUT RAM) | M7 | two flags from one edge, synchronised separately, compared |
| C11 | xpm_fifo_async 512x16 (block RAM), reset by the storms | M8 | source domain's raw reset clears a destination register |
| C12 | reset bridge into 32 flops over two pblocks | M9 | async FIFO reset on the write side only |
| C13 | Cummings FIFO, both sides reset together, reader qualified | M10 | 32 flops released by a raw asynchronous reset |
| | | M11 | 2-phase handshake, source side reset alone |

Copy counts are parameters (`N_<variant>` on `rig_top`/`rig_core`): the small build has one of each (28 copies), the
full build 352 (`tcl/rig_map.tcl`; the design's 536 did not place on the xc7a100t, see [results/](results)).

## Checkers and readout

Every checker sits in the copy's destination domain: event counts against a correct `xpm_cdc_gray` reference at quiet
points, plus a glitch check (level and pulse crossings); a step and one-bit-change check (counters); PRBS-16 word
continuity with one allowed relock per reset event and a 2^16-cycle lock-up watchdog (handshakes and FIFOs); release
coherence (C12/M10); pairwise agreement (M2, M7). Each copy has a record {errors 24 saturating, events 32, lock-ups 8,
relocks 8, saturated 1}. Every 60 s of traffic the sources stop, the domains drain and freeze, and each domain's
records rotate bit by bit through a correct XPM toggle handshake to clk_a and out of the UART as one CRC-8 line per
copy (format in [rtl/rig_ctrl.sv](rtl/rig_ctrl.sv)); traffic resumes. Reset storms (mean about 1 kHz, modes source /
destination / both by epoch) start after 10 minutes and reach only C11-C13 and M8-M11. The XADC stops all traffic
at Tj >= 80 degC.

## Files

| Path | What |
|---|---|
| [rtl/](rtl) | `rig_top` (clocks, STARTUPE2, MMCM, XADC), `rig_core`, `rig_copy` (all variants), checkers, control, Cummings FIFO |
| [sim/](sim) | Icarus top, cocotb benches, behavioural stand-ins for the five XPM macros (simulation only) |
| [tests/](tests) | pytest entries: the rig with injection and storms, the checkers, the host reader |
| [host/read_counters.py](host/read_counters.py) | PC-side reader: CRC check, CSV, stop rules (read only) |
| [constr/rig.xdc](constr/rig.xdc), [tcl/](tcl) | pins and clocks; per-copy exceptions, pblocks and waivers; build; delay table |
| [run_build.sh](run_build.sh) | one Vivado build, memory-capped |
| [results/](results) | simulation summaries, Vivado report extracts, the per-copy delay tables |
| [RUNBOOK.md](RUNBOOK.md) | the owner's smoke-run and soak plan, programming (JTAG to SRAM only), stop rules |

## Reproduce

```bash
python -m pytest -q hil/cdc_soak/tests                  # 3 copies a variant, two seeds (about an hour)
CDC_SIM_QUICK=1 python -m pytest -q hil/cdc_soak/tests  # 1 copy a variant (CI, about 5 minutes)
hil/cdc_soak/run_build.sh small                         # 28 copies; then: run_build.sh full
```
