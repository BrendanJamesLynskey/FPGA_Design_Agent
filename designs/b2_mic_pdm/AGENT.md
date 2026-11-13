# AGENT b2_mic_pdm (fda-handover/1)
source: designs/b2_mic_pdm/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b2_mic_pdm

## identity
kind=board-selfcheck produced_by=human part=xc7a100tcsg324-1 board=Nexys A7-100T top=b2_mic_pdm_top tool=Vivado 2026.1

## summary
Clocks the Nexys A7's PDM microphone at 2.381 MHz and counts, over a window of PDM bits, how many bits were 1 and how many times the bit changed. The counts tell a live microphone (about half ones, frequent changes) from a dead one, a stuck data line or a missing clock. The test shell carries the registers, and `selfcheck.py` holds the on-board pass rule, written before any board run.
not: an audio path: nothing decimates or filters the PDM stream, so it says nothing about audio quality; an agent benchmark task; it was written by hand to prove the board inventory on hardware

## state
stage=board-verified vivado=2026.1 kb_pin=1fc7ed8 build_id=6b2ffe2b
gates: build_2026_1=pass board_selfcheck=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the board's reset button, synchronised by the test shell's reset synchroniser (assert asynchronous, release synchronous)
if UART register window test shell, 8N1 UART at 115200 baud: the design's six registers sit at shell addresses 0x80 to 0x85 (CTRL, STATUS, NBITS, ONES, CHANGES, INFO); the map is in the header of rtl/mic_regs.sv; other window addresses read 0 doc=shell/PROTOCOL.md
if PDM microphone M_CLK out, M_DATA in, M_LRSEL out (LVCMOS33): M_LRSEL is held low, so the microphone drives M_DATA after each falling edge of M_CLK; M_DATA is synchronised and sampled in the middle of the high half doc=boards/nexys_a7_100t/inventory.yaml
param HALF=21 legal=1 to 65535 (16-bit divider); the board value is 21

## files
designs/b2_mic_pdm/rtl/pdm_stats.sv a124aa465b: clock divider, sample point, ones and change counters
designs/b2_mic_pdm/rtl/mic_regs.sv 1d09870a80: the registers in the shell window, with the register map in its header
designs/b2_mic_pdm/rtl/b2_mic_pdm_top.sv b3c762d55a: board top (test shell plus the microphone block)
designs/b2_mic_pdm/design.xdc f7143b4809: pins, the 100 MHz clock and the false paths on the asynchronous inputs
designs/b2_mic_pdm/build.yaml e7a26514c4: how flow/run_vivado.sh builds the design
designs/b2_mic_pdm/selfcheck.py c9a191d1d5: the on-board check and its pass rule (docstring), pre-registered before any board run
designs/b2_mic_pdm/tests/test_mic_rtl.py a551fe6f8e: cocotb with Icarus Verilog against a microphone model (counts equal the bits sent; a stuck line)

## commands
simulate against the microphone model (~1min): python3 -m pytest -q designs/b2_mic_pdm/tests/test_mic_rtl.py
[heavy] build and run the gates (~4min): flow/run_vivado.sh designs/b2_mic_pdm base
power gate, program SRAM, self-check, three times (~2min): python3 flow/board_check.py designs/b2_mic_pdm --runs 3

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b2_mic_pdm/tests/test_mic_rtl.py a551fe6f8e
R2 results/vivado_2026_1_remeasure/b2_builds.json 2ab9aafe7a
R3 results/board_v2/b2_mic_pdm.json 3edbd92219

## evidence
E1 simulation pass R1 ci: register-level test against a microphone model; the ones and change counts equal the bits sent, and a stuck line counts as stuck
E2 build pass R2: whole-board build on Vivado 2026.1; every gate passes (built, not programmed)
E3 board pass x3 R3: three self-check runs on the board, from a clean committed tree; each passes the pre-registered rule in all three windows | cond: wall power; the power gate (report_power total and junction temperature against the 2.0 W and 85 C limits) passed before programming; XADC rails and die temperature were not read during these runs

## measured
M1 resources lut=481 LUT R2#builds.b2_mic_pdm.lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1, xc7a100tcsg324-1, including the test shell
M2 resources ff=421 FF R2#builds.b2_mic_pdm.ff: flip-flops, whole board design | routed whole-board build, Vivado 2026.1, including the test shell
M3 timing wns_ns=3.436 ns R2#builds.b2_mic_pdm.wns_ns: worst setup slack | routed, at the 100 MHz board clock
M4 timing whs_ns=0.16 ns R2#builds.b2_mic_pdm.whs_ns: worst hold slack | ditto
M5 power power_w=0.117 W R2#builds.b2_mic_pdm.power_w: total on-chip power estimate | report_power after routing, vectorless (default toggle rates), the board's thermal environment
M6 board -=0.5167 R3#results[0].steps.selfcheck.windows[0].ones_fraction: fraction of ones, first window of the first recorded run | room sound neither controlled nor recorded; M_LRSEL low, window of 1,048,576 bits; pass range 0.40 to 0.60
M7 board -=0.7377 R3#results[0].steps.selfcheck.windows[0].change_fraction: fraction of bit-to-bit changes, first window of the first recorded run | as M6; pass threshold 0.10

## gaps
[latency] Not measured. A window takes its length in M_CLK periods (1,048,576 bits is about 0.44 s at 2.381 MHz) by design; no record times it.
[throughput] Not applicable as a data path; the block reports two counts per window and has no streaming output.
[E3] The board runs used bitstreams built on the earlier Vivado release; the 2026.1 build (E2) has the same build stamp but was not programmed. Re-run the board check on a 2026.1 bitstream to close this.
[operating conditions] The board runs predate the 2026-11-11 rule; die temperature and the VCCINT, VCCAUX and VCCBRAM rails were not read from the XADC, so the runs cannot be shown to be inside the recommended operating conditions.
[behaviour] GO written while a window runs is ignored (pdm_stats.sv starts a window only when idle), but no test covers it; NBITS of 0 is taken as 1; reset clears the counts and DONE; reads of undefined window addresses return 0 with no error.
[audio] No decimation or audio measurement; the check proves the microphone and its pins are alive, not sound quality.

## next_actions
1. Re-run the board check on a Vivado 2026.1 bitstream with the XADC read at the start and end of each run.
2. Add a test for GO written while busy, and state that it is ignored in the register map header.
3. If an audio path is wanted, add a CIC decimator from ip_lib behind the counters rather than changing them.

## open_questions
- Should the self-check also record M_CLK's measured frequency from the board, rather than the design value?

## history
2026-10-31 04c pr=-: written with the board inventory, power budget and power gate; 3 of 3 board runs pass
2026-11-11 49 pr=-: rebuilt on Vivado 2026.1; every gate passes (not programmed)
2026-11-13 68 pr=-: handover written to the documentation standard
