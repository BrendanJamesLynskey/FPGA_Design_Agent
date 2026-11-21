# AGENT b102_managed_fcs (fda-handover/1)
source: designs/b102_managed_fcs/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b102_managed_fcs

## identity
kind=demonstration produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=fcs_top tool=Vivado 2026.1

## summary
A KR260 self-test of an Ethernet FCS stage that exists to demonstrate a managed project (brief 102). An owned sequencer sends a fixed sixteen-word frame through a CRC-32 block that was made outside the project as an EDIF netlist and is frozen, and shows the verdict on an LED; a heartbeat divider is excluded from the agent's view but built with the rest. project.yaml marks each part, and the agent's tools enforce it.
not: a 10G Ethernet FCS check; the CRC block takes sixteen bits a clock, not the 64-bit word of the 96 design, because the open equivalence engines could not prove 64 bits; a board design; it was not programmed, and the 161 MHz clock constraint is on the 25 MHz oscillator pin for a timing study

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=fd07818d
gates: import_checks=pass build_2026_1=pass boundary_checks=pass

## interface
clk clk_25 161.13MHz
rst power-on counter active-high: a four-clock shift register in fcs_top holds every block in synchronous reset after configuration; there is no reset input
if crc32_d16 slot black-box module filled by an EDIF netlist (build.yaml netlists): the contract is in project.yaml (ports, clock, reset, boundary timing budgets); behaviour a user could guess wrong is in the header of ext/reference/crc32_d16.sv (register not complement, little-endian words, hold on en low, reset wins) doc=designs/b102_managed_fcs/project.yaml
param N_WORDS=16 legal=1 to 254 (the counter is eight bits wide in the word function)
param EXPECT=0x79D3D43A legal=the CRC register value of the frame, from flow/managed_import.crc32_model

## files
designs/b102_managed_fcs/project.yaml 5e12c73fd8: the managed-project manifest, ownership and contracts of the four components
designs/b102_managed_fcs/rtl/fcs_top.sv 5cf2f929fe: top level, power-on reset and the LEDs
designs/b102_managed_fcs/rtl/fcs_ctrl.sv 2e11253b3f: the owned sequencer and FCS verdict
designs/b102_managed_fcs/ext/crc32_d16.edf b602ea89bb: the frozen CRC-32 block as an EDIF netlist made by Yosys outside the project
designs/b102_managed_fcs/ext/reference/crc32_d16.sv 5fd46dc110: the supplier's RTL, the reference for the equivalence proof (not in the build)
designs/b102_managed_fcs/build.yaml 3d2d8b3271: how flow/run_vivado.sh builds the design, with the netlist

## commands
import checks (interface, licence, simulation, eqy) (~1min): python3 flow/managed_import.py check designs/b102_managed_fcs --sim --eqy
the scripted agent session on a scratch copy (~1min): python3 designs/b102_managed_fcs/scripts/demo_managed_session.py
[heavy] build and run the gates (~12min): flow/run_vivado.sh designs/b102_managed_fcs base

## records (path sha256-prefix; claims below cite R<n>)
R1 agent/tests/test_102_managed.py 66813399dc
R2 results/102_managed/import_check.json a76aed2d1e
R3 results/102_managed/eqy_fault.json 547b2e0178
R4 results/102_managed/demo_session.json a8da549f48
R5 results/102_managed/boundary.json 73755c3cf4
R6 results/102_managed/latency.json b174f5be8d
R7 results/102_managed/builds.json e3cb7b1d4f

## evidence
E1 simulation pass R1 ci: ownership, scope, contract and path-trick tests of the agent's tools; the import checks, the boundary parsers and the build plumbing
E2 simulation pass R2: the netlist's interface equals the contract, the licence and hash are recorded, 400 simulated vectors match the model, and eqy proves the supplier's RTL equivalent to the netlist
E3 faults pass R3: one flipped LUT INIT bit in the netlist fails both the simulation and the eqy proof
E4 review pass R4: the scripted session edits only the owned controller; its attempts on the frozen netlist, the excluded block, the out-of-scope top, a port change, a dropped build source and the manifest are all refused
E5 build pass R5: both builds (before and after the edit) pass every gate on Vivado 2026.1, with the CRC block read from its EDIF netlist; the boundary check finds no CDC row on the slot and both boundary timing budgets are met

## measured
M1 latency latency_clocks=1 clocks R6#clocks_saved: clocks saved by the agent session's edit (first cycle in which pass_o rises, baseline minus edited) | Icarus simulation, CRC block from its functional netlist, counted from power-up
M2 resources lut=76 LUT R7#builds.baseline.lut: LUTs, whole design including the frozen CRC netlist | routed build, Vivado 2026.1, xck26-sfvc784-2LV-c
M3 resources ff=74 FF R7#builds.baseline.ff: flip-flops, whole design | routed build, Vivado 2026.1
M4 timing wns_ns=3.594 ns R7#builds.baseline.wns_ns: worst setup slack at the 6.206 ns clock | routed, 161.13 MHz constraint on the 25 MHz pin
M5 timing whs_ns=0.086 ns R7#builds.baseline.whs_ns: worst hold slack | routed, 6.206 ns clock
M6 power power_w=0.337 W R7#builds.baseline.power_w: total on-chip power estimate | report_power after routing, vectorless, never run on a board
M7 timing wns_ns_edited=3.894 ns R7#builds.edited.wns_ns: worst setup slack after the agent session's edit | routed, 6.206 ns clock, controller with the registered compare stage removed

## gaps
[power] The estimate is vectorless at default toggle rates; this is a timing study that was never run on a board, so no power measurement is claimed.
[throughput] Not applicable beyond the clock; the block takes two bytes a clock by construction and no throughput measurement was made.
[width] The CRC block is sixteen bits wide; the 10G design uses sixty-four. The open engines of eqy proved 8 and 16 bits within two minutes and not 32 or 64 (results/102_managed/eqy_width_scaling.json).
[board] Never programmed; no hardware evidence and no operating conditions exist.
[behaviour] The design has no reset input and one fixed frame; the verdict LED is sticky until the next configuration, a corrupted word in a later frame does not clear it.

## next_actions
1. Record the two Vivado builds, the gates and the boundary checks, and replace the resources and timing gaps with their measurements.
2. Stage 2 of brief 102 imports a placed-and-routed block and relocates it with RapidWright.

## open_questions
- Which owner-approved block should be the first real external import (stage 3 of brief 102)?

## history
2026-11-17 102 pr=-: written for stage 1 of the managed-project brief
