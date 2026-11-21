# AGENT b102_managed_pr (fda-handover/1)
source: designs/b102_managed_pr/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b102_managed_pr

## identity
kind=demonstration produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=pr_top tool=Vivado 2026.1
verified: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement (record: designs/b102_managed_pr/VERIFIED.md, designs/b102_managed_pr/verified.json; definition: docs/verified.md)

## summary
A KR260 timing study that exists to demonstrate stage 2 of a managed project (brief 102). The block pcs_unit, brief 96's 64b/66b transmit path, arrives as a placed, routed and locked checkpoint made outside the project and is frozen; an owned stimulus and sink around it are placed and routed by Vivado. project.yaml records the block's keep-out region, the agent's tools refuse to place or constrain anything inside it, and the block's internal timing is measured at six placements, relocated by RapidWright and not.
not: a 10G Ethernet design; the block is the 64b/66b encoder and scrambler between a shift register and an XOR sink, with three input pins; a board design; it was not programmed, and the 250 MHz constraint is on the 25 MHz oscillator pin for a timing study; a claim that relocation preserves a block's timing everywhere; the results say where it does and where it does not

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=7874befe
gates: import_checks=pass build_2026_1=pass boundary_checks=pass

## interface
clk clk_25 250MHz
rst power-on counter active-high: a four-clock shift register in pr_top holds the owned logic and the block in synchronous reset after configuration; there is no reset input
if pcs_unit slot black-box module filled by a locked placed-and-routed checkpoint (build.yaml netlists, format checkpoint): the contract is in project.yaml (ports, clock, reset, boundary timing budgets, keep-out region); the block's input shift register has no reset, so its first 72 outputs after configuration depend on what shifted in, and the reset must be held for 80 clocks while data shifts in before the output is comparable with the supplier's RTL (the import simulation does this) doc=designs/b102_managed_pr/project.yaml
param placement.region=SLICE_X26Y70:SLICE_X37Y91 legal=a slice range that contains the block's footprint (slices X27..34, Y72..90)
param placement.timing_tolerance_ps=0 legal=a whole number of picoseconds, 0 or more

## files
designs/b102_managed_pr/project.yaml 66ddde7e3b: the managed-project manifest, ownership, contracts and the block's placement keep-out
designs/b102_managed_pr/rtl/pr_top.sv ac0783fa4d: top level, power-on reset and the LEDs
designs/b102_managed_pr/rtl/pr_src.sv 349d147ce9: the owned LFSR that feeds the block's serial input
designs/b102_managed_pr/rtl/pr_sink.sv 1763a9b589: the owned consumer of the block's output and the LED drivers
designs/b102_managed_pr/ext/pcs_unit_p0.dcp 71ca7f7bcd: the frozen block as a placed, routed and locked checkpoint made by Vivado outside the project
designs/b102_managed_pr/ext/reference/pcs_unit.sv c825d999f4: the supplier's RTL, the reference for the import simulation (not in the build)
designs/b102_managed_pr/build.yaml ca72c9c40e: how flow/run_vivado.sh builds the design, with the checkpoint
designs/b102_managed_pr/design.xdc c070fe60db: the pins and the 4.0 ns clock; the agent's file, kept out of the block's keep-out region

## commands
[heavy] import check (interface, licence, lock, footprint, simulation) (~3min): python3 flow/managed_placed.py check designs/b102_managed_pr --sim
[heavy] the placement runs and the evidence (~45min): designs/b102_managed_pr/scripts/run_placements.sh && designs/b102_managed_pr/scripts/run_dumps.sh
the scripted agent session (~1min): python3 designs/b102_managed_pr/scripts/demo_managed_session.py
[heavy] build and run the gates (~15min): flow/run_vivado.sh designs/b102_managed_pr base

## records (path sha256-prefix; claims below cite R<n>)
R1 agent/tests/test_102_stage2.py a3c75a92a0
R2 results/102_managed_pr/import_check.json 0b74a51c70
R3 results/102_managed_pr/import_fault.json b666d18522
R4 results/102_managed_pr/placements/placement_evidence.json a1300a0c62
R5 results/102_managed_pr/placements/placement_evidence_all.json 9fd16b932e
R6 results/102_managed_pr/demo_session.json 64cd49f4ea
R7 results/102_managed_pr/boundary.json 5168e2c230
R8 results/102_managed_pr/builds.json cf5d2c57a1

## evidence
E1 simulation pass R1 ci: the manifest rules, the keep-out on constraints and on the RapidWright tools' arguments, the trust label's need for placement evidence, the import check's reading of a checkpoint's facts and the placement comparison
E2 simulation pass R2: interface equals the contract, the licence and hash are recorded, every placeable cell has a fixed location and BEL and every routed net has fixed routing, the footprint is inside the keep-out region, and the functional netlist matches the supplier's RTL
E3 faults pass R3: one flipped LUT INIT bit in the functional netlist fails the simulation
E4 build pass R4: Vivado left every cell, BEL and route of the block alone at the four adopted placements (the delivered one, two re-placements of the owned logic around it, and a relocation by one clock region), the interconnect delays inside it are identical at all four, its netlist fingerprint is the same, and the boundary budgets are met
E5 build fail R5: the same evidence for all six placements fails at tolerance 0 ps for two of them, because relocation by half a clock region (largest change 161 ps) and to another column (275 ps) changes interconnect delays
E6 review pass R6: the scripted session's attempts on the checkpoint, a pblock and a LOC inside the keep-out, a placement property on the block, the RapidWright tools aimed at the block, and an out-of-scope file are all refused; the real placement tool places owned cells around the block and the written checkpoint holds the block unchanged
E7 build pass R7: the flow build passes every gate on Vivado 2026.1 with the block read from its checkpoint; the boundary budgets are met on the routed build

## measured
M1 resources lut=735 LUT R8#builds.baseline.lut: LUTs, whole design including the frozen block | routed build, Vivado 2026.1, xck26-sfvc784-2LV-c
M2 resources ff=387 FF R8#builds.baseline.ff: flip-flops, whole design | routed build, Vivado 2026.1
M3 timing wns_ns=0.061 ns R8#builds.baseline.wns_ns: worst setup slack at the 4.0 ns clock | routed, 250 MHz constraint on the 25 MHz pin
M4 timing whs_ns=0.06 ns R8#builds.baseline.whs_ns: worst hold slack | routed, 4.0 ns clock
M5 power power_w=0.369 W R8#builds.baseline.power_w: total on-chip power estimate | report_power after routing, vectorless, never run on a board
M6 timing relocation_region_identical_pins=5197 pins R5#placements.p1.net_delays.identical_pins: interconnect delays inside the block that are identical (to the picosecond) when it is relocated by one clock region (60 slice rows), of the pin delays compared | Vivado 2026.1 get_net_delays on the written checkpoint, block relocated by RapidWright, other logic placed and routed around it
M7 timing relocation_half_region_max_diff_ps=161 ps R5#placements.p2.net_delays.max_abs_diff_ps: largest change of an interconnect delay inside the block when it is relocated by half a clock region (30 slice rows) | same as M6, placement p2
M8 timing relocation_other_column_max_diff_ps=275 ps R5#placements.p3.net_delays.max_abs_diff_ps: largest change of an interconnect delay inside the block when it is relocated to another slice column | same as M6, placement p3

## gaps
[E5] The evidence for all six placements fails by design of the demonstration; the project adopts the four placements of E4 and the other two are recorded as not adoptable at tolerance 0 ps.
[power] The estimate is vectorless at default toggle rates; this is a timing study that was never run on a board, so no power measurement is claimed.
[latency] Not measured; the design is a timing and placement study, and the block's latency in clocks is the supplier's, from its RTL.
[throughput] Not applicable beyond the clock; the block takes one bit a clock by construction and no throughput measurement was made.
[board] Never programmed; no hardware evidence and no operating conditions exist.
[placement evidence] Six placements of one block on one device, one run each (Vivado's placer has no seed). Relocation by a clock region leaves every interconnect delay unchanged; half a region or another column does not (see the placement table in results/102_managed_pr/README.md).
[keep-out] The keep-out binds the agent's tools and constraints; Vivado's own placer fills free slices inside the supplier's pblock rectangle with owned logic.

## next_actions
1. A model-driven run on this project (the session here is a script).
2. Stage 3 of brief 102 integrates a real external open-licence block.

## open_questions
- Which tolerance should a project accept for relocated blocks? Zero passes only whole-clock-region moves.

## history
2026-11-19 102 pr=-: written for stage 2 of the managed-project brief
