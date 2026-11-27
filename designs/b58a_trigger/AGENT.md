# AGENT b58a_trigger (fda-handover/1)
source: designs/b58a_trigger/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b58a_trigger

## identity
kind=showcase produced_by=session part=xck26-sfvc784-2LV-c board=Kria KR260 top=kr260_top tool=Vivado 2026.1
verified: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement (record: designs/b58a_trigger/VERIFIED.md, designs/b58a_trigger/verified.json; definition: docs/verified.md)

## summary
A bench model of a low-latency trading path. A packet arrives on a PL Ethernet port, its fields are parsed while it is still arriving, a rule loaded at run time decides, hardware interlocks check the order, and in speculative mode the response leaves before the incoming frame has finished (undone by a poisoned frame check sequence if the frame was bad). Simulated, formally checked in part, and built with Vivado 2026.1; never run on a board.
not: a real market path: a mock. The message format is our own (docs/bench_feed_v1.md), the traffic sources are our own, and there is no exchange, broker or market data; a board result; no latency figure here was measured on hardware, and the PHYs, the cable and the real RGMII timing are outside every number; a proof of the whole design; only interlocks.sv has a k-induction proof, and the order slot and the MAC state machines have bounded checks

## state
stage=built vivado=2026.1 kb_pin=eaf6794 build_id=8b5149c3
gates: build_2026_1=fail board_run=not-run

## interface
clk clk_25 25MHz
clk a_rxc 125MHz
clk b_rxc 125MHz
rst core reset active-high: held until the MMCM locks and the receive delay lines are calibrated (IDELAYCTRL ready), through reset synchronisers; the PHYs have a register bit that holds them in reset
if RGMII ports A and B RGMII at 1000 Mb/s, LVCMOS18; port A (PHY2, J10B) is the trading port, port B (PHY3, J10A) the generator and loop timer: the PHYs are TI DP83867 (MDIO addresses 2 and 3); receive is centre-aligned with the PHY's RX delay on and a 1000 ps IDELAY on each input; transmit is edge-aligned with the PHY's TX delay on (1.75 ns). Constraints come from the PHY datasheet and are in design.xdc, derived in docs/phy_dp83867.md doc=ip_lib/eth_mac_rgmii/README.md
if host register bus 32-bit registers over the JTAG cable (BSCANE2), word addresses 0x000 to 0xFFF: control, addresses, interlock limits, rule table, counters, order log, book and two latency histograms; a read returns data two clocks after the address. The JTAG script has not run on a board doc=designs/b58a_trigger/docs/register_map.md
if message format Bench Feed v1 over UDP, Ethernet and IPv4: our own format; UDP checksums are not checked or generated, and IPv4 options, VLAN tags and fragments are rejected doc=designs/b58a_trigger/docs/bench_feed_v1.md
param BUILD_MODE=0 legal=0, 1 or 2
param RX_IDELAY_PS=1000 legal=from the timing analysis
param NINST=256 legal=instrument count

## files
designs/b58a_trigger/rtl/kr260_top.sv fca2846bea: board top (RGMII ports, clocks, JTAG bus, port B generator and loop timer)
designs/b58a_trigger/rtl/trigger_core.sv 802883690b: the path from frame parser to order control
designs/b58a_trigger/rtl/feed_rx.sv ccc1c62f8b: Ethernet, IPv4, UDP and Bench Feed parser, field by field
designs/b58a_trigger/rtl/book.sv 216116a0a8: best bid and ask per instrument in block RAM
designs/b58a_trigger/rtl/rules.sv bf046cfda6: 8 run-time rules checked at once
designs/b58a_trigger/rtl/interlocks.sv 8157198a83: kill, halt, size, price band, position and rate checks
designs/b58a_trigger/rtl/order_ctl.sv db91763b3f: binds each order to its frame's verdict; drop, poison or cancel
designs/b58a_trigger/rtl/jtag_bus.sv 5a6042e567: register bus over the JTAG cable
designs/b58a_trigger/design.xdc c0f38a62ee: pins, clocks and the RGMII timing constraints
designs/b58a_trigger/build.yaml b4cfdb9fd4: build recipe, including the RGMII timing data from the PHY datasheet
designs/b58a_trigger/model/ref_model.py 94bdf465f8: Python reference model written from the docs, not the RTL
designs/b58a_trigger/tests/test_b58a_rtl.py 85faa7d825: cocotb tests against the model, with hostile frames
designs/b58a_trigger/tests/test_rev_adv_rtl.py d3c1ce109d: adversarial regression tests from the independent review
designs/b58a_trigger/tests/test_b58a_formal.py ed84d82687: runs the SymbiYosys jobs
designs/b58a_trigger/host/nl_rule.py 7588eaa25a: turns a sentence into a rule through a hosted language model, validated by model/rules.py
designs/b58a_trigger/docs/board_run_plan.md 9150b18a42: the board run plan; no step has been run
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
R7 results/b58a/build/summary.json ec22e14cce
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
M1 resources lut=7305 LUT R7#utilisation.CLB LUTs.used: LUTs | routed build, Vivado 2026.1, xck26-sfvc784-2LV-c, whole design
M2 resources ff=10347 FF R7#utilisation.CLB Registers.used: flip-flops | as M1
M3 resources bram_tile=6.5 tile R7#utilisation.Block RAM Tile.used: block RAM tiles | ditto
M4 timing wns_ns=-0.003 ns R7#timing_post_route.wns_ns: worst setup slack | routed, all clocks including the RGMII source-synchronous paths; the transmit window is the DP83867's, less the carrier skew bound (0.05 ns port A, 0.09 ns port B); the failing endpoint is b_txd[0], by 3 ps
M5 timing whs_ns=0.012 ns R7#timing_post_route.whs_ns: worst hold slack | as M4
M6 power power_w=0.501 W R7#power.total_on_chip_w: total on-chip power estimate | report_power after routing, vectorless, still air with no heat sink at 40 C ambient (the pessimistic bound); not a measurement
M7 latency decision_clocks_speculative=8 clocks R8#modes.speculative_1msg.decision_to_first_byte: decision latency, speculative, price field complete to first response byte | simulation, core side at 125 MHz (8 ns a clock), checksum computed before the decision; before the RGMII registers and the pins
M8 latency decision_clocks_safe=18 clocks R8#modes.safe_1msg.decision_to_first_byte: decision latency, safe mode, one-message frame | as M7; safe mode waits for the good frame check sequence
M9 latency sfd_to_first_byte_clocks=65 clocks R8#modes.speculative_1msg.tick_to_trade_sfd_to_first_byte: frame-start latency, speculative, SFD in to first response byte | as M7; 57 of these clocks are the header bytes before the price field
M10 latency decision_clocks_assemble=75 clocks R9#modes.speculative_1msg.decision_to_first_byte: decision latency when the whole frame is stored and assembled after the decision (BUILD_MODE 2) | as M7
M11 latency hist_a_min_clocks=65 clocks R10#hist_a.min: histogram A, minimum, port B loop in simulation | simulation of the generator, trading port and back, with bad-FCS and gap injection; not a board measurement

## gaps
[build_2026_1] The Vivado 2026.1 build fails one gate, post-route setup, by 3 ps on port B transmit (b_txd[0], slack -0.003 ns; port A +0.002 ns). Brief 175 did not change the architecture; the options are in the brief 175 report. Every other gate passes.
[board_run] No board run has happened and no KR260 programming path exists in the flow yet. The JTAG register script has not run on a board. docs/board_run_plan.md lists the steps.
[throughput] Not measured. Only latency was recorded; no record states a sustained order or frame rate.
[E3] Only interlocks.sv is proved (k-induction). order_ctl.sv (30 clocks) and the MAC receive and transmit state machines (20 and 40 clocks) are bounded checks; order backlogs and the saturation of its 16-bit age counter are outside the bound.
[latency] Every latency figure is simulation. The receive clock crossing, the RGMII registers, the pins, the PHY chips and the cable are outside it, and the crossing FIFO is a simulation model of the Xilinx XPM macro, so its real latency is unmeasured.
[operating conditions] No SYSMON temperature or rail readings exist because nothing ran on a board; the board run plan reads them.
[build] The transmit window rests on our reading of the DP83867 datasheet's 1.0 to 2.6 ns clock-after-data figure as the total at the PHY, and on a carrier skew bound (0.05 ns port A, 0.09 ns port B) from the carrier trace lengths; the SOM routing is unknown. The build misses that window by 3 ps on port B (met by 2 ps on port A); the board delay sweep (board_run_plan.md step 5b) tests the window itself.
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
2026-11-23 175 pr=-: PHY corrected from the assumed Marvell 88E1111 to the KR260's TI DP83867 (BOM and schematic); transmit constraints re-derived and the dead transmit constraints repaired; rebuilt, every gate passes except post-route setup, by 3 ps on port B transmit; not run on a board
