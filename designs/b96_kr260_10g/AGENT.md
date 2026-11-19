# AGENT b96_kr260_10g (fda-handover/1)
source: designs/b96_kr260_10g/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b96_kr260_10g

## identity
kind=example produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=kr260_10g_top tool=Vivado 2026.1

## summary
A Kria KR260 design that carries our own 10GBASE-R PCS (64B/66B, scrambler, gearbox, block lock) and a 64-bit Ethernet MAC on one GTH lane at 10.3125 Gb/s, with the mock trading path of brief 58A behind it (a one-rule 64-bit decision in the same message format), because the AMD 10G Ethernet core is refused on the free Basic licence. Verified against an independent Python reference in simulation (the GT is a behavioural stand-in) and built to a bitstream on Vivado 2026.1 Basic with every flow gate passing in two variants; not run on a board.
not: an interoperability proof: a PCS talking to itself accepts its own symmetric mistakes, only a network card proves it; the full 58A trading core (book, rule table, interlocks, ARP) at 64 bits: trade64 is a small stand-in with one rule; the reconciliation sublayer link-fault state machine, the BER monitor, an ARP or ICMP responder

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=fec2fc2f
gates: build_2026_1=pass

## interface
clk clk_25 25MHz
clk sfp_mgt_refclk 156.25MHz
rst reset helper active-high: the register block is reset while the MMCM is unlocked; each path is held in reset while the GT Wizard reports its transmit or receive side not done
if Host register block 32-bit register bus over JTAG (BSCANE2 USER4, jtag_bus): generated from regmap.py; unmapped reads return 0; counters read from a snapshot; reads have no side effects doc=designs/b96_kr260_10g/docs/register_map.md
if SFP+ lane and control pins one GTH lane at 10.3125 Gb/s; tx_disable, mod_abs, rx_los, tx_fault, I2C: the laser is disabled at reset (tx_disable = 1; polarity unconfirmed until the first board run) doc=designs/b96_kr260_10g/docs/board_run_plan.md
param NEAR_END=0 (variant b), 1 (variant a) legal=0 or 1
param TRADE=1 (variant b), 0 (variant a) legal=0 or 1
param line rate=10.3125 Gb/s legal=fixed by 10GBASE-R

## files
designs/b96_kr260_10g/rtl/b96_pkg.sv ac2ee00c42: block codes, scrambler, CRC-32 functions
designs/b96_kr260_10g/rtl/pcs_tx.sv e0e68141d9: transmit PCS (encode, scramble, gearbox)
designs/b96_kr260_10g/rtl/pcs_rx.sv 161c35209b: receive PCS (gearbox with slip, block lock, descramble, decode)
designs/b96_kr260_10g/rtl/mac64_tx.sv 0cbc07b026: 64-bit MAC transmitter
designs/b96_kr260_10g/rtl/mac64_rx.sv 35a0ed74f5: 64-bit MAC receiver
designs/b96_kr260_10g/rtl/frame_src.sv a745598f6a: frame builder for orders, feed, probe and test frames
designs/b96_kr260_10g/rtl/trade64.sv 1999e01a37: the 64-bit mock trading decision
designs/b96_kr260_10g/rtl/tx_path.sv 91039813b5: transmit domain: sources, generator, timestamps
designs/b96_kr260_10g/rtl/rx_path.sv fdfa0f70a8: receive domain: PCS, MAC, decision, counters
designs/b96_kr260_10g/rtl/b96_core.sv bea03470de: registers, GT wrapper and clock-domain crossings
designs/b96_kr260_10g/rtl/kr260_10g_top.sv 79baa37536: board top (MMCM, SYSMON, pins)
designs/b96_kr260_10g/rtl/rate_match.sv 89bdb4e820: rate-matching elastic buffer (idle insert and delete between frames, xpm_fifo_async), brief 96C
designs/b96_kr260_10g/model/ratematch.py 29ed3ac9f2: Python twin of the rate matcher, compared output for output with the RTL
designs/b96_kr260_10g/host/b96c_ppm.py a5a5b3d64e: board driver for the ppm sweep (TX phase-interpolator offset, measured ppm, SYSMON conditions)
designs/b96_kr260_10g/rtl/hs_vec.sv bb5cad4fa9: coherent vector crossing
designs/b96_kr260_10g/model/pcs.py 92790d45d7: bit-serial Python reference of the PCS (the twin)
designs/b96_kr260_10g/design.xdc 4dec8c5ba8: pins, clocks, slow-pin constraints
designs/b96_kr260_10g/docs/design.md 4bf99ccf2c: design note: decisions and alternatives
designs/b96_kr260_10g/docs/board_run_plan.md 678413f0be: stage 3 plan for the board
designs/b96_kr260_10g/docs/what_we_found.md e707017fad: results and gaps
designs/b96_kr260_10g/regmap.py 7970a54355: register map as data
designs/b96_kr260_10g/docs/register_map.md b31f99a6e3: interface datasheet

## commands
simulate the PCS, MAC and core against the Python reference (~2min): python -m pytest -q designs/b96_kr260_10g/tests
[heavy] build variant (b) and run all gates (~22min): flow/run_vivado.sh designs/b96_kr260_10g base
[heavy] build variant (a), the near-end loopback self-test (~22min): flow/run_vivado.sh designs/b96_kr260_10g/selftest base

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py 47e65a97a6
R2 results/b96c/builds/control/digest.json cbe7ba0bca
R3 results/b96/build_a/gates.json fe45f7625c
R4 results/b96/README.md 3fb82e2bc0
R5 results/b96c/builds/control/run.json b63fd6335d
R6 results/b96/latency_sim.json e5453d4c0b
R7 results/b96c/core_sim.json 227e0284e2
R8 results/b96c/builds/all3/digest.json 53fa66d4a7

## evidence
E1 simulation pass R1 ci: PCS and MAC against an independent bit-serial Python model clock for clock; frames in lane 0 and lane 4, every length residue, any bit offset; the whole core with a stand-in for the GT: probe echo, trading loop, decisions, poisoned orders
E2 build pass R2: variant (b) with the 96C rate matcher, synthesis, implementation and bitstream on the Basic tier; every flow gate and every GT gate passes (29 of 29)
E4 build pass R3: variant (a), the near-end loopback self-test, built before brief 96C and not rebuilt with the rate matcher: synthesis, implementation and bitstream; every flow gate and every GT gate passes
E3 review pass R4: one independent correctness review (Sonnet) and one fix round

## measured
M1 resources lut=6613 LUT R2#utilization.lut: LUTs, variant (b) | routed, Vivado 2026.1
M2 resources ff=15,667 FF R2#utilization.ff: registers, variant (b) | as M1
M3 timing wns_ns=0.293 ns R2#timing.wns_ns: worst setup slack, variant (b) | routed, user clocks 161.133 MHz and 100 MHz
M4 timing whs_ns=0.01 ns R2#timing.whs_ns: worst hold slack, variant (b) | as M3
M5 power power_w=0.928 W R2#power.total_w: total on-chip power estimate, variant (b) | report_power after routing, vectorless, confidence Medium
M6 other -=4449 MiB R5#vivado_peak_rss_mib: Vivado peak resident memory of the variant (b) build | 1 thread, MemoryMax=6G scope, one run, no cap hits
M7 latency -=3 clocks R6#tx_clocks_max: transmit latency, worst gearbox phase | simulation, 161.13 MHz clock, MAC output register to the GT word with the last bit of the start block
M8 latency -=13 clocks R7#tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks.max: digital tick-to-trade, worst simulated case with the rate matcher (11 before brief 96C) | simulation, same-phase clocks; GT, optics and clock-crossing phase not included
M9 timing wns_ns_all3=0.004 ns R8#timing.wns_ns: worst setup slack, latency variant all3 with the rate matcher | as M3; the margin is thin

## gaps
[hardware] Nothing has run on a board. The reference clock source and frequency, the 25 MHz input and the SFP+ control pin functions and TX_DISABLE polarity are unconfirmed (third-party example, not the schematic).
[interoperability] The PCS and MAC are checked against a model written by the same author and against zlib and a recurrence; the standard text was not available, so only a network card proves the block formats and scrambler order.
[simulation] The transceiver is a behavioural stand-in because the free simulator refuses the real model; the whole-core bench uses same-phase clocks, so the receive-to-transmit crossing phase is not simulated.
[trading path] trade64 is a one-rule 64-bit stand-in, not the 58A core; orders that overlap are dropped; no cancel after send; the order fields cross as a quasi-static bus (CDC-6 warning).
[protocol] No link-fault state machine, BER monitor, ARP or ICMP responder; ordered sets are counted and shown as idles; receive does not check preamble, runts or jumbo frames; the transmit MAC does not pad.
[throughput] The line rate and the 10 Gb/s payload rate are by configuration and by the gearbox arithmetic; no throughput or error-rate measurement exists because nothing ran on a board.
[build] The 96C builds of the latency variant (all3) and its ppm twin hit the 6 GiB scope cap about 1000 times and used about 700 MiB of swap (the base build did not); the Vivado resident peak of the base build is 4449 MiB. all3 closes timing with 0.004 ns of setup slack, which is thin.

## next_actions
1. Run docs/board_run_plan.md steps 1 to 4 on the KR260 (laser polarity first), then the NIC steps after the owner buys a card and cable.
2. Confirm the reference clock and the control pins against the carrier schematic.
3. Widen the 58A core to 64 bits, or add the missing 58A features to trade64.

## open_questions
- Does the PL load over JTAG with the PS idle on the KR260 (flow/program.py has no KR260 board entry yet)?

## history
2026-11-19 - pr=-: brief 96C: elastic-buffer rate matcher (xpm_fifo_async) in the base design and lat_all3, TX phase-interpolator ppm controls, four builds with all 29 gates, board session pending
2026-11-17 - pr=-: brief 96 stages 0 to 2: board facts, design note, PCS, MAC, trading path, host code, builds; one review round
