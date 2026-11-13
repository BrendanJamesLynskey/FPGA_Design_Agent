# AGENT b58a_trigger (fda-handover/1)
source: designs/b58a_trigger/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b58a_trigger

## identity
kind=showcase produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=kr260_top tool=Vivado 2026.1

## summary
A bench model of a low-latency trading path. A packet arrives on a PL Ethernet port, its fields are parsed while it is still arriving, a rule loaded at run time decides, hardware interlocks check the order, and in speculative mode the response leaves before the incoming frame has finished (undone by a poisoned frame check sequence if the frame was bad). Simulated, formally checked in part, and built with Vivado 2026.1; never run on a board.
not: a real market path: a mock. The message format is our own (docs/bench_feed_v1.md), the traffic sources are our own, and there is no exchange, broker or market data; a board result; no latency figure here was measured on hardware, and the PHYs, the cable and the real RGMII timing are outside every number; a proof of the whole design; only interlocks.sv has a k-induction proof, and the order slot and the MAC state machines have bounded checks

## state
stage=built vivado=2026.1 kb_pin=1fc7ed8 build_id=a4aa23de
gates: build_2026_1=pass board_run=not-run

## interface
clk clk_25 25MHz
clk a_rxc 125MHz
clk b_rxc 125MHz
rst core reset active-high: held until the MMCM locks and the receive delay lines are calibrated (IDELAYCTRL ready), through reset synchronisers; the PHYs have a register bit that holds them in reset
if RGMII ports A and B RGMII at 1000 Mb/s, LVCMOS18; port A (PHY2, J10B) is the trading port, port B (PHY3, J10A) the generator and loop timer: receive is centre-aligned with the PHY's RX delay on and a 1000 ps IDELAY on each input; transmit is edge-aligned with the PHY's TX delay on. Constraints come from the PHY datasheet and are in design.xdc doc=ip_lib/eth_mac_rgmii/README.md
if host register bus 32-bit registers over the JTAG cable (BSCANE2), word addresses 0x000 to 0xFFF: control, addresses, interlock limits, rule table, counters, order log, book and two latency histograms; a read returns data two clocks after the address. The JTAG script has not run on a board doc=designs/b58a_trigger/docs/register_map.md
if message format Bench Feed v1 over UDP, Ethernet and IPv4: our own format; UDP checksums are not checked or generated, and IPv4 options, VLAN tags and fragments are rejected doc=designs/b58a_trigger/docs/bench_feed_v1.md
param BUILD_MODE=0 legal=0, 1 or 2
param RX_IDELAY_PS=1000 legal=from the timing analysis
param NINST=256 legal=instrument count

## files
designs/b58a_trigger/rtl/kr260_top.sv d57f5f9d6e: board top (RGMII ports, clocks, JTAG bus, port B generator and loop timer)
designs/b58a_trigger/rtl/trigger_core.sv a2574194eb: the path from frame parser to order control
designs/b58a_trigger/rtl/feed_rx.sv ccc1c62f8b: Ethernet, IPv4, UDP and Bench Feed parser, field by field
designs/b58a_trigger/rtl/book.sv 216116a0a8: best bid and ask per instrument in block RAM
designs/b58a_trigger/rtl/rules.sv bf046cfda6: 8 run-time rules checked at once
designs/b58a_trigger/rtl/interlocks.sv 37a99e59c6: kill, halt, size, price band, position and rate checks
designs/b58a_trigger/rtl/order_ctl.sv db91763b3f: binds each order to its frame's verdict; drop, poison or cancel
designs/b58a_trigger/rtl/jtag_bus.sv c56593b3f6: register bus over the JTAG cable
designs/b58a_trigger/design.xdc 62c1e380c0: pins, clocks and the RGMII timing constraints
designs/b58a_trigger/build.yaml 6f8f5777a3: build recipe, including the RGMII timing data from the PHY datasheet
designs/b58a_trigger/model/ref_model.py bf2f0369fc: Python reference model written from the docs, not the RTL
designs/b58a_trigger/tests/test_b58a_rtl.py 85faa7d825: cocotb tests against the model, with hostile frames
designs/b58a_trigger/tests/test_rev_adv_rtl.py d3c1ce109d: adversarial regression tests from the independent review
designs/b58a_trigger/tests/test_b58a_formal.py ed84d82687: runs the SymbiYosys jobs
designs/b58a_trigger/host/nl_rule.py 933decf496: turns a sentence into a rule through a hosted language model, validated by model/rules.py
designs/b58a_trigger/docs/board_run_plan.md f7c240f3ce: the board run plan; no step has been run
designs/b58a_trigger/showcase/trading_path.yaml a9ef8b6cc2: the showcase entry, in progress, no numbers until a board result

## commands
simulation tests against the reference model (~10min): python3 -m pytest -q designs/b58a_trigger/tests/test_b58a_model.py designs/b58a_trigger/tests/test_b58a_records.py designs/b58a_trigger/tests/test_b58a_rtl.py
regenerate the simulation records (~10min): B58A_RECORD=results/b58a python3 -m pytest -q designs/b58a_trigger/tests/test_b58a_rtl.py
formal checks (~30min): python3 -m pytest -q designs/b58a_trigger/tests/test_b58a_formal.py
[heavy] build the KR260 bitstream (~23min): flow/run_vivado.sh designs/b58a_trigger

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b58a_trigger/tests/test_b58a_rtl.py 85faa7d825
R2 designs/b58a_trigger/tests/test_rev_adv_rtl.py d3c1ce109d
R3 results/b58a/formal.json a1d4d11567
R4 results/b58a/mac_rgmii_faults.json 1ec1e53e3e
R5 results/b58a/pins_sim.json ac8a706f11
R6 results/b58a/nl_rules.json 0e81038cbe
R7 results/b58a/build/summary.json dde54251b4
R8 results/b58a/latency_sim.json 3e6bded690
R9 results/b58a/latency_sim_assemble.json 6b7d0bbd16
R10 results/b58a/loop_sim.json 1a99b954a5

## evidence
E1 simulation pass R1 ci: cocotb tests against the Python reference model, random streams with hostile frames in speculative and safe mode
E2 simulation pass R2 ci: adversarial regression tests from the independent review; every order from a bad frame is dropped, poisoned or cancelled
E3 formal partial R3: interlocks.sv has a k-induction proof; the order slot and the MAC receive and transmit state machines have bounded checks, not proofs
E4 faults pass R4: 10 deliberately injected bugs in the Ethernet MAC library block, each detected by its test suite
E5 simulation pass R5: kr260_top with RGMII looped from port B to port A in simulation; all frames arrive intact (the clock-crossing FIFO is its simulation model)
E6 review pass R6: ten recorded sentences for the natural-language rule step, checked offline against meanings written by hand; one expectation was changed after the model's reply was seen (recorded in the file)
E7 build pass R7: KR260 build on Vivado 2026.1; every gate passes through bitstream (built, not programmed)

## measured
M1 resources lut=7225 LUT R7#utilisation.CLB LUTs.used: LUTs | routed build, Vivado 2026.1, xck26-sfvc784-2LV-c, whole design
M2 resources ff=10318 FF R7#utilisation.CLB Registers.used: flip-flops | as M1
M3 resources bram_tile=6.5 tile R7#utilisation.Block RAM Tile.used: block RAM tiles | ditto
M4 timing wns_ns=0.102 ns R7#timing_post_route.wns_ns: worst setup slack | routed, all clocks including the RGMII source-synchronous paths; the transmit window assumes 0.1 ns of board skew
M5 timing whs_ns=0.01 ns R7#timing_post_route.whs_ns: worst hold slack | as M4
M6 power power_w=0.501 W R7#power.total_on_chip_w: total on-chip power estimate | report_power after routing, vectorless, still air with no heat sink at 40 C ambient (the pessimistic bound); not a measurement
M7 latency decision_clocks_speculative=8 clocks R8#modes.speculative_1msg.decision_to_first_byte: decision latency, speculative, price field complete to first response byte | simulation, core side at 125 MHz (8 ns a clock), checksum computed before the decision; before the RGMII registers and the pins
M8 latency decision_clocks_safe=18 clocks R8#modes.safe_1msg.decision_to_first_byte: decision latency, safe mode, one-message frame | as M7; safe mode waits for the good frame check sequence
M9 latency sfd_to_first_byte_clocks=65 clocks R8#modes.speculative_1msg.tick_to_trade_sfd_to_first_byte: frame-start latency, speculative, SFD in to first response byte | as M7; 57 of these clocks are the header bytes before the price field
M10 latency decision_clocks_assemble=75 clocks R9#modes.speculative_1msg.decision_to_first_byte: decision latency when the whole frame is stored and assembled after the decision (BUILD_MODE 2) | as M7
M11 latency hist_a_min_clocks=65 clocks R10#hist_a.min: histogram A, minimum, port B loop in simulation | simulation of the generator, trading port and back, with bad-FCS and gap injection; not a board measurement

## gaps
[board_run] No board run has happened and no KR260 programming path exists in the flow yet. The JTAG register script has not run on a board. docs/board_run_plan.md lists the steps.
[throughput] Not measured. Only latency was recorded; no record states a sustained order or frame rate.
[E3] Only interlocks.sv is proved (k-induction). order_ctl.sv (30 clocks) and the MAC receive and transmit state machines (20 and 40 clocks) are bounded checks; order backlogs and the saturation of its 16-bit age counter are outside the bound.
[latency] Every latency figure is simulation. The receive clock crossing, the RGMII registers, the pins, the PHY chips and the cable are outside it, and the crossing FIFO is a simulation model of the Xilinx XPM macro, so its real latency is unmeasured.
[operating conditions] No SYSMON temperature or rail readings exist because nothing ran on a board; the board run plan reads them.
[build] The transmit window assumes 0.1 ns of TXC-to-TXD skew on the KR260, which is not in our notes; the schematic or the layout report would confirm it. Worst transmit setup slack is the smallest margin in the build.
[behaviour] One order slot, at most one request per frame. A bad frame's book updates are not rolled back. No UDP checksum checks. The kill is a register only because the KR260 has no PL push button.
[tick-to-config] The 2,125-clock tick-to-config figure includes 2,000 clocks of software time that is assumed, not measured; it shows the mechanism.

## next_actions
1. Run the board run plan, starting with the bench loop between the two PL ports, and read SYSMON during each run.
2. Add a KR260 programming path to the flow.
3. Confirm the TXC-to-TXD skew from the schematic or the layout report and re-derive the transmit constraints.

## open_questions
- Should the order slot be widened so that several orders can be outstanding?

## history
2026-11-12 58a pr=-: built, simulated and formally checked; Vivado 2026.1 build closes with all gates passing; not run on a board
2026-11-13 68 pr=-: handover written to the documentation standard
