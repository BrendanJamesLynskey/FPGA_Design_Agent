# AGENT b96_kr260_10g (fda-handover/1)
source: designs/b96_kr260_10g/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b96_kr260_10g

## identity
kind=example produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=kr260_10g_top tool=Vivado 2026.1

## summary
A Kria KR260 design that carries our own 10GBASE-R PCS (64B/66B, scrambler, gearbox, block lock) and a 64-bit Ethernet MAC on one GTH lane at 10.3125 Gb/s, with the mock trading path of brief 58A behind it (a one-rule 64-bit decision in the same message format), because the AMD 10G Ethernet core is refused on the free Basic licence. Verified against an independent Python reference in simulation (the GT is a behavioural stand-in) and built to a bitstream on Vivado 2026.1 Basic with every flow gate passing in two variants. Brief 96C added a rate-matching elastic buffer as a build option (default off, the board-proven 97C receive path); the base and its rate-matched variants have run on a KR260 optical loopback, not yet against a network card or a second reference clock.
not: an interoperability proof: a PCS talking to itself accepts its own symmetric mistakes, only a network card proves it; the full 58A trading core (book, rule table, interlocks, ARP) at 64 bits: trade64 is a small stand-in with one rule; the reconciliation sublayer link-fault state machine, the BER monitor, an ARP or ICMP responder

## state
stage=built vivado=2026.1 kb_pin=5e2eab8 build_id=f387f9e5
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
param RM_DIRECT=0 (default), 1 (build rm_gp_direct) legal=0 or 1
param GO_REG=1 (default), 0 in lat_all3 legal=0 or 1
param line rate=10.3125 Gb/s legal=fixed by 10GBASE-R

## files
designs/b96_kr260_10g/dbg_xvc/rtl/xvc_debug.sv 13459b988d: the debug path of build dbg_xvc: PS AXI master, AXI4 to AXI4-Lite converter, Debug Bridge (AXI to BSCAN) and one ILA on status taps (brief 131)
designs/b96_kr260_10g/dbg_xvc/rtl/b96_core.sv f97848c5f7: copy of rtl/b96_core.sv for build dbg_xvc with three read-only tap ports for the debug ILA (brief 131)
designs/b96_kr260_10g/dbg_xvc/rtl/kr260_10g_top.sv ca47f11df2: copy of rtl/kr260_10g_top.sv for build dbg_xvc with the debug path instantiated (brief 131)
designs/b96_kr260_10g/dbg_xvc/build.yaml 241abf02aa: how flow/run_vivado.sh builds dbg_xvc (the eyescan build plus the debug path, brief 131)
designs/b96_kr260_10g/ip/amd_ip_xvc.tcl 322bd679d3: the AMD IP of build dbg_xvc: Zynq UltraScale+ PS, AXI Protocol Converter, Debug Bridge, ILA (brief 131)
designs/b96_kr260_10g/dbg_xvc/docs/dbg_xvc.md afd7cf480e: what build dbg_xvc is, what the ILA watches and why, what the debug logic changes, measured against the parent build (brief 131)
designs/b96_kr260_10g/dbg_xvc/docs/xvc_board_side.md b5fcf54a03: how XVC would run on the KR260's Ubuntu: which variant fits, the overlay, the Vivado connection; written, not run (brief 131)
designs/b96_kr260_10g/dbg_xvc/docs/xvc_board_test.md 1c31caf208: the pre-registered board test for build dbg_xvc: criteria written before any board time (brief 131)
designs/b96_kr260_10g/dbg_xvc/board/pl-dbg-xvc.dtsi 6b0dd3f24b: device-tree overlay fragment for the debug bridge on the KR260; not loaded on a board (brief 131)
designs/b96_kr260_10g/dbg_xvc/board/xvc_board_session.sh bb8534601a: the board-session script for the dbg_xvc test, given by the planner at the board; not run (brief 131)
designs/b96_kr260_10g/dbg_xvc/board/xvc_capture.tcl c43a40ce6f: Vivado hardware-manager side of the dbg_xvc board test: XVC connection and ILA captures; not run (brief 131)
designs/b96_kr260_10g/dbg_xvc/model/xvc_verdict.py 6e5f94a169: the pre-registered verdict of the dbg_xvc board test (brief 131)
designs/b96_kr260_10g/dbg_xvc/scripts/dump_netlist_timing.tcl d2746b1b03: dumps a routed build's core cells and slacks so the debug build can be compared with its parent (brief 131)
designs/b96_kr260_10g/verif/pyuvm/README.md 0b5695e70d: how the pyuvm (Python UVM on cocotb and Icarus) bench for the PCS and MAC is built, run and limited; the same job as the SystemVerilog UVM bench (brief 123)
designs/b96_kr260_10g/verif/pyuvm/COMPARISON.md 0f9578afff: the measured comparison of the pyuvm and the SystemVerilog UVM bench, where each fits the project, and a section for the verification course (brief 123)
designs/b96_kr260_10g/verif/uvm/README.md 28bc0ecbd5: how the UVM 1.2 bench for the PCS and MAC is built, what each part checks, the coverage and the seeded bugs (brief 112)
designs/b96_kr260_10g/rm_gp_bypass/rtl/b96_core.sv 82d6c44238: copy of rtl/b96_core.sv for build rm_gp_bypass with the GT buffer-bypass controllers connected, run gates and (brief 96F1b) the alignment timeout and retry status in GT_BUF
designs/b96_kr260_10g/rm_gp_bypass/rtl/gt_bp_ctl.sv 71963d3f2f: per-direction reset synchroniser, 30 ms TX / 130 ms RX alignment timeout with bounded retry and gave-up flag for the bypass controller (brief 96F1b)
designs/b96_kr260_10g/rm_gp_bypass/rtl/gt_bp_gate.sv 5e384b6757: per-direction gate that releases the paths only after the bypass controller has restarted and finished (brief 96F1)
designs/b96_kr260_10g/ip/amd_ip_bypass.tcl 2b44c98771: the GT Wizard configuration with both buffers bypassed (brief 96F1)
designs/b96_kr260_10g/host/b96f1_bypass.py 8e94dd345a: board driver and pre-registered verdict for build rm_gp_bypass (brief 96F1)
designs/b96_kr260_10g/lat_all3_bypass/build.yaml bbb4d85334: build lat_all3_bypass, the default receive path with the 97C latency cuts and both GT elastic buffers bypassed; points at the parent builds' files, no copy (brief 126)
designs/b96_kr260_10g/host/b126_all3_bypass.py 6fef448fa4: board driver and pre-registered verdict for build lat_all3_bypass (brief 126)
designs/b96_kr260_10g/rm_gp_ml/rtl/ml_stage.sv 1c1abfce18: the ML decision stage of build rm_gp_ml: one-instrument book, order-flow features, classifier pipeline and counters (brief 113)
designs/b96_kr260_10g/rm_gp_ml/rtl/ml_pkg.sv 71363adf14: constants shared by the ML stage (brief 113)
designs/b96_kr260_10g/rm_gp_ml/rtl/trade64.sv 3e80ab02a4: copy of rtl/trade64.sv for build rm_gp_ml with the model's veto on the rule's decision (brief 113)
designs/b96_kr260_10g/rm_gp_ml/rtl/rx_path.sv da1472f5fa: copy of rtl/rx_path.sv for build rm_gp_ml with the ML stage's ports through to trade64 (brief 113)
designs/b96_kr260_10g/rm_gp_ml/rtl/rx_path_legacy.sv cc5cf55776: copy of rtl/rx_path_legacy.sv for build rm_gp_ml with the ML ports tied off (brief 113)
designs/b96_kr260_10g/rm_gp_ml/rtl/b96_core.sv 46ceb4153e: copy of rtl/b96_core.sv for build rm_gp_ml with the ML registers, crossings and status words (brief 113)
designs/b96_kr260_10g/rm_gp_ml/build.yaml a081d3c86e: how flow/run_vivado.sh builds rm_gp_ml (rm_gp with the ML stage, brief 113)
designs/b96_kr260_10g/rm_gp_ml/docs/ml_stage.md beb51c0a3c: which model block was chosen and why, how the stage is arranged, the measured cost in context (brief 113)
designs/b96_kr260_10g/rm_gp_ml/docs/ml_registers.md 487b9de7fe: register map of the ML stage, generated from rm_gp_ml/regmap_ml.py (brief 113)
designs/b96_kr260_10g/rm_gp_ml/model/twin.py ec29cc5d38: Python twin of the ML stage over the brief 87 references (brief 113)
designs/b96_kr260_10g/rm_gp_ml/model/stream.py 7047fabb32: synthetic Bench Feed v1 streams as 10GBASE-R words, with the twin's expectation per frame (brief 113)
designs/b96_kr260_10g/rm_gp_ml/sim/tb_ml_core.sv bcc7b0ea4d: whole-core xsim bench with a synthetic feed injected on the receive words (brief 113)
designs/b96_kr260_10g/host/b113_ml.py 167efbfa06: board driver and pre-registered verdict for build rm_gp_ml (brief 113)
designs/b96_kr260_10g/rtl/es_ctrl.sv 671362a1c0: DRP master and eye-scan point sequencer for the GTHE4 channel (EYESCAN = 1), brief 96D
designs/b96_kr260_10g/es.xdc 9f571dada7: powers up the GT's eye-scan circuit (ES_EYE_SCAN_EN, ES_ERRDET_EN) in the eyescan build
designs/b96_kr260_10g/model/eyescan.py a4f8ffb4ab: Python twin of the eye-scan point sequencer's DRP traffic
designs/b96_kr260_10g/tests/eyescan_cocotb.py b6da9be062: cocotb bench of the sequencer against the twin and a DRP stand-in
designs/b96_kr260_10g/rtl/b96_pkg.sv ac2ee00c42: block codes, scrambler, CRC-32 functions
designs/b96_kr260_10g/rtl/pcs_tx.sv e0e68141d9: transmit PCS (encode, scramble, gearbox)
designs/b96_kr260_10g/rtl/pcs_rx.sv 161c35209b: receive PCS (gearbox with slip, block lock, descramble, decode)
designs/b96_kr260_10g/rtl/mac64_tx.sv 0cbc07b026: 64-bit MAC transmitter
designs/b96_kr260_10g/rtl/mac64_rx.sv 35a0ed74f5: 64-bit MAC receiver
designs/b96_kr260_10g/rtl/frame_src.sv a745598f6a: frame builder for orders, feed, probe and test frames
designs/b96_kr260_10g/rtl/trade64.sv 1999e01a37: the 64-bit mock trading decision
designs/b96_kr260_10g/rtl/tx_path.sv 91039813b5: transmit domain: sources, generator, timestamps
designs/b96_kr260_10g/rtl/rx_path.sv 926b9f9901: receive domain: PCS, MAC, decision, counters
designs/b96_kr260_10g/rtl/b96_core.sv bc8ac81d24: registers, GT wrapper and clock-domain crossings
designs/b96_kr260_10g/rtl/kr260_10g_top.sv 3d4ca01e5a: board top (MMCM, SYSMON, pins)
designs/b96_kr260_10g/rtl/rx_path_legacy.sv 4c9412a3ce: the 97C receive path (main 6909e43f), used when RATE_MATCH = 0
designs/b96_kr260_10g/rtl/rate_match.sv f16fa46d1d: rate-matching elastic buffer (idle insert and delete between frames, xpm_fifo_async), brief 96C
designs/b96_kr260_10g/rtl/rate_match_gp.sv 09ba730191: low-latency elastic buffer with our own gray-pointer crossing (RM_OWN = 1), brief 96E
designs/b96_kr260_10g/rate_match_gp.xdc 68705f884b: set_max_delay -datapath_only for the direct-read variant of rate_match_gp (build rm_gp_direct only)
designs/b96_kr260_10g/model/ratematch.py 8794519d31: Python twin of the rate matcher, compared output for output with the RTL
designs/b96_kr260_10g/host/b96c_ppm.py a5a5b3d64e: board driver for the ppm sweep (TX phase-interpolator offset, measured ppm, SYSMON conditions)
designs/b96_kr260_10g/rtl/hs_vec.sv e0fc43a9b5: coherent vector crossing
designs/b96_kr260_10g/model/pcs.py 92790d45d7: bit-serial Python reference of the PCS (the twin)
designs/b96_kr260_10g/design.xdc 4dec8c5ba8: pins, clocks, slow-pin constraints
designs/b96_kr260_10g/docs/design.md 7007e677f1: design note: decisions and alternatives
designs/b96_kr260_10g/docs/board_run_plan.md 678413f0be: stage 3 plan for the board
designs/b96_kr260_10g/docs/what_we_found.md 376623bbd5: results and gaps
designs/b96_kr260_10g/docs/loop_timing_feasibility.md 500557ea56: loop-timing and buffer-bypass feasibility study (96F)
designs/b96_kr260_10g/docs/loop_timing_board_test_plan.md 9740d509f2: board test plan for loop timing (96F, for approval)
designs/b96_kr260_10g/docs/loop_timing_sources.md c53e4dbe34: AMD sources read for loop timing (XAPP1276, Wizard example, TXPI, QPLL outside the core; 96F2)
docs/latency_definitions.md 7323927a60: our latencies against STAC-T0 and wire-to-wire definitions (109)
designs/b96_kr260_10g/model/loop_timing.py a2d1bf6428: Python model of the loop-timing frequency tracker (96F)
designs/b96_kr260_10g/regmap.py 020260c536: register map as data
designs/b96_kr260_10g/docs/register_map.md d2846103ad: interface datasheet
designs/b96_kr260_10g/rm_gp_itch/rtl/udp_strip.sv 18ecd60fab: adapter from mac64_rx to the Mold receiver (build rm_gp_itch, brief 127): header checks, strip with a 2-byte realign, FCS verdict as a late strobe, capture ring
designs/b96_kr260_10g/rm_gp_itch/rtl/itch_top.sv aaf47540c5: brief 110's mold_rx, itch_dec, book_core, risk_glue (unchanged) with the late verdict and the segment builder (brief 127)
designs/b96_kr260_10g/rm_gp_itch/rtl/order_seg.sv 473fe555c6: the order frame as a 113-byte Ethernet/IPv4/TCP stream, the stand-in for brief 119's tcp_fast (brief 127)
designs/b96_kr260_10g/rm_gp_itch/rtl/order_seg_tcpfast.sv 30fc090de0: the same module with tcp_fast in place of the stand-in: the hook, not in the build (brief 127)
designs/b96_kr260_10g/rm_gp_itch/rtl/tx_mux.sv 60060254bf: transmit multiplexer in front of mac64_tx: frame source, replay memory, order stream with FIFO and head register (brief 127)
designs/b96_kr260_10g/rm_gp_itch/rtl/itch_path.sv 3f8c04b0c0: core-clock wrapper of the ITCH path: host vectors, order poison policy, counters, latency statistics (brief 127)
designs/b96_kr260_10g/rm_gp_itch/rtl/b96_core.sv 2ee04f6ca6: copy of rtl/b96_core.sv for build rm_gp_itch: RATE_MATCH = 1 only, the ITCH path and its registers 0x300 to 0x57C (brief 127)
designs/b96_kr260_10g/rm_gp_itch/regmap_itch.py 607630b5da: register map of build rm_gp_itch as data, generates its datasheet (brief 127)
designs/b96_kr260_10g/rm_gp_itch/docs/itch_integration.md dc4f9f826c: the ITCH/OUCH path inside the 10G design: path, latency, the late frame check, registers, hook for tcp_fast, results (brief 127)
designs/b96_kr260_10g/rm_gp_itch/docs/board_test_plan.md 2801a79865: pre-registered board test of build rm_gp_itch (brief 127), not run
designs/b96_kr260_10g/rm_gp_itch/host/itch_host.py 61c12a6515: synthetic MoldUDP64/ITCH frames, replay image, expected order frame and the order check (brief 127)
designs/b96_kr260_10g/rm_gp_itch/host/b127_stages.py 9033fe838b: the pre-registered board stages, shared with the simulation's dry run (brief 127)

## commands
simulate the PCS, MAC and core against the Python reference (~2min): python -m pytest -q designs/b96_kr260_10g/tests
[heavy] build variant (b) and run all gates (~22min): flow/run_vivado.sh designs/b96_kr260_10g base
[heavy] build variant (a), the near-end loopback self-test (~22min): flow/run_vivado.sh designs/b96_kr260_10g/selftest base
the UVM 1.2 regression of the PCS and MAC in xsim (every test over its seeds, coverage merge, seeded bugs) (~40min): designs/b96_kr260_10g/verif/uvm/scripts/run_regress.sh --mutants --record results/112_uvm_pcs_mac
the pyuvm regression of the PCS and MAC in Icarus (every test over its seeds, coverage merge, seeded bugs); needs pyuvm 5.0.0 and cocotb-coverage in a venv that sees cocotb 2.0.1 (~15min): PYTHONPATH=. python designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --mutants --record results/123_pyuvm_pcs_mac

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py b26b6317ae
R2 results/b96c/builds/control/digest.json f4c148e6e1
R3 results/b96c/eqy_default/result_default.txt 0144f4bfb6
R4 results/b96c/hw/20261119_080724/control/stage3.json 269183b66c
R5 results/b96/build_a/gates.json fe45f7625c
R6 results/b96/README.md 3fb82e2bc0
R7 results/b96e/core_lat_sim.json 77fb782b78
R8 results/b96e/builds/rm_gp/digest.json fdc4edc093
R9 results/b96f1/builds/rm_gp_bypass/digest.json f49d9a7e1a
R10 results/b96f1/bypass_seq/result.txt 457378d737
R11 results/b96f1b/builds/rm_gp_bypass/digest.json e4681b81a1
R12 results/b96f1b/bypass_ctl/result.txt 6d13cfb7e4
R13 results/b126/builds/lat_all3_bypass/digest.json b0b2ce349a
R14 results/b126/core_sim/all3_bypass.json 0f8de19801
R15 designs/b96_kr260_10g/rm_gp_itch/tests/test_b127_unit_rtl.py 973c292a1f
R16 results/b127/core_sim.json 868de45ea1
R17 results/b127/builds/rm_gp_itch/digest.json 547ee036d5
R18 results/b96c/builds/control/run.json 699ba4c7ee
R19 results/b96/latency_sim.json e5453d4c0b
R20 results/b96c/core_sim.json 227e0284e2
R21 results/b96c/core_sim_default.json 21559dbac7
R22 results/b96c/builds/rm_all3/digest.json 53fa66d4a7

## evidence
E1 simulation pass R1 ci: PCS and MAC against an independent bit-serial Python model clock for clock; frames in lane 0 and lane 4, every length residue, any bit offset; the whole core with a stand-in for the GT: probe echo, trading loop, decisions, poisoned orders
E2 build pass R2: variant (b), the default build (RATE_MATCH = 0, the 97C receive path; rebuilt for brief 96C addendum 2), synthesis, implementation and bitstream on the Basic tier; every flow gate and every GT gate passes (29 of 29)
E5 formal pass R3: the RATE_MATCH = 0 core is equivalent to main 6909e43f's core (eqy, slang front end, OSS CAD Suite; XPM crossings as wires, GT a black box, the 96C-only registers cut from the proof copy: see results/b96c/eqy_default/README.md); a planted change in the MAC error counter fails it
E6 board pass R4: the rate-matched builds (RATE_MATCH = 1, from f47986f4) on a KR260 optical loopback: safety accepted on all four variants (100 of 100 restarts locked, 500 of 500 orders sent = fired = order_ok per variant, every fault counter 0, SYSMON inside the DS925 windows); the TX phase-interpolator route gave no relative offset (0.0 ppm at every code; non-zero targets recorded unreachable), so rate matching under a real offset is not shown on hardware; the buffer costs 11 clocks of loop latency | cond: KR260, SFP+ optical loopback, Vivado 2026.1 bitstreams of 2026-11-19, 100 restarts a variant, 20 s dwell at 0 ppm
E4 build pass R5: variant (a), the near-end loopback self-test, built before brief 96C and not rebuilt with the rate matcher: synthesis, implementation and bitstream; every flow gate and every GT gate passes
E3 review pass R6: one independent correctness review (Sonnet) and one fix round
E7 simulation pass R7: whole core in xsim with AMD's real XPM macros, four clock phases: tick-to-trade of the 97C path, of the xpm_fifo_async buffer and of the own gray-pointer buffer (RM_OWN = 1); the numbers and the accounting of the board's loop-latency increase are in design.md section 11
E8 build pass R8: build rm_gp (RATE_MATCH = 1, RM_OWN = 1), all 29 gates, WNS +0.105 ns, WHS +0.011 ns, stamp 1a2fa1a8 recomputed from the tree; not loaded on a board
E9 build pass R9: build rm_gp_bypass (both GT buffers bypassed, brief 96F1), all 29 gates, WNS +0.090 ns, WHS +0.010 ns, report_cdc no critical, stamp b2a7aeea; not loaded on a board
E10 simulation pass R10: the Wizard's own buffer-bypass controllers with our run gate against a stand-in transceiver in xsim, 28 checks (start on the reset-done edge, stale done held off, error holds the paths in reset)
E11 build pass R11: build rm_gp_bypass rebuilt with the reset synchroniser and the alignment timeout and retry (brief 96F1b), all 29 gates, WNS +0.118 ns, WHS +0.010 ns, report_cdc no critical and no waivers, stamp 86037ce1; not loaded on a board; supersedes E9
E12 simulation pass R12: gt_bp_ctl with the Wizard's own controllers against a stand-in transceiver in xsim (reset assert and release, normal start, retries, give-up, error not retried, clock inactive), plus the 28 checks of E10 unchanged; the whole core in three scenarios; the real 30 ms and 130 ms values
E13 build pass R13: build lat_all3_bypass (default receive path, 97C's three latency cuts, both GT buffers bypassed; brief 126), all 29 gates, WNS +0.066 ns, WHS +0.010 ns, report_cdc no critical, methodology no critical, stamp 9641284d; not loaded on a board
E14 simulation pass R14: the whole core of lat_all3_bypass in xsim with AMD's real XPM macros at four clock phases, with a stand-in transceiver with the bypass controllers' ports and the safety counters read back; 8 of 8 orders, every safety counter 0, the same digital tick-to-trade as lat_all3 within 0.1 clock; one retry recovers a hung alignment, a never-aligned link sends nothing
E15 simulation pass R15 ci: the new blocks of build rm_gp_itch with the real mac64_rx and mac64_tx against brief 110's model: four seeded sessions with speculation off and on, every counter, every book update, the final top of book and every order frame byte for byte; the adapter's frame lengths and alignments with bubbles and bad FCS; the poison of an order on a bad frame, the FCS window sweep, the replay and the capture ring on a closed loop, orders dropped when the MAC is busy, back-to-back orders
E16 simulation pass R16: the whole core of build rm_gp_itch in xsim 2026.1 with AMD's real XPM macros and the GT stand-in, four phases between the clocks: 16 orders a phase from replayed frames round a closed loop, every counter equal to the model's, tick-to-trade GT port to GT port recorded; the board test's five stages run against it as a dry run | cond: xsim 2026.1, GT stand-in, phases 0, 1550, 3100, 4650 ps
E17 build pass R17: build rm_gp_itch through the flow on Vivado 2026.1 (every flow gate; report_cdc no critical, no new waiver)

## measured
M1 resources lut=6167 LUT R2#utilization.lut: LUTs, variant (b) | routed, Vivado 2026.1
M2 resources ff=14,183 FF R2#utilization.ff: registers, variant (b) | as M1
M3 timing wns_ns=0.221 ns R2#timing.wns_ns: worst setup slack, variant (b) | routed, user clocks 161.133 MHz and 100 MHz
M4 timing whs_ns=0.011 ns R2#timing.whs_ns: worst hold slack, variant (b) | as M3
M5 power power_w=1.087 W R2#power.total_w: total on-chip power estimate, variant (b) | report_power after routing, vectorless, confidence Medium
M6 other -=4439 MiB R18#vivado_peak_rss_mib: Vivado peak resident memory of the variant (b) build | 1 thread, MemoryMax=6G scope, one run, no cap hits
M7 latency -=3 clocks R19#tx_clocks_max: transmit latency, worst gearbox phase | simulation, 161.13 MHz clock, MAC output register to the GT word with the last bit of the start block
M8 latency -=13 clocks R20#tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks.max: digital tick-to-trade, worst simulated case with the rate matcher (RATE_MATCH = 1) | simulation, same-phase clocks, the Icarus stand-in of the FIFO macro; GT, optics and clock-crossing phase not included; the board measured 11 clocks more than 97C, see E6 and design.md section 9
M10 latency tick_to_trade_default_clocks=11 clocks R21#tick_to_trade_digital_sim.gt_rxdata_price_word_to_gt_txdata_order_start_clocks: digital tick-to-trade, simulation of the default build (RATE_MATCH = 0, the 97C path) | simulation, same-phase clocks; as M8
M9 timing wns_ns_all3=0.004 ns R22#timing.wns_ns: worst setup slack, latency variant all3 with the rate matcher (RATE_MATCH = 1) | as M3; the margin is thin
M11 latency tick_to_trade_own_buffer_clocks=13 clocks R7#results.rate_match_1_rm_own_1.1550.tick_to_trade.mean: GT-port tick-to-trade in simulation with AMD's real macros, own gray-pointer buffer (RM_OWN = 1), mean over four phases at phase 1550 ps | xsim 2026.1, whole core, GT stand-in, phase 1550 ps between the clocks; the 97C path is 10.75 and the xpm_fifo_async buffer 16.0 at the same phase; the board has not measured this build
M12 timing wns_ns_all3_bypass=0.066 ns R13#timing.wns_ns: worst setup slack, build lat_all3_bypass (the 97C cuts with both GT buffers bypassed) | as M3
M13 latency tick_to_trade_all3_bypass_clocks=7.6 clocks R14#means_over_phases_clocks.rate_match_0_rm_own_0.tick_to_trade: GT-port tick-to-trade in simulation, build lat_all3_bypass, mean over four phases (the same as lat_all3 within 0.1 clock, because the stand-in has no GT buffers and the bypass's saving is not simulated) | xsim 2026.1, whole core, GT stand-in with the bypass controllers' ports, four phases between the clocks
M14 resources lut_itch=17,258 LUT R17#utilization.lut: LUTs, build rm_gp_itch | routed, Vivado 2026.1
M15 resources ff_itch=46,116 FF R17#utilization.ff: registers, build rm_gp_itch | as M14
M16 timing wns_ns_itch=0.153 ns R17#timing.wns_ns: worst setup slack, build rm_gp_itch | routed, user clocks 161.133 MHz and 100 MHz
M17 timing whs_ns_itch=0.01 ns R17#timing.whs_ns: worst hold slack, build rm_gp_itch | as M16
M18 power power_itch_w=1.253 W R17#power.total_w: total on-chip power estimate, build rm_gp_itch | report_power after routing, vectorless
M19 latency itch_t2t_spec_clocks=16.78 clocks R16#itch_to_order.speculative.tick_to_trade_gt_clocks.mean: ITCH tick-to-trade, GT port to GT port, speculative start, mean over four phases | xsim 2026.1, whole core, GT stand-in; from the last byte of the message at the receive PCS output to the order's start block on the transmit GT port
M20 latency itch_t2t_verdict_clocks=21.63 clocks R16#itch_to_order.at_verdict.tick_to_trade_gt_clocks.mean: ITCH tick-to-trade, GT port to GT port, order started at the risk verdict, mean over four phases | as M19

## gaps
[hardware] The design has run on a KR260 optical loopback only (briefs 97 and 96C), never against a network card or a second reference clock, so rate matching (RATE_MATCH = 1) has not been seen under a real frequency offset; the TX phase-interpolator route gave none. The reference clock source and frequency, the 25 MHz input and the SFP+ control pin functions are unconfirmed against the schematic (third-party example).
[interoperability] The PCS and MAC are checked against a model written by the same author and against zlib and a recurrence; the standard text was not available, so only a network card proves the block formats and scrambler order.
[simulation] The transceiver is a behavioural stand-in because the free simulator refuses the real model; the whole-core bench uses same-phase clocks, so the receive-to-transmit crossing phase is not simulated.
[trading path] trade64 is a one-rule 64-bit stand-in, not the 58A core; orders that overlap are dropped; no cancel after send; the order fields cross as a quasi-static bus (CDC-6 warning).
[protocol] No link-fault state machine, BER monitor, ARP or ICMP responder; ordered sets are counted and shown as idles; receive does not check preamble, runts or jumbo frames; the transmit MAC does not pad.
[throughput] The line rate and the 10 Gb/s payload rate are by configuration and by the gearbox arithmetic; no throughput or error-rate measurement exists because nothing ran on a board.
[build] The 96C builds of the latency variant with the buffer (rm_all3) and its ppm twin hit the 6 GiB scope cap about 1000 times and used about 700 MiB of swap (the base build did not); the Vivado resident peak of the base build is 4439 MiB. all3 closes timing with 0.004 ns of setup slack, which is thin.
[constraints] The per-entry data path to the first synchroniser flop (write-clock entry flop to the first `xpm_cdc_array_single` flop) has no max-delay bound: the one-clock margin of `ENT_SYNC = 1` covers normal routing, but it is not constrained.
[ml stage] Build rm_gp_ml (the ML decision stage behind the rule, brief 113) has not run on a board; its board test is pre-registered in results/b113/preregistration.md and the owner's script is written. The stage tracks one instrument with a top-of-book and sees the first message of a frame only; the model is brief 87's trees on one planted-signal data set.
[itch path] Build rm_gp_itch has not run on a board (the test is pre-registered, the script written); its order frame is a stand-in for brief 119's TCP fast path with the TCP checksum 0, so no real TCP stack would accept it; the loopback tests only our own frames; a bad frame's order can leave before the frame's check is known when its trigger message is far from the packet's end (rm_gp_itch/docs/itch_integration.md section 4).

## next_actions
1. Run _handoff/fpga_agent/run_96f1_stage1.sh on the KR260 (pre-registered in results/b96f1/preregistration.md, amendment 2026-11-20), build rm_gp_bypass (stamp 86037ce1, brief 96F1b) against the 96E rm_gp board run; read the retry counts and gave-up flags.
2. Run docs/board_run_plan.md steps 1 to 4 on the KR260 (laser polarity first), then the NIC steps after the owner buys a card and cable.
3. Confirm the reference clock and the control pins against the carrier schematic.
4. Widen the 58A core to 64 bits, or add the missing 58A features to trade64.
5. Run _handoff/fpga_agent/run_127_stage1.sh on the KR260 (pre-registered in results/b127/preregistration.md), build rm_gp_itch.
6. Merge brief 119's PR #245 and swap order_seg.sv for order_seg_tcpfast.sv (rm_gp_itch/docs/itch_integration.md section 8).

## open_questions
- Does the PL load over JTAG with the PS idle on the KR260 (flow/program.py has no KR260 board entry yet)?

## history
2026-11-21 - pr=-: brief 127: build rm_gp_itch, brief 110's MoldUDP64/ITCH/book/risk/OUCH path inside the 10G design (udp_strip adapter with a late FCS verdict, transmit multiplexer, replay memory and capture ring, stand-in for tcp_fast with a hook); bit-exact against 110's model in xsim and Icarus; built with timing met; board test pre-registered and script written, nothing run on a board
2026-11-21 - pr=-: brief 126: build lat_all3_bypass (the default receive path, the 97C latency cuts and the GT buffer bypass together), all 29 gates, WNS +0.066 ns, report_cdc no critical; simulated in xsim; board test pre-registered from the two measured runs (E 16.0, L 38.0, D 6.0, tick-to-trade 22 clocks) and script written; nothing run on a board
2026-11-20 - pr=-: brief 96F1b: build rm_gp_bypass with AMD-style synchronised controller reset and a 30 ms TX / 130 ms RX alignment timeout with 3 retries then a gave-up flag (GT_BUF bits 29:16); all 29 gates, timing met, report_cdc no critical; gave-up added as a fail line before any board time; nothing run on a board
2026-11-20 - pr=-: brief 123: pyuvm bench for the PCS and MAC (designs/b96_kr260_10g/verif/pyuvm) with the same tests, bugs and coverage bins as brief 112, run in Icarus; same verification result, measured comparison and recommendation in COMPARISON.md; no RTL change
2026-11-20 - pr=-: brief 112: UVM 1.2 bench for the PCS and MAC (designs/b96_kr260_10g/verif/uvm): agents, reference models, scoreboard, coverage, SVAs, regression and seeded bugs, in xsim 2026.1; no RTL bug found; xcrg refused on the Basic tier
2026-11-20 - pr=-: brief 96F1: build rm_gp_bypass (both GT elastic buffers bypassed; Wizard probe in results/b96f1/wizard_probe), all 29 gates, timing met, report_cdc no critical; board test pre-registered and script written, nothing run on a board
2026-11-19 - pr=-: brief 96E: own gray-pointer elastic buffer (RM_OWN), +1.2 clocks of tick-to-trade over 97C in xsim against +5.3 for the macro buffer; the board's +11 accounted (1.25 left in D); build rm_gp with all 29 gates; board run and real-offset plan pending the owner
2026-11-19 - pr=-: brief 96D: on-chip RX eye scan (EYESCAN build option, es_ctrl, flow/eyescan); built with all 29 gates; simulated against a stand-in; not yet run on the board
2026-11-19 - pr=-: brief 96C addendum 2: RATE_MATCH build parameter, default 0 (the 97C path, shown equivalent by eqy and the 97C bench); the board measured the buffer at +11 clocks and no relative offset by the TX phase interpolator
2026-11-19 - pr=-: brief 96C: elastic-buffer rate matcher (xpm_fifo_async) in the base design and lat_all3, TX phase-interpolator ppm controls, four builds with all 29 gates, board session pending
2026-11-17 - pr=-: brief 96 stages 0 to 2: board facts, design note, PCS, MAC, trading path, host code, builds; one review round
