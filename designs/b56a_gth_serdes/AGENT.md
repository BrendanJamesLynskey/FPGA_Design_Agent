# AGENT b56a_gth_serdes (fda-handover/1)
source: designs/b56a_gth_serdes/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b56a_gth_serdes

## identity
kind=example produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=kr260_gth_top tool=Vivado 2026.1

## summary
A Kria KR260 design that drives one UltraScale+ GTH transceiver (quad 224, channel 2, the SFP+ cage J24) at 10.3125 Gb/s with PRBS test patterns, checks them in fabric (exact bit errors) and in the transceiver (error cycles), and reports everything over the JTAG cable through a documented register block. It is the base for the board work of brief 56. Built with Vivado 2026.1 on the free Basic licence; not yet run on a board.
not: a protocol or a link layer (RAW data, PRBS only); no Aurora or Ethernet core (10G/25G Ethernet is refused by the Basic licence); multi-lane work, meaning channel bonding, lane deskew, PCIe x4 and 40G are simulation-only on this one-lane board

## state
stage=built vivado=2026.1 kb_pin=1fc7ed8 build_id=cdb9eeef
gates: build_2026_1=pass

## interface
clk clk_25 25MHz
clk sfp_mgt_refclk 156.25MHz
rst reset helper active-high: the register block is reset while the MMCM is unlocked; the GT Wizard's reset-all is held with it and its sequence starts when it is released
if Host register block 32-bit register bus over JTAG (BSCANE2 USER4, jtag_bus): generated from regmap.py; unmapped reads return 0, no read side effects, counters read from a snapshot doc=designs/b56a_gth_serdes/docs/register_map.md
if SFP+ lane and control pins one GTH lane at 10.3125 Gb/s; tx_disable, mod_abs, rx_los, tx_fault, I2C: the laser is disabled at reset (tx_disable = 1; polarity unconfirmed until the first board run) doc=designs/b56a_gth_serdes/docs/board_run_plan.md
param line rate=10.3125 Gb/s legal=0.5 to 12.5 Gb/s on this part (-2LV), subject to the PLL windows in flow/gt_data.py
param user data width=64 bits on a 32-bit internal path legal=32/64 pairs allowed by DS925 table 104

## files
designs/b56a_gth_serdes/rtl/gth_serdes_core.sv 1c0fe7acf1: GT Wizard wrapper, registers, snapshot, DRP and SYSMON windows
designs/b56a_gth_serdes/rtl/prbs64.sv 9b8dfb6fd1: fabric PRBS generator and checker
designs/b56a_gth_serdes/rtl/kr260_gth_top.sv b69b051f3a: board top (MMCM, SYSMON, pins)
designs/b56a_gth_serdes/design.xdc 60018c8f19: pins, clocks, slow-pin constraints
designs/b56a_gth_serdes/ip/amd_ip.tcl 66d54de6a5: creates the GT Wizard core (hash-listed in flow/ip_tcl_allow.yaml)
designs/b56a_gth_serdes/regmap.py 34a85543ac: the register map as data; generates docs/register_map.md
designs/b56a_gth_serdes/docs/register_map.md cf312ad0e3: interface datasheet
designs/b56a_gth_serdes/docs/board_run_plan.md 129e5775d0: the board plan for brief 56B

## commands
simulate the PRBS blocks and the core against the Wizard stand-in (~1min): python -m pytest -q designs/b56a_gth_serdes/tests
[heavy] build the design and run all gates (~7min): flow/run_vivado.sh designs/b56a_gth_serdes base

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b56a_gth_serdes/tests/test_b56a_core_sim_rtl.py d7bd3da661
R2 results/56a_serdes/gt_build/gates.json 6e3accd275
R3 results/56a_serdes/README.md 6f5635a12a
R4 results/56a_serdes/gt_build/run.json 4bc1a348be

## evidence
E1 simulation pass R1 ci: fabric PRBS generator and checker against an independent model (exact error counting, lock, loss of lock); register block, bring-up, counting, injection, snapshots, I2C, SYSMON and DRP windows against a behavioural stand-in of the Wizard
E2 build pass R2: synthesis, implementation and bitstream on the Basic tier; every flow gate and every GT gate passes
E3 review pass R3: one independent correctness review (Sonnet) and one fix round

## measured
M1 resources lut=973 LUT R2#utilization.lut: LUTs | routed, Vivado 2026.1
M2 resources ff=3106 FF R2#utilization.ff: registers | as M1
M3 timing wns_ns=2.156 ns R2#timing.wns_ns: worst setup slack | routed, user clocks 161.133 MHz and 100 MHz
M4 timing whs_ns=0.016 ns R2#timing.whs_ns: worst hold slack | as M3
M5 power power_w=0.764 W R2#power.total_w: total on-chip power estimate | report_power after routing, vectorless, confidence Medium
M6 other -=4235 MiB R4#vivado_peak_rss_mib: Vivado peak resident memory of the first GT build | 2 threads, MemoryMax=8G, alone on the machine, one run

## gaps
[latency] Not measured; the design has no data path latency requirement and the stand-in has no transceiver latency. Board work (56B) is the first chance.
[throughput] The line rate is 10.3125 Gb/s by configuration; no throughput or error-rate measurement exists because nothing ran on a board.
[hardware] Nothing has run on a board. The reference clock source and frequency, the 25 MHz input, the SFP+ control pin functions and the TX_DISABLE polarity are unconfirmed (open-source example, not the schematic).
[simulation] AMD's Wizard simulation model is refused by the free Vivado Simulator (54716 instances against 50000); the register-level bench uses a behavioural stand-in, so the transceiver itself is untested.
[counters] The hard PRBS checker counts cycles with an error, not bits; TXPRBSFORCEERR may inject two errors per pulse with these clock ratios (UG576); the DRP window hangs if used while the transceiver is in reset (no timeout).
[behaviour] Guessable wrongly (docs/register_map.md): unmapped reads return 0 and writes are ignored; PULSE bits are strobes and read 0; counters change only on a snapshot; DRP_DATA reads the last read, not the last write; reads have no side effects.
[review] One review round; STATUS bits 6 and 7 are reserved; the planner does not check that a rate is reachable from the reference by an integer divider; SYSMON conversion to physical units is not implemented.

## next_actions
1. Run docs/board_run_plan.md on the KR260 (laser polarity first, then near-end loopback BER, then the optical loop).
2. Confirm the reference clock and the control pins against the carrier schematic.
3. Build an I2C master for the module's SFF-8472 diagnostics.

## open_questions
- Does the PL load over JTAG with the PS idle on the new SD card state? (board_run_plan.md section 1)

## history
2026-11-13 56A pr=-: design, gates, probe and knowledge written; one independent review round
