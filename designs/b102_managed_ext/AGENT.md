# AGENT b102_managed_ext (fda-handover/1)
source: designs/b102_managed_ext/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b102_managed_ext

## identity
kind=demonstration produced_by=human part=xck26-sfvc784-2LV-c board=Kria KR260 top=fcs_top tool=Vivado 2026.1

## summary
A KR260 self-test of an Ethernet FCS stage that integrates one real third-party block under a managed project (brief 102, stage 3). Alex Forencich's parallel CRC/LFSR (verilog-ethernet, MIT, commit 77320a9471d1) is vendored unmodified and frozen; our adapter (owned) adds the register, the restart and the enable around it; an owned sequencer sends a fixed sixteen-word frame and shows the verdict on an LED. project.yaml records the licence, the commit and the hash of every file of theirs, and the agent's tools refuse every route to edit them.
not: a 10G Ethernet FCS check; the block is instantiated at 16 data bits a clock, not the 64-bit word of the 96 design; a board design; it was not programmed, and the 161 MHz clock constraint is on the 25 MHz oscillator pin for a timing study

## state
stage=built vivado=2026.1 kb_pin=93d158c build_id=19e88489
gates: import_checks=pass build_2026_1=pass boundary_checks=pass

## interface
clk clk_25 161.13MHz
rst power-on counter active-high: a four-clock shift register in fcs_top holds every block in synchronous reset after configuration; there is no reset input
if lfsr block third-party combinational RTL module (data_in, state_in, data_out, state_out) at LFSR_WIDTH 32, DATA_WIDTH 16: the contract is in project.yaml; behaviour a user could guess wrong is in the header of rtl/crc32_d16.sv (register not complement, little-endian words, hold on en low, reset wins) and in the block's own header (CRC32 = Galois, bit-reverse, polynomial 04C11DB7, initial FFFFFFFF) doc=designs/b102_managed_ext/project.yaml
param N_WORDS=16 legal=at least 1; the sequencer counter is sized from it and the word function takes an eight-bit index
param EXPECT=0x79D3D43A legal=the CRC register value of the frame, from flow/managed_import.crc32_model

## files
designs/b102_managed_ext/project.yaml 5071ecb805: the managed-project manifest: ownership, contracts and the third-party provenance of the four components
designs/b102_managed_ext/rtl/fcs_top.sv 7665c80db9: top level, power-on reset and the LEDs (ours)
designs/b102_managed_ext/rtl/fcs_ctrl.sv 2e11253b3f: the owned sequencer and FCS verdict (ours)
designs/b102_managed_ext/rtl/crc32_d16.sv 441eb31ce2: the CRC adapter around the third-party block (ours)
designs/b102_managed_ext/third_party/verilog-ethernet/lfsr.v 5502c8203b: the third-party block, unmodified (theirs, MIT)
designs/b102_managed_ext/third_party/verilog-ethernet/COPYING 8ea57f9536: its licence text (theirs)
designs/b102_managed_ext/reference/crc32_d16.sv b240398dd1: our own specification of the adapter, written without the block (not in the build)
designs/b102_managed_ext/build.yaml 532bcd6ade: how flow/run_vivado.sh builds the design

## commands
import checks (provenance, upstream comparison, interface, simulation, planted fault, optional eqy); needs the OSS CAD Suite and a clone of the upstream (~1min): python3 flow/managed_rtl_import.py check designs/b102_managed_ext --upstream <clone of verilog-ethernet>
the scripted agent session on a scratch copy (run under pytest: the in-process access-gate bypass applies) (~1min): FDA_102_RECORD=1 python3 -m pytest -q flow/tests/test_102_stage3.py -k scripted
[heavy] build and run the gates (~5min): flow/run_vivado.sh designs/b102_managed_ext base

## records (path sha256-prefix; claims below cite R<n>)
R1 flow/tests/test_102_stage3.py 13b5a87cf3
R2 results/102_stage3/import_check.json ce5b4e0c7a
R3 results/102_stage3/demo_session.json 33a2ba1fa6
R4 results/102_stage3/boundary.json 387f78e286
R5 results/102_stage3/builds.json 9061eb9dc4

## evidence
E1 simulation pass R1 ci: provenance gaps, the licence rule, the tools refusing every route to the vendored block, the import checks and the scripted session
E2 simulation pass R2: each vendored file equals the recorded hash and the bytes at the upstream commit; the block matches a CRC-32 step model on 2,000 random vectors at each of 8, 16, 32 and 64 data bits; the adapter plus the block matches the register model; a planted fault in a copy of the block fails both
E3 review pass R3: the scripted session edits only the owned controller; its attempts on the vendored files, an out-of-scope file, the manifest and a build.yaml that drops the block are refused
E4 build pass R4: the build passes every gate on Vivado 2026.1 with the third-party block compiled in; the boundary CDC check finds no row on the adapter

## measured
M1 resources lut=64 LUT R5#build.lut: LUTs, whole design including the third-party block | routed build, Vivado 2026.1, xck26-sfvc784-2LV-c
M2 resources ff=49 FF R5#build.ff: flip-flops, whole design | routed build, Vivado 2026.1
M3 timing wns_ns=4.467 ns R5#build.wns_ns: worst setup slack at the 6.206 ns clock | routed, 161.13 MHz constraint on the 25 MHz pin
M4 timing whs_ns=0.062 ns R5#build.whs_ns: worst hold slack | routed, 6.206 ns clock
M5 power power_w=0.336 W R5#build.power_w: total on-chip power estimate | report_power after routing, vectorless, never run on a board

## gaps
[power] The estimate is vectorless at default toggle rates; this is a timing study that was never run on a board, so no power measurement is claimed.
[throughput] Not applicable beyond the clock; the block takes two bytes a clock by construction and no throughput measurement was made.
[width] The block is instantiated at sixteen data bits; the 10G design uses sixty-four. The block alone is simulated at 8, 16, 32 and 64 bits against a model, but only the 16-bit instance is built.
[board] Never programmed; no hardware evidence and no operating conditions exist.
[behaviour] The design has no reset input and one fixed frame; the verdict LED is sticky until the next configuration.
[upstream tests] The block's upstream tests (MyHDL co-simulations of the Ethernet modules that use it) were not run: they need MyHDL's Icarus plug-in built from source, which was not approved here.
[latency] Not measured on this design; the stage 1 demonstration measured the verdict latency, and the scripted session records only that the controller edit saves one clock in simulation (results/102_stage3/demo_session.json).

## next_actions
1. A model-driven run on this managed project (the scripted session tests the rules, not a model).
2. The recorded-demo intake (docs/demo_intake.md) can use the same provenance fields for a requester's block.

## history
2026-11-19 102 pr=-: written for stage 3 of the managed-project brief
