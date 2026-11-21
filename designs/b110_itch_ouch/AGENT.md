# AGENT b110_itch_ouch (fda-handover/1)
source: designs/b110_itch_ouch/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b110_itch_ouch

## identity
kind=showcase produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 (K26 SOM) top=itch_ouch_top (wrapped with input registers in ooc_wrap for the out-of-context build) tool=Vivado 2026.1
verified: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement (record: designs/b110_itch_ouch/VERIFIED.md, designs/b110_itch_ouch/verified.json; definition: docs/verified.md)

## summary
A trading path in the formats a real venue speaks, in simulation. UDP payload words carrying MoldUDP64 and Nasdaq TotalView-ITCH 5.0 are decoded, a small top-of-book is kept for a few instruments, a pre-trade risk check with a kill switch decides, and an OUCH 5.0 Enter Order is built in a SoupBinTCP 3.00 packet and handed to a stub port, optionally started before the risk verdict and cancelled if it fails. A Python reference model and a seeded synthetic generator check the RTL bit for bit, seeded faults in the RTL are all caught, and the block is built out of context for the KR260's part at the 10G core clock.
not: real market data or a real exchange; every message comes from our own seeded generator and no order is ever sent anywhere; TCP, SoupBinTCP login, heartbeats or order responses; the frame goes to a stub port (docs/tcp_plan.md is a plan); Ethernet, IP or UDP handling and the FCS check; the path starts at the UDP payload (docs/phase2_integration.md is a plan); a full-depth book or every instrument; a few instruments with a bounded number of price levels, and a stated way to fail; a board run, power, or timing inside the 10G core; the numbers are simulation and an out-of-context Vivado 2026.1 build

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=None
gates: rtl_equals_model=pass lint=pass seeded_faults=pass ooc_build_2026_1=pass board_run=not-run

## interface
clk clk 161.132MHz
rst rst active-high: synchronous; resets every register including the counters and starts the table sweep; one clock domain, no asynchronous input
if payload input s_v, s_d[63:0], s_sof, s_eof, s_keep[7:0], s_err (UDP payload words): byte 0 in bits 7:0; keep is low-contiguous on the last word; the messages of a packet are delivered before its frame check is known doc=designs/b110_itch_ouch/docs/itch_ouch.md
if order frame output o_v, o_d[63:0], o_sof, o_eof, o_keep[7:0], o_abort (stub port): eight words, never paused; o_abort cancels the frame in flight (speculative start only) doc=designs/b110_itch_ouch/docs/itch_ouch.md
if configuration and clears cfg_* static inputs and one-clock clr_* pulses: configuration is static while traffic runs; clr_book starts a table sweep during which events are dropped and counted doc=designs/b110_itch_ouch/docs/itch_ouch.md
if observation flags, cnt (45 counters of 32 bits), tu_* top-of-book update record, tob_* registers: counters wrap, never saturate; every counter is defined in the datasheet doc=designs/b110_itch_ouch/docs/itch_ouch.md
param N_INST=4 legal=2 to 8
param LEVELS=8 legal=4 or 8
param ORD_AW=8 legal=4 to 16 (tested at 5, 6, 8 and 10)

## files
designs/b110_itch_ouch/rtl/mold_rx.sv 2439cc5a50: MoldUDP64 receiver
designs/b110_itch_ouch/rtl/itch_dec.sv 43c7f717f1: ITCH 5.0 decoder
designs/b110_itch_ouch/rtl/book_core.sv 4f9ea037d5: order table, ladders, top of book
designs/b110_itch_ouch/rtl/risk_glue.sv 2cde343aec: decision, risk checks, kill switch, order queue
designs/b110_itch_ouch/rtl/ouch_enter.sv 95066c0f3c: OUCH 5.0 Enter Order in SoupBinTCP framing
designs/b110_itch_ouch/rtl/itch_ouch_top.sv 6f9da05065: top level
designs/b110_itch_ouch/model/proto.py ae43fca45e: packers for the four protocols, from the specifications
designs/b110_itch_ouch/model/ref.py 92ebceb812: reference model (untimed, exact)
designs/b110_itch_ouch/model/gen.py 7a5ed6f04b: seeded synthetic ITCH over MoldUDP64 generator
designs/b110_itch_ouch/tests/b110_cocotb.py e8b7915b02: cocotb bench
designs/b110_itch_ouch/tests/run_mutants.py d7d017acd5: seeded-fault runner
designs/b110_itch_ouch/ooc/ooc.py 13550cc38a: out-of-context build driver
designs/b110_itch_ouch/docs/itch_ouch.md 21f329f7ca: datasheet
designs/b110_itch_ouch/docs/spec_notes.md 5ce86ae4a2: field layouts and where each comes from
designs/b110_itch_ouch/docs/tcp_plan.md 95463d9cfc: TCP options and the phase 2 recommendation
designs/b110_itch_ouch/docs/phase2_integration.md a15fee8877: integration plan for the KR260 design, the host bench and the board test

## commands
the whole bench (cocotb on Icarus), the model tests and the lint (~2min): python3 -m pytest -q designs/b110_itch_ouch/tests/test_b110_model.py designs/b110_itch_ouch/tests/test_b110_rtl.py designs/b110_itch_ouch/tests/test_b110_lint.py
the same with the measurement records written (latency, throughput, coverage, idle gap) (~1min): B110_RECORD=$PWD/results/b110 python3 -m pytest -q designs/b110_itch_ouch/tests/test_b110_rtl.py::test_all_benches
the seeded faults (every mutant of verif/mutants.yaml against the bench) (~25min): python3 designs/b110_itch_ouch/tests/run_mutants.py --jobs 2 --json results/b110/mutation.json
[heavy] the out-of-context builds (three clocks) (~30min): python3 -m designs.b110_itch_ouch.ooc.ooc --clocks 6.2061 5.0 4.4

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b110_itch_ouch/tests/test_b110_rtl.py ed9179dc6e
R2 designs/b110_itch_ouch/tests/test_b110_model.py 0ac06f1af3
R3 designs/b110_itch_ouch/tests/test_b110_lint.py 3028d8b5b4
R4 results/b110/mutation.json 2c13eb56b0
R5 results/b110/coverage_sim.json 69836756e5
R6 results/b110/ooc/itch_ouch_top.json 4d84f7e2e8
R7 results/b110/latency_sim.json c181bd7465
R8 results/b110/throughput_sim.json a4e3cf74c3
R9 results/b96c/core_sim_default.json 21559dbac7

## evidence
E1 simulation pass R1 ci: the whole path against the Python reference over seeded sessions, hand-built corner cases, impairments, a stress run and other parameters - events, every top-of-book update, every order frame bit for bit, every counter and flag
E2 model pass R2 ci: the packers against the field tables of the specifications and the reference model against hand-computed behaviour of the protocol layer, the book and the risk checks
E3 lint pass R3 ci: Verilator -Wall clean at the default parameters and at three others
E4 faults pass R4: every one of the seeded faults in the RTL (operators, constants and conditions across the five blocks) fails the bench
E5 simulation pass R5: coverage over the bench - every message type decoded, every byte offset where a message starts and ends in a word, every last-word keep mask, every counter
E6 build pass R6: out-of-context, post-route builds on the K26 at the required 10G core clock and two faster ones; the required clock closed (setup, hold and pulse width)

## measured
M1 latency book_update_clocks=7 clocks R7#non_speculative.book_update_add: clocks from the last byte of a message to its top-of-book update (Add Order) | simulation, one clock
M2 latency order_first_word_clocks=8 clocks R7#non_speculative.first_order_word: clocks from the last byte of the triggering message to the first word of the order frame, frame started at the risk verdict | ditto
M3 latency order_first_word_spec_clocks=3 clocks R7#speculative.first_order_word: the same with the frame started speculatively, before the verdict | simulation, one clock; only when the frame is idle and no earlier candidate is in flight
M4 latency decision_to_first_word_clocks=1 clocks R7#non_speculative.decision_to_first_order_word: the order frame's first word after the decision (the verdict, or the candidate when speculative) is known | simulation, one clock; the same figure the 96 design has from its decision register to its order logic
M5 throughput clocks_per_message=3.838 clocks R8#clocks_per_message: clocks per message with payloads back to back and no idle clock, mixed Add, Delete and Replace; nothing dropped | simulation; one 64-bit word a clock is accepted, so the figure is the input's own rate for these message sizes
M6 resources lut=6621 LUT R6#at_required.core_lut: LUTs of itch_ouch_top at the required clock (including the LUTs used as memory) | out of context, Vivado 2026.1, one thread, default parameters; the wrapper's input registers are not counted
M7 resources ff=5223 FF R6#at_required.core_ff: registers of itch_ouch_top at the required clock | as M6
M8 timing wns_ns=0.109 ns R6#at_required.wns_ns: worst setup slack at the required clock | out of context, post-route, period 6.2061 ns, no clock buffer or jitter
M9 timing whs_ns=0.055 ns R6#at_required.whs_ns: worst hold slack at the required clock | as M8
M10 timing closed_at_ns=5 ns R6#closed_at_ns: fastest clock period tried that closed | a closed point out of the three tried, not a bound; as M8
M11 other mutants_killed=58 faults R4#killed: seeded faults killed by the bench | simulation, the whole bench per fault
M12 other mutants_valid=58 faults R4#valid: seeded faults that build and were tried | as M11
M13 resources lutram=1728 LUT R6#at_required.core_lutram: of those LUTs, the ones used as distributed memory (the order table and the price ladders) | as M6
M14 resources bram_tiles=0 tiles R6#at_required.bram_tiles: block RAM tiles used | ditto
M15 latency bench_feed_price_to_preamble_clocks=7 clocks R9#tick_to_trade_digital_sim.mac_register_of_price_word_to_order_preamble_clocks: the 96 design's bench-feed path, simulated, from the price word in the MAC register to the order's preamble in the MAC register (default build with the clock crossing) | simulation of the whole 96 core; a different quantity from M2 and M3 (see the datasheet's comparison)

## gaps
[board_run] Not run on a board; phase 2 would bring it behind the 10G MAC of the KR260 design (docs/phase2_integration.md).
[power] Not measured; an out-of-context build has no realistic activity and nothing ran on a board.
[E6] Out of context the clock has no buffer or jitter and the inputs are registered in the wrapper; inside the 10G core the clock and placement can differ. Only the default parameters were built.
[throughput] Measured in simulation only, and the figure is the rate of the input stream for these message sizes, not a limit of the path; no figure on a board.
[tcp] No TCP, SoupBinTCP login, client heartbeat or response handling; the frame goes to a stub port. docs/tcp_plan.md compares the options and recommends one for phase 2; it was not built or timed.
[ethernet] The path starts at the UDP payload. Header handling, the frame check and the late frame verdict of the 10G MAC are phase 2 (docs/phase2_integration.md); until then a bad frame cannot recall messages already applied or an order already triggered.
[spec] Field layouts were read from the public Nasdaq documents; the items that were recalled or assumed are marked UNCONFIRMED in docs/spec_notes.md, among them whether older OUCH 5.0 ports expect a 4 byte price and whether a TagValue length counts its tag byte. No order was ever accepted by anything but our own model.
[book] Not a full-depth book. Behaviour a user could guess wrong - more distinct prices than LEVELS or two live orders with one table index make the instrument inexact and orders on it are refused until clr_book; the position counts the quantity sent, not filled; a Replace never triggers an order; the candidate's verdict uses the book after the triggering message.
[simulators] Simulated with Icarus Verilog and cocotb only; no Verilator simulation and no formal proof of the protocol layer.
[cdc] One clock domain and no asynchronous input, so no clock-domain-crossing check applies; the crossing into the 10G core's clock is phase 2.
[data] Synthetic data from one generator with its own message mix; the figures say how the block behaves on that mix, nothing about a market.

## next_actions
1. Write the phase 2 brief from docs/phase2_integration.md - the adapter from the MAC's words, the late frame verdict, registers, and in-context timing on the KR260.
2. Build the TCP fast path of docs/tcp_plan.md option A and test it against a software exchange on the host PC.
3. Decide with the board latency whether the book-dependent risk verdict should be replaced by a faster partial check.

## open_questions
- Is the speculative start worth its abort path once the TCP headers and the 10G chain are in front of the frame?
- Should a Replace trigger an order, given that its side is known one clock after an Add's?

## history
2026-11-20 110 pr=-: RTL, reference model, generator, bench, seeded faults, out-of-context builds, TCP and phase 2 plans
