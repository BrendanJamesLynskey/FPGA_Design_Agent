# b96_kr260_10g: A 10GBASE-R link on the KR260 SFP+ cage: our own PCS and 64-bit MAC with a mock trading path

<!-- Generated from handover.yaml by flow/handover.py (brief 68). Edit handover.yaml, or the text between the prose markers, then run: python -m flow.handover write designs/b96_kr260_10g -->

A Kria KR260 design that carries our own 10GBASE-R PCS (64B/66B, scrambler, gearbox, block lock) and a 64-bit Ethernet MAC on one GTH lane at 10.3125 Gb/s, with the mock trading path of brief 58A behind it (a one-rule 64-bit decision in the same message format), because the AMD 10G Ethernet core is refused on the free Basic licence. Verified against an independent Python reference in simulation (the GT is a behavioural stand-in) and built to a bitstream on Vivado 2026.1 Basic with every flow gate passing in two variants; not run on a board.

Not in scope:

- an interoperability proof: a PCS talking to itself accepts its own symmetric mistakes, only a network card proves it
- the full 58A trading core (book, rule table, interlocks, ARP) at 64 bits: trade64 is a small stand-in with one rule
- the reconciliation sublayer link-fault state machine, the BER monitor, an ARP or ICMP responder

Kind: example; written by hand. State: built. For an agent: [AGENT.md](AGENT.md).

![Block diagram: the design's blocks and the links between them](docs/handover/architecture.svg)

<!-- prose:what -->
<!-- /prose:what -->

## Technical parameters

| Item | Value |
|---|---|
| Part | `xck26-sfvc784-2LV-c` |
| Board | Kria KR260 |
| Top | `kr260_10g_top` |
| Tool | Vivado 2026.1 |
| Note | GTHE4_CHANNEL_X0Y6 of quad 224; SFP+ cage J24; reference MGTREFCLK0 (Y6/Y5); variant (a) is selftest/build.yaml |

Clocks:

- `clk_25`: 25 MHz (from `designs/b96_kr260_10g/design.xdc`); input C3, an open-source example figure, unconfirmed against the schematic; an MMCM makes the 100 MHz free-running clock
- `sfp_mgt_refclk`: 156.25 MHz (from `designs/b96_kr260_10g/design.xdc`); MGTREFCLK0 of quad 224; frequency and source unconfirmed (two third-party sources agree, no AMD document or schematic)

Resets:

- `reset helper`, active high: the register block is reset while the MMCM is unlocked; each path is held in reset while the GT Wizard reports its transmit or receive side not done

Interfaces:

- `Host register block` (32-bit register bus over JTAG (BSCANE2 USER4, jtag_bus)) ([datasheet](docs/register_map.md)): generated from regmap.py; unmapped reads return 0; counters read from a snapshot; reads have no side effects
- `SFP+ lane and control pins` (one GTH lane at 10.3125 Gb/s; tx_disable, mod_abs, rx_los, tx_fault, I2C) ([datasheet](docs/board_run_plan.md)): the laser is disabled at reset (tx_disable = 1; polarity unconfirmed until the first board run)

| Parameter | Value | Legal range | Note |
|---|---|---|---|
| `NEAR_END` | 0 (variant b), 1 (variant a) | 0 or 1 | 1 selects the near-end PMA loopback at reset |
| `TRADE` | 1 (variant b), 0 (variant a) | 0 or 1 | 1 enables the mock trading path at reset; it still needs ARM |
| `line rate` | 10.3125 Gb/s | fixed by 10GBASE-R | QPLL0 from the 156.25 MHz reference; the user clocks (161.133 MHz) carry 64 bits a word and the PCS takes one clock pause in 33 |

| Quantity | Value | Source |
|---|---|---|
| Resources | LUTs, variant (b): 6613 LUT; registers, variant (b): 15,667 FF | M1, M2 |
| Timing | worst setup slack, variant (b): 0.293 ns; worst hold slack, variant (b): 0.01 ns; worst setup slack, latency variant all3 with the rate matcher: 0.004 ns | M3, M4, M9 |
| Power | total on-chip power estimate, variant (b): 0.928 W | M5 |
| Latency | transmit latency, worst gearbox phase: 3 clocks; digital tick-to-trade, worst simulated case with the rate matcher (11 before brief 96C): 13 clocks | M7, M8 |
| Throughput | not measured | [Known gaps](#known-gaps-and-limits) |

![Resource use as a share of the part, and timing slack](docs/handover/resources.svg)

<!-- prose:parameters -->
<!-- /prose:parameters -->

## How to build, run and reproduce

| Step | Command | Heavy slot | Time |
|---|---|---|---|
| simulate the PCS, MAC and core against the Python reference; needs Icarus Verilog and cocotb 2.0.1 | `python -m pytest -q designs/b96_kr260_10g/tests` | no | about 2 min |
| build variant (b) and run all gates; needs local Vivado 2026.1 (Basic tier) and a heavy slot (take_heavy_slot.sh), MEM_MAX=6G reaches the cap | `flow/run_vivado.sh designs/b96_kr260_10g base` | yes | about 22 min |
| build variant (a), the near-end loopback self-test; needs as above | `flow/run_vivado.sh designs/b96_kr260_10g/selftest base` | yes | about 22 min |

Tool: Vivado 2026.1. Build ID of the inputs at handover: `dd5144c3` (`python flow/manifest.py show designs/b96_kr260_10g`: what a rebuild of today's sources and flow would carry; it changes when any build input or the flow changes, so it can differ from the build ID in an older evidence record). Knowledge-bank pin: `93d158c`.

| File | What |
|---|---|
| [`designs/b96_kr260_10g/rtl/b96_pkg.sv`](rtl/b96_pkg.sv) | block codes, scrambler, CRC-32 functions |
| [`designs/b96_kr260_10g/rtl/pcs_tx.sv`](rtl/pcs_tx.sv) | transmit PCS (encode, scramble, gearbox) |
| [`designs/b96_kr260_10g/rtl/pcs_rx.sv`](rtl/pcs_rx.sv) | receive PCS (gearbox with slip, block lock, descramble, decode) |
| [`designs/b96_kr260_10g/rtl/mac64_tx.sv`](rtl/mac64_tx.sv) | 64-bit MAC transmitter |
| [`designs/b96_kr260_10g/rtl/mac64_rx.sv`](rtl/mac64_rx.sv) | 64-bit MAC receiver |
| [`designs/b96_kr260_10g/rtl/frame_src.sv`](rtl/frame_src.sv) | frame builder for orders, feed, probe and test frames |
| [`designs/b96_kr260_10g/rtl/trade64.sv`](rtl/trade64.sv) | the 64-bit mock trading decision |
| [`designs/b96_kr260_10g/rtl/tx_path.sv`](rtl/tx_path.sv) | transmit domain: sources, generator, timestamps |
| [`designs/b96_kr260_10g/rtl/rx_path.sv`](rtl/rx_path.sv) | receive domain: PCS, MAC, decision, counters |
| [`designs/b96_kr260_10g/rtl/b96_core.sv`](rtl/b96_core.sv) | registers, GT wrapper and clock-domain crossings |
| [`designs/b96_kr260_10g/rtl/kr260_10g_top.sv`](rtl/kr260_10g_top.sv) | board top (MMCM, SYSMON, pins) |
| [`designs/b96_kr260_10g/rtl/rate_match.sv`](rtl/rate_match.sv) | rate-matching elastic buffer (idle insert and delete between frames, xpm_fifo_async), brief 96C |
| [`designs/b96_kr260_10g/model/ratematch.py`](model/ratematch.py) | Python twin of the rate matcher, compared output for output with the RTL |
| [`designs/b96_kr260_10g/host/b96c_ppm.py`](host/b96c_ppm.py) | board driver for the ppm sweep (TX phase-interpolator offset, measured ppm, SYSMON conditions) |
| [`designs/b96_kr260_10g/rtl/hs_vec.sv`](rtl/hs_vec.sv) | coherent vector crossing |
| [`designs/b96_kr260_10g/model/pcs.py`](model/pcs.py) | bit-serial Python reference of the PCS (the twin) |
| [`designs/b96_kr260_10g/design.xdc`](design.xdc) | pins, clocks, slow-pin constraints |
| [`designs/b96_kr260_10g/docs/design.md`](docs/design.md) | design note: decisions and alternatives |
| [`designs/b96_kr260_10g/docs/board_run_plan.md`](docs/board_run_plan.md) | stage 3 plan for the board |
| [`designs/b96_kr260_10g/docs/what_we_found.md`](docs/what_we_found.md) | results and gaps |
| [`designs/b96_kr260_10g/regmap.py`](regmap.py) | register map as data |
| [`designs/b96_kr260_10g/docs/register_map.md`](docs/register_map.md) | interface datasheet |

<!-- prose:build -->
<!-- /prose:build -->

## Verified

![Verification matrix: each activity and its result](docs/handover/verification.svg)

| ID | Activity | Result | What | Evidence | Conditions |
|---|---|---|---|---|---|
| E1 | simulation | pass | PCS and MAC against an independent bit-serial Python model clock for clock; frames in lane 0 and lane 4, every length residue, any bit offset; the whole core with a stand-in for the GT: probe echo, trading loop, decisions, poisoned orders | [`designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py`](tests/test_b96_pcs_rtl.py) (run in CI) | - |
| E2 | build | pass | variant (b) with the 96C rate matcher, synthesis, implementation and bitstream on the Basic tier; every flow gate and every GT gate passes (29 of 29) | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) | - |
| E4 | build | pass | variant (a), the near-end loopback self-test, built before brief 96C and not rebuilt with the rate matcher: synthesis, implementation and bitstream; every flow gate and every GT gate passes | [`results/b96/build_a/gates.json`](../../results/b96/build_a/gates.json) | - |
| E3 | review | pass | one independent correctness review (Sonnet) and one fix round | [`results/b96/README.md`](../../results/b96/README.md) | - |

Gates at handover: `build_2026_1` pass.

<!-- prose:verified -->
<!-- /prose:verified -->

## Measured

Every value is read from the record by `python -m flow.handover fill`, not typed.

| ID | What | Value | Runs | Source | Conditions |
|---|---|---|---|---|---|
| M1 | LUTs, variant (b) | 6613 LUT | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `utilization.lut` | routed, Vivado 2026.1 |
| M2 | registers, variant (b) | 15,667 FF | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `utilization.ff` | as M1 |
| M3 | worst setup slack, variant (b) | 0.293 ns | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `timing.wns_ns` | routed, user clocks 161.133 MHz and 100 MHz |
| M4 | worst hold slack, variant (b) | 0.01 ns | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `timing.whs_ns` | as M3 |
| M5 | total on-chip power estimate, variant (b) | 0.928 W | 1 | [`results/b96c/builds/control/digest.json`](../../results/b96c/builds/control/digest.json) `power.total_w` | report_power after routing, vectorless, confidence Medium |
| M6 | Vivado peak resident memory of the variant (b) build | 4449 MiB | 1 | [`results/b96c/builds/control/run.json`](../../results/b96c/builds/control/run.json) `vivado_peak_rss_mib` | 1 thread, MemoryMax=6G scope, one run, no cap hits |
| M7 | transmit latency, worst gearbox phase | 3 clocks | 1 | [`results/b96/latency_sim.json`](../../results/b96/latency_sim.json) `tx_clocks_max` | simulation, 161.13 MHz clock, MAC output register to the GT word with the last bit of the start block |
| M8 | digital tick-to-trade, worst simulated case with the rate matcher (11 before brief 96C) | 13 clocks | 1 | [`results/b96c/core_sim.json`](../../results/b96c/core_sim.json) `tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks.max` | simulation, same-phase clocks; GT, optics and clock-crossing phase not included |
| M9 | worst setup slack, latency variant all3 with the rate matcher | 0.004 ns | 1 | [`results/b96c/builds/all3/digest.json`](../../results/b96c/builds/all3/digest.json) `timing.wns_ns` | as M3; the margin is thin |

<!-- prose:measured -->
<!-- /prose:measured -->

## Known gaps and limits

- **hardware**: Nothing has run on a board. The reference clock source and frequency, the 25 MHz input and the SFP+ control pin functions and TX_DISABLE polarity are unconfirmed (third-party example, not the schematic).
- **interoperability**: The PCS and MAC are checked against a model written by the same author and against zlib and a recurrence; the standard text was not available, so only a network card proves the block formats and scrambler order.
- **simulation**: The transceiver is a behavioural stand-in because the free simulator refuses the real model; the whole-core bench uses same-phase clocks, so the receive-to-transmit crossing phase is not simulated.
- **trading path**: trade64 is a one-rule 64-bit stand-in, not the 58A core; orders that overlap are dropped; no cancel after send; the order fields cross as a quasi-static bus (CDC-6 warning).
- **protocol**: No link-fault state machine, BER monitor, ARP or ICMP responder; ordered sets are counted and shown as idles; receive does not check preamble, runts or jumbo frames; the transmit MAC does not pad.
- **throughput**: The line rate and the 10 Gb/s payload rate are by configuration and by the gearbox arithmetic; no throughput or error-rate measurement exists because nothing ran on a board.
- **build**: The 96C builds of the latency variant (all3) and its ppm twin hit the 6 GiB scope cap about 1000 times and used about 700 MiB of swap (the base build did not); the Vivado resident peak of the base build is 4449 MiB. all3 closes timing with 0.004 ns of setup slack, which is thin.

<!-- prose:gaps -->
<!-- /prose:gaps -->

## Next steps

1. Run docs/board_run_plan.md steps 1 to 4 on the KR260 (laser polarity first), then the NIC steps after the owner buys a card and cable.
2. Confirm the reference clock and the control pins against the carrier schematic.
3. Widen the 58A core to 64 bits, or add the missing 58A features to trade64.

Open questions:

- Does the PL load over JTAG with the PS idle on the KR260 (flow/program.py has no KR260 board entry yet)?

<!-- prose:next -->
<!-- /prose:next -->

## History

| Date | Brief | PR | What |
|---|---|---|---|
| 2026-11-19 | - | - | brief 96C: elastic-buffer rate matcher (xpm_fifo_async) in the base design and lat_all3, TX phase-interpolator ppm controls, four builds with all 29 gates, board session pending |
| 2026-11-17 | - | - | brief 96 stages 0 to 2: board facts, design note, PCS, MAC, trading path, host code, builds; one review round |

<!-- prose:history -->
<!-- /prose:history -->
