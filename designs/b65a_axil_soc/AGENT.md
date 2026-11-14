# AGENT b65a_axil_soc (fda-handover/1)
source: designs/b65a_axil_soc/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b65a_axil_soc

## identity
kind=example produced_by=human part=xc7a100tcsg324-1 board=Nexys A7-100T top=b65a_axil_soc_top tool=Vivado 2026.1

## summary
The brief 65A sample block design. A DDS tone generator and a frequency and duty counter (grouped as the tone hierarchy) and a logic analyser, all from ip_lib, sit behind a generated AXI4-Lite crossbar that the host reaches through the UART test shell. blockdesign.yaml and tone.yaml are the source; everything under gen/ (top, wrappers, address map, graph) is generated from them. It shows the block-design format, its checks and the generator, and was built; it has not been run on a board.
not: a showcase or a board-verified design; the bitstream was built, not programmed; a general interconnect; generation covers AXI4-Lite only, 32-bit data and one clock domain

## state
stage=built vivado=2026.1 kb_pin=20d73e8 build_id=2b28c63c
gates: build_2026_1=pass board_run=not-run

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the reset button; synchronised into the sys domain, where the generated blocks see a synchronous active-high rst
if UART register window test shell, 8N1 UART at 115200 baud: the window is an AXI4-Lite master (bd_win_axil_master); window registers ADDR, WDATA, CTRL, STATUS, RDATA at offsets 0x00-0x04; one transfer at a time, ignored while busy doc=shell/PROTOCOL.md
if Address map AXI4-Lite slaves behind axil_xbar: tone.s_dds 0x40000000, tone.s_fd 0x40001000, la.s_axil 0x40010000, 4 KB each; the register layout of each block is in that file doc=designs/b65a_axil_soc/gen/address_map.md
if LEDs LED[15:0] (LVCMOS33): LED[15:8] show the high byte of the DDS sample; LED[7:0] are tied to 0
param CLKS_PER_BIT=868 legal=derived from the clock; raised to a top-module parameter
param tone.fd.GATE_CLKS=1,000,000 legal=a positive integer; raised to a top-module parameter
param la ADDR_W=8 legal=per ip_lib/logic_analyser
param dds=PHASE_W 32, LUT_W 8, OUT_W 16, variant bram legal=per ip_lib/dds_awg

## files
designs/b65a_axil_soc/blockdesign.yaml 336ec09a35: the source; instances, connections, interconnect, address map
designs/b65a_axil_soc/tone.yaml ae1887c1f9: the tone hierarchy; DDS and frequency counter with their register definitions
designs/b65a_axil_soc/gen/address_map.md 598c086cd3: generated address map and register tables
designs/b65a_axil_soc/gen/graph.json f235b29f94: generated graph that the viewer draws
designs/b65a_axil_soc/gen/manifest.json 810abcec95: generated; input and output hashes, components, diagnostics
designs/b65a_axil_soc/design.xdc a0619232b1: pins and the 100 MHz clock
designs/b65a_axil_soc/tests/test_b65a_rtl.py 583424fc10: generated design simulated end to end through the UART shell
docs/blockdesign.md 500c66d77b: user guide to the format, validation and generator

## commands
validate the block design: python3 -m flow.blockdesign validate designs/b65a_axil_soc
regenerate gen/ from the two YAML files: python3 -m flow.blockdesign generate designs/b65a_axil_soc
check gen/ against the sources: python3 -m flow.blockdesign check designs/b65a_axil_soc
simulate end to end (~1min): python -m pytest -q designs/b65a_axil_soc/tests/test_b65a_rtl.py
[heavy] build (~4min): flow/run_vivado.sh designs/b65a_axil_soc

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b65a_axil_soc/tests/test_b65a_rtl.py 583424fc10
R2 flow/blockdesign/tests/test_65a_blockdesign.py 87d41b298c
R3 results/65a_blockdesign/faults.json 987ffa0570
R4 results/65a_blockdesign/vivado_build/gates.json 476929e068
R5 results/blockdesign/b65a_axil_soc/build.json 0f94c01fe9
R6 results/65a_blockdesign/sim_end_to_end.json 82ca2d20f8

## evidence
E1 simulation pass R1 ci: generated top under cocotb and Icarus through the UART shell, with the AXI4-Lite protocol checker and the missing-response monitor (brief 71) on every top-level link; reset values, strobes, error responses, the tone counted and the analyser samples checked
E2 review pass R2 ci: pure-Python tests of the block-design validator and generator, an adversarial case per rule, including the generated files matching their sources
E3 faults pass R3: seeded faults in the crossbar ip_lib/axil_xbar, each caught by its bench
E4 build pass R4: whole-board build on Vivado 2026.1; every gate passes
E5 model pass R5: the viewer's graph against the synthesised netlist; all 14 expected instances found, the crossbar's address ranges equal the built RTL's

## measured
M1 resources lut=1093 LUT R4#utilization.lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1, including the test shell
M2 resources ff=1150 FF R4#utilization.ff: flip-flops, whole board design | as M1
M3 resources bram_tile=0.5 tiles R4#utilization.bram_tile: block RAM tiles, whole board design | ditto
M4 timing wns_ns=2.933 ns R4#timing.wns_ns: worst setup slack | routed, 100 MHz clock
M5 timing whs_ns=0.076 ns R4#timing.whs_ns: worst hold slack | ditto
M6 power power_w=0.13 W R4#power.total_w: total on-chip power estimate | report_power after routing, vectorless, confidence Medium
M7 verification -=86 transfers R6#axi_transfers: AXI4-Lite transfers in the end-to-end simulation | simulation, with no protocol rule broken on the four top-level links
M8 verification -=62 edges R6#edges: rising edges the frequency counter read in the gate | simulation, a 4000-clock gate for a 64-clock tone, so 62.5 expected
M9 verification -=10 faults R3#caught: crossbar seeded faults caught | of 10, the crossbar alone

## gaps
[board_run] No board run was attempted. A smoke run reading the three blocks over the UART would put it on hardware; nothing in the records shows the UART, the DDS output or the LEDs working on the device.
[latency] Not measured. The records count transfers, not clocks per transfer through the shell master and crossbar.
[throughput] Not measured. The shell master does one transfer at a time over a 115200-baud link, so the rate is set by the UART; no record times it.
[power] Vectorless estimate only; the tone generator's real switching activity is not in it.
[E1] The end-to-end bench exercises the generated design in simulation only, with a shortened UART bit time and a shortened gate; the full-length parameters were built but not simulated.
[E2] There is no seeded-fault run against the generator's own output or the support RTL (the shell master, the window adapter and the register bank); the end-to-end test covers them functionally only.
[E3] Faults cover the crossbar alone. The parameter guards of the crossbar and the support RTL run in simulation only; Vivado ignores them.
[E5] The graph check compares 6 of the 7 links; the inverted sample bit that feeds the frequency counter goes through logic and is not compared.
[build identity] The recorded build was made from a tree with uncommitted changes (git_dirty is true in run.json), at 2 threads; the build ID covers the thread count and the inputs, so it changes when either does.
[scope] Generation covers AXI4-Lite with 32-bit data and a single clock domain; AXI4 and AXI4-Stream links are checked and wired point to point only; no interrupt concatenation and no debug-core automation.
[behaviour] From the generated gen/address_map.md: addresses between the blocks' ranges (0x40002000 to 0x4000FFFF) get DECERR from the crossbar; inside the register-bank blocks an offset with no register, and a write to a read-only register, answer SLVERR with read data 0, which that file says agrees with the house convention for a read of a hole (split response: SLVERR, read 0) and differs for a write, which the house convention answers with OKAY and ignores; the banks have no error-capture registers; la.s_axil answers SLVERR from offset 0x200. Byte strobes are honoured on control registers. fd offset 0x000 is a SCRATCH register with no block input. The master keeps one write and one read in flight.

## next_actions
1. Add a board smoke run over the UART that reads the three blocks and checks the reset values, and record it with its operating conditions.
2. Bring the hand-written register banks (flow/blockdesign/rtl/bd_axil_regs.sv, bd_axil_win.sv) in line with the house split response (a write to an unmapped offset answers OKAY) and give them the error-capture registers, or generate them with hwsw/regmap.py; until then gen/address_map.md states how they differ. Then regenerate gen/ and the docs.
3. Use the viewer as the how-it-works diagram on other showcase pages, and add the remaining items in docs/blockdesign.md under Not yet.

## open_questions
- The register-map format is 65A's own; should brief 64A's single source consume or replace it?

## history
2026-11-13 65A pr=-: block-design format, validator, generator, crossbar ip_lib/axil_xbar and viewer built; this sample validated, generated, simulated and built on Vivado 2026.1
2026-11-13 68 pr=-: handover written to the documentation standard
