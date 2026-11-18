# AGENT b96_kr260_10g (fda-handover/1)
source: designs/b96_kr260_10g/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b96_kr260_10g

## identity
kind=example produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=kr260_10g_top tool=Vivado 2026.1

## summary
A Kria KR260 design that carries our own 10GBASE-R PCS (64B/66B, scrambler, gearbox, block lock) and a 64-bit Ethernet MAC on one GTH lane at 10.3125 Gb/s, with the mock trading path of brief 58A behind it (a one-rule 64-bit decision in the same message format), because the AMD 10G Ethernet core is refused on the free Basic licence. Verified against an independent Python reference in simulation (the GT is a behavioural stand-in) and built to a bitstream on Vivado 2026.1 Basic with every flow gate passing in two variants; not run on a board.
not: an interoperability proof: a PCS talking to itself accepts its own symmetric mistakes, only a network card proves it; the full 58A trading core (book, rule table, interlocks, ARP) at 64 bits: trade64 is a small stand-in with one rule; the reconciliation sublayer link-fault state machine, the BER monitor, an ARP or ICMP responder

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=c4786c4b
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
designs/b96_kr260_10g/rtl/b96_pkg.sv 6fdf7f5fec: block codes, scrambler, CRC-32 functions
designs/b96_kr260_10g/rtl/pcs_tx.sv e0e68141d9: transmit PCS (encode, scramble, gearbox)
designs/b96_kr260_10g/rtl/pcs_rx.sv 0065dd34d9: receive PCS (gearbox with slip, block lock, descramble, decode)
designs/b96_kr260_10g/rtl/mac64_tx.sv 0cbc07b026: 64-bit MAC transmitter
designs/b96_kr260_10g/rtl/mac64_rx.sv 35a0ed74f5: 64-bit MAC receiver
designs/b96_kr260_10g/rtl/frame_src.sv 2b72ce74c5: frame builder for orders, feed, probe and test frames
designs/b96_kr260_10g/rtl/trade64.sv 09b28ff824: the 64-bit mock trading decision
designs/b96_kr260_10g/rtl/tx_path.sv 96f37455a0: transmit domain: sources, generator, timestamps
designs/b96_kr260_10g/rtl/rx_path.sv d17b21f834: receive domain: PCS, MAC, decision, counters
designs/b96_kr260_10g/rtl/b96_core.sv 87e4a5d7d8: registers, GT wrapper and clock-domain crossings
designs/b96_kr260_10g/rtl/kr260_10g_top.sv 79baa37536: board top (MMCM, SYSMON, pins)
designs/b96_kr260_10g/rtl/hs_vec.sv bb5cad4fa9: coherent vector crossing
designs/b96_kr260_10g/model/pcs.py 92790d45d7: bit-serial Python reference of the PCS (the twin)
designs/b96_kr260_10g/design.xdc 4dec8c5ba8: pins, clocks, slow-pin constraints
designs/b96_kr260_10g/docs/design.md f410e6c00f: design note: decisions and alternatives
designs/b96_kr260_10g/docs/board_run_plan.md 61aea50d7d: stage 3 plan for the board
designs/b96_kr260_10g/docs/what_we_found.md d1095afbeb: results and gaps
designs/b96_kr260_10g/regmap.py 60923fc43a: register map as data
designs/b96_kr260_10g/docs/register_map.md a4f09edf86: interface datasheet

## commands
simulate the PCS, MAC and core against the Python reference (~2min): python -m pytest -q designs/b96_kr260_10g/tests
[heavy] build variant (b) and run all gates (~22min): flow/run_vivado.sh designs/b96_kr260_10g base
[heavy] build variant (a), the near-end loopback self-test (~22min): flow/run_vivado.sh designs/b96_kr260_10g/selftest base

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py 5c76fb4bc0
R2 results/b96/build_b/gates.json 935b96de0d
R3 results/b96/build_a/gates.json fe45f7625c
R4 results/b96/README.md 3fb82e2bc0
R5 results/b96/build_b/run.json 830cf90442
R6 results/b96/latency_sim.json e5453d4c0b
R7 results/b96/core_sim.json b1ba6d48f8

## evidence
E1 simulation pass R1 ci: PCS and MAC against an independent bit-serial Python model clock for clock; frames in lane 0 and lane 4, every length residue, any bit offset; the whole core with a stand-in for the GT: probe echo, trading loop, decisions, poisoned orders
E2 build pass R2: variant (b) synthesis, implementation and bitstream on the Basic tier; every flow gate and every GT gate passes
E4 build pass R3: variant (a), the near-end loopback self-test: synthesis, implementation and bitstream; every flow gate and every GT gate passes
E3 review pass R4: one independent correctness review (Sonnet) and one fix round

## measured
M1 resources lut=5954 LUT R2#utilization.lut: LUTs, variant (b) | routed, Vivado 2026.1
M2 resources ff=13,657 FF R2#utilization.ff: registers, variant (b) | as M1
M3 timing wns_ns=0.115 ns R2#timing.wns_ns: worst setup slack, variant (b) | routed, user clocks 161.133 MHz and 100 MHz
M4 timing whs_ns=0.01 ns R2#timing.whs_ns: worst hold slack, variant (b) | as M3
M5 power power_w=1.068 W R2#power.total_w: total on-chip power estimate, variant (b) | report_power after routing, vectorless, confidence Medium
M6 other -=3893 MiB R5#vivado_peak_rss_mib: Vivado peak resident memory of the variant (b) build | 2 threads, MemoryMax=6G reached, one run
M7 latency -=3 clocks R6#tx_clocks_max: transmit latency, worst gearbox phase | simulation, 161.13 MHz clock, MAC output register to the GT word with the last bit of the start block
M8 latency -=11 clocks R7#tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks: digital tick-to-trade | simulation, same-phase clocks; GT, optics and clock-crossing phase not included

## gaps
[hardware] Nothing has run on a board. The reference clock source and frequency, the 25 MHz input and the SFP+ control pin functions and TX_DISABLE polarity are unconfirmed (third-party example, not the schematic).
[interoperability] The PCS and MAC are checked against a model written by the same author and against zlib and a recurrence; the standard text was not available, so only a network card proves the block formats and scrambler order.
[simulation] The transceiver is a behavioural stand-in because the free simulator refuses the real model; the whole-core bench uses same-phase clocks, so the receive-to-transmit crossing phase is not simulated.
[trading path] trade64 is a one-rule 64-bit stand-in, not the 58A core; orders that overlap are dropped; no cancel after send; the order fields cross as a quasi-static bus (CDC-6 warning).
[protocol] No link-fault state machine, BER monitor, ARP or ICMP responder; ordered sets are counted and shown as idles; receive does not check preamble, runts or jumbo frames; the transmit MAC does not pad.
[throughput] The line rate and the 10 Gb/s payload rate are by configuration and by the gearbox arithmetic; no throughput or error-rate measurement exists because nothing ran on a board.
[build] Both builds run at the 6 GiB memory cap and swap (thousands of cap hits in the run records); the Vivado resident peak is 3893 MiB.

## next_actions
1. Run docs/board_run_plan.md steps 1 to 4 on the KR260 (laser polarity first), then the NIC steps after the owner buys a card and cable.
2. Confirm the reference clock and the control pins against the carrier schematic.
3. Widen the 58A core to 64 bits, or add the missing 58A features to trade64.

## open_questions
- Does the PL load over JTAG with the PS idle on the KR260 (flow/program.py has no KR260 board entry yet)?

## history
2026-11-17 - pr=-: brief 96 stages 0 to 2: board facts, design note, PCS, MAC, trading path, host code, builds; one review round
