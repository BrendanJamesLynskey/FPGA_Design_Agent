# AGENT b96_kr260_10g (fda-handover/1)
source: designs/b96_kr260_10g/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b96_kr260_10g

## identity
kind=example produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=kr260_10g_top tool=Vivado 2026.1

## summary
A Kria KR260 design that carries our own 10GBASE-R PCS (64B/66B, scrambler, gearbox, block lock) and a 64-bit Ethernet MAC on one GTH lane at 10.3125 Gb/s, with the mock trading path of brief 58A behind it (a one-rule 64-bit decision in the same message format), because the AMD 10G Ethernet core is refused on the free Basic licence. Verified against an independent Python reference in simulation (the GT is a behavioural stand-in) and built to a bitstream on Vivado 2026.1 Basic with every flow gate passing in two variants. Brief 96C added a rate-matching elastic buffer as a build option (default off, the board-proven 97C receive path); the base and its rate-matched variants have run on a KR260 optical loopback, not yet against a network card or a second reference clock.
not: an interoperability proof: a PCS talking to itself accepts its own symmetric mistakes, only a network card proves it; the full 58A trading core (book, rule table, interlocks, ARP) at 64 bits: trade64 is a small stand-in with one rule; the reconciliation sublayer link-fault state machine, the BER monitor, an ARP or ICMP responder

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=114de4b3
gates: build_2026_1=pass

## interface
clk clk_25 25MHz
clk sfp_mgt_refclk 156.25MHz
rst reset helper active-high: the register block is reset while the MMCM is unlocked; each path is held in reset while the GT Wizard reports its transmit or receive side not done
if Host register block 32-bit register bus over JTAG (BSCANE2 USER4, jtag_bus): generated from regmap.py; unmapped reads return 0; counters read from a snapshot; reads have no side effects doc=designs/b96_kr260_10g/docs/register_map.md
if SFP+ lane and control pins one GTH lane at 10.3125 Gb/s; tx_disable, mod_abs, rx_los, tx_fault, I2C: the laser is disabled at reset (tx_disable = 1; polarity unconfirmed until the first board run) doc=designs/b96_kr260_10g/docs/board_run_plan.md
param NEAR_END=0 (variant b), 1 (variant a) legal=0 or 1
param TRADE=1 (variant b), 0 (variant a) legal=0 or 1
param RATE_MATCH=0 (default), 1 (the 96C elastic buffer) legal=0 or 1
param EYESCAN=0 (default), 1 (the eyescan build) legal=0 or 1
param RM_OWN=0 (default), 1 (the 96E own gray-pointer buffer) legal=0 or 1
param GO_REG=1 (default), 0 in lat_all3 legal=0 or 1
param line rate=10.3125 Gb/s legal=fixed by 10GBASE-R

## files
designs/b96_kr260_10g/rtl/es_ctrl.sv 671362a1c0: DRP master and eye-scan point sequencer for the GTHE4 channel (EYESCAN = 1), brief 96D
designs/b96_kr260_10g/es.xdc 9f571dada7: powers up the GT's eye-scan circuit (ES_EYE_SCAN_EN, ES_ERRDET_EN) in the eyescan build
designs/b96_kr260_10g/model/eyescan.py 9e408b13c6: Python twin of the eye-scan point sequencer's DRP traffic
designs/b96_kr260_10g/tests/eyescan_cocotb.py b6da9be062: cocotb bench of the sequencer against the twin and a DRP stand-in
designs/b96_kr260_10g/rtl/b96_pkg.sv ac2ee00c42: block codes, scrambler, CRC-32 functions
designs/b96_kr260_10g/rtl/pcs_tx.sv e0e68141d9: transmit PCS (encode, scramble, gearbox)
designs/b96_kr260_10g/rtl/pcs_rx.sv 161c35209b: receive PCS (gearbox with slip, block lock, descramble, decode)
designs/b96_kr260_10g/rtl/mac64_tx.sv 0cbc07b026: 64-bit MAC transmitter
designs/b96_kr260_10g/rtl/mac64_rx.sv 35a0ed74f5: 64-bit MAC receiver
designs/b96_kr260_10g/rtl/frame_src.sv a745598f6a: frame builder for orders, feed, probe and test frames
designs/b96_kr260_10g/rtl/trade64.sv 1999e01a37: the 64-bit mock trading decision
designs/b96_kr260_10g/rtl/tx_path.sv 91039813b5: transmit domain: sources, generator, timestamps
designs/b96_kr260_10g/rtl/rx_path.sv 51c39177f6: receive domain: PCS, MAC, decision, counters
designs/b96_kr260_10g/rtl/b96_core.sv 21d71bff9b: registers, GT wrapper and clock-domain crossings
designs/b96_kr260_10g/rtl/kr260_10g_top.sv bcd50deb41: board top (MMCM, SYSMON, pins)
designs/b96_kr260_10g/rtl/rx_path_legacy.sv 4c9412a3ce: the 97C receive path (main 6909e43f), used when RATE_MATCH = 0
designs/b96_kr260_10g/rtl/rate_match.sv 99afaeec54: rate-matching elastic buffer (idle insert and delete between frames, xpm_fifo_async), brief 96C
designs/b96_kr260_10g/rtl/rate_match_gp.sv b598699be8: low-latency elastic buffer with our own gray-pointer crossing (RM_OWN = 1), brief 96E
designs/b96_kr260_10g/model/ratematch.py 1f19d534d0: Python twin of the rate matcher, compared output for output with the RTL
designs/b96_kr260_10g/host/b96c_ppm.py a5a5b3d64e: board driver for the ppm sweep (TX phase-interpolator offset, measured ppm, SYSMON conditions)
designs/b96_kr260_10g/rtl/hs_vec.sv bb5cad4fa9: coherent vector crossing
designs/b96_kr260_10g/model/pcs.py 92790d45d7: bit-serial Python reference of the PCS (the twin)
designs/b96_kr260_10g/design.xdc 4dec8c5ba8: pins, clocks, slow-pin constraints
designs/b96_kr260_10g/docs/design.md 79f1ae4aad: design note: decisions and alternatives
designs/b96_kr260_10g/docs/board_run_plan.md 678413f0be: stage 3 plan for the board
designs/b96_kr260_10g/docs/what_we_found.md 376623bbd5: results and gaps
designs/b96_kr260_10g/regmap.py 5146c294c8: register map as data
designs/b96_kr260_10g/docs/register_map.md eb9e177aa2: interface datasheet

## commands
simulate the PCS, MAC and core against the Python reference (~2min): python -m pytest -q designs/b96_kr260_10g/tests
[heavy] build variant (b) and run all gates (~22min): flow/run_vivado.sh designs/b96_kr260_10g base
[heavy] build variant (a), the near-end loopback self-test (~22min): flow/run_vivado.sh designs/b96_kr260_10g/selftest base

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py 20c8500b7a
R2 results/b96c/builds/control/digest.json f4c148e6e1
R3 results/b96c/eqy_default/result_default.txt 0144f4bfb6
R4 results/b96c/hw/20261119_080724/control/stage3.json 269183b66c
R5 results/b96/build_a/gates.json fe45f7625c
R6 results/b96/README.md 3fb82e2bc0
R7 results/b96e/core_lat_sim.json 227305d43f
R8 results/b96e/builds/rm_gp/digest.json 8eabb05bcc
R9 results/b96c/builds/control/run.json 699ba4c7ee
R10 results/b96/latency_sim.json e5453d4c0b
R11 results/b96c/core_sim.json 227e0284e2
R12 results/b96c/core_sim_default.json 21559dbac7
R13 results/b96c/builds/rm_all3/digest.json 53fa66d4a7

## evidence
E1 simulation pass R1 ci: PCS and MAC against an independent bit-serial Python model clock for clock; frames in lane 0 and lane 4, every length residue, any bit offset; the whole core with a stand-in for the GT: probe echo, trading loop, decisions, poisoned orders
E2 build pass R2: variant (b), the default build (RATE_MATCH = 0, the 97C receive path; rebuilt for brief 96C addendum 2), synthesis, implementation and bitstream on the Basic tier; every flow gate and every GT gate passes (29 of 29)
E5 formal pass R3: the RATE_MATCH = 0 core is equivalent to main 6909e43f's core (eqy, slang front end, OSS CAD Suite; XPM crossings as wires, GT a black box, the 96C-only registers cut from the proof copy: see results/b96c/eqy_default/README.md); a planted change in the MAC error counter fails it
E6 board pass R4: the rate-matched builds (RATE_MATCH = 1, from f47986f4) on a KR260 optical loopback: safety accepted on all four variants (100 of 100 restarts locked, 500 of 500 orders sent = fired = order_ok per variant, every fault counter 0, SYSMON inside the DS925 windows); the TX phase-interpolator route gave no relative offset (0.0 ppm at every code; non-zero targets recorded unreachable), so rate matching under a real offset is not shown on hardware; the buffer costs 11 clocks of loop latency | cond: KR260, SFP+ optical loopback, Vivado 2026.1 bitstreams of 2026-11-19, 100 restarts a variant, 20 s dwell at 0 ppm
E4 build pass R5: variant (a), the near-end loopback self-test, built before brief 96C and not rebuilt with the rate matcher: synthesis, implementation and bitstream; every flow gate and every GT gate passes
E3 review pass R6: one independent correctness review (Sonnet) and one fix round
E7 simulation pass R7: whole core in xsim with AMD's real XPM macros, four clock phases: tick-to-trade of the 97C path, of the xpm_fifo_async buffer and of the own gray-pointer buffer (RM_OWN = 1); the numbers and the accounting of the board's loop-latency increase are in design.md section 11
E8 build pass R8: build rm_gp (RATE_MATCH = 1, RM_OWN = 1), all 29 gates, WNS +0.105 ns, WHS +0.011 ns, stamp 1a2fa1a8 recomputed from the tree; not loaded on a board

## measured
M1 resources lut=6167 LUT R2#utilization.lut: LUTs, variant (b) | routed, Vivado 2026.1
M2 resources ff=14,183 FF R2#utilization.ff: registers, variant (b) | as M1
M3 timing wns_ns=0.221 ns R2#timing.wns_ns: worst setup slack, variant (b) | routed, user clocks 161.133 MHz and 100 MHz
M4 timing whs_ns=0.011 ns R2#timing.whs_ns: worst hold slack, variant (b) | as M3
M5 power power_w=1.087 W R2#power.total_w: total on-chip power estimate, variant (b) | report_power after routing, vectorless, confidence Medium
M6 other -=4439 MiB R9#vivado_peak_rss_mib: Vivado peak resident memory of the variant (b) build | 1 thread, MemoryMax=6G scope, one run, no cap hits
M7 latency -=3 clocks R10#tx_clocks_max: transmit latency, worst gearbox phase | simulation, 161.13 MHz clock, MAC output register to the GT word with the last bit of the start block
M8 latency -=13 clocks R11#tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks.max: digital tick-to-trade, worst simulated case with the rate matcher (RATE_MATCH = 1) | simulation, same-phase clocks, the Icarus stand-in of the FIFO macro; GT, optics and clock-crossing phase not included; the board measured 11 clocks more than 97C, see E6 and design.md section 9
M10 latency tick_to_trade_default_clocks=11 clocks R12#tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks: digital tick-to-trade, simulation of the default build (RATE_MATCH = 0, the 97C path) | simulation, same-phase clocks; as M8
M9 timing wns_ns_all3=0.004 ns R13#timing.wns_ns: worst setup slack, latency variant all3 with the rate matcher (RATE_MATCH = 1) | as M3; the margin is thin
M11 latency tick_to_trade_own_buffer_clocks=11.88 clocks R7#results.rate_match_1_rm_own_1.1550.tick_to_trade.mean: GT-port tick-to-trade in simulation with AMD's real macros, own gray-pointer buffer (RM_OWN = 1), mean over four phases at phase 1550 ps | xsim 2026.1, whole core, GT stand-in, phase 1550 ps between the clocks; the 97C path is 10.75 and the xpm_fifo_async buffer 16.0 at the same phase; the board has not measured this build

## gaps
[hardware] The design has run on a KR260 optical loopback only (briefs 97 and 96C), never against a network card or a second reference clock, so rate matching (RATE_MATCH = 1) has not been seen under a real frequency offset; the TX phase-interpolator route gave none. The reference clock source and frequency, the 25 MHz input and the SFP+ control pin functions are unconfirmed against the schematic (third-party example).
[interoperability] The PCS and MAC are checked against a model written by the same author and against zlib and a recurrence; the standard text was not available, so only a network card proves the block formats and scrambler order.
[simulation] The transceiver is a behavioural stand-in because the free simulator refuses the real model; the whole-core bench uses same-phase clocks, so the receive-to-transmit crossing phase is not simulated.
[trading path] trade64 is a one-rule 64-bit stand-in, not the 58A core; orders that overlap are dropped; no cancel after send; the order fields cross as a quasi-static bus (CDC-6 warning).
[protocol] No link-fault state machine, BER monitor, ARP or ICMP responder; ordered sets are counted and shown as idles; receive does not check preamble, runts or jumbo frames; the transmit MAC does not pad.
[throughput] The line rate and the 10 Gb/s payload rate are by configuration and by the gearbox arithmetic; no throughput or error-rate measurement exists because nothing ran on a board.
[build] The 96C builds of the latency variant with the buffer (rm_all3) and its ppm twin hit the 6 GiB scope cap about 1000 times and used about 700 MiB of swap (the base build did not); the Vivado resident peak of the base build is 4439 MiB. all3 closes timing with 0.004 ns of setup slack, which is thin.

## next_actions
1. Run docs/board_run_plan.md steps 1 to 4 on the KR260 (laser polarity first), then the NIC steps after the owner buys a card and cable.
2. Confirm the reference clock and the control pins against the carrier schematic.
3. Widen the 58A core to 64 bits, or add the missing 58A features to trade64.

## open_questions
- Does the PL load over JTAG with the PS idle on the KR260 (flow/program.py has no KR260 board entry yet)?

## history
2026-11-19 - pr=-: brief 96E: own gray-pointer elastic buffer (RM_OWN), +1.2 clocks of tick-to-trade over 97C in xsim against +5.3 for the macro buffer; the board's +11 accounted (1.25 left in D); build rm_gp with all 29 gates; board run and real-offset plan pending the owner
2026-11-19 - pr=-: brief 96D: on-chip RX eye scan (EYESCAN build option, es_ctrl, flow/eyescan); built with all 29 gates; simulated against a stand-in; not yet run on the board
2026-11-19 - pr=-: brief 96C addendum 2: RATE_MATCH build parameter, default 0 (the 97C path, shown equivalent by eqy and the 97C bench); the board measured the buffer at +11 clocks and no relative offset by the TX phase interpolator
2026-11-19 - pr=-: brief 96C: elastic-buffer rate matcher (xpm_fifo_async) in the base design and lat_all3, TX phase-interpolator ppm controls, four builds with all 29 gates, board session pending
2026-11-17 - pr=-: brief 96 stages 0 to 2: board facts, design note, PCS, MAC, trading path, host code, builds; one review round
