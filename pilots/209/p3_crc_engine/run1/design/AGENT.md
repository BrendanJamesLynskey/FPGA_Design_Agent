# AGENT p3_crc_engine (fda-handover/1)
source: runs/20261125-102852-3fd4/p3_crc_engine/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261125-102852-3fd4/p3_crc_engine

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=crc32_top tool=Vivado 2026.1
agent_run=20261125-102852-3fd4 record=runs/20261125-102852-3fd4/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 8 loops, 155 turns, 5,449,218 tokens, 1002 s wall time, 2.67122 USD model cost (provider-reported), stopped because: stage 2 visited more than 6 times; last failing gate: lint; owned by the rtl role; the same failure on 5 consecutive visits

## summary
The design computes a reflected CRC-32 (the zlib.crc32 variant) over bytes pushed through a JTAG-accessed register map (jtag_bus) on the KR260. A PUSH4 write consumes four bytes in one clock and a PUSH_N write consumes 1 to 3 tail bytes. The core also keeps byte and busy-cycle counters. The run stopped at the rtl-design-creation stage, whose lint gate failed on 5 consecutive visits. Nothing was synthesised, implemented or run on a board, and verification reached V2 of V3. The specification and architecture were approved automatically, with no human review.
not: Not a general CRC engine, the polynomial, init and final XOR are fixed to the Ethernet CRC-32 values in the RTL.; Not a streaming or AXI data path, data enters only through the single JTAG register port, one write per clock.; Not built, timed or tested on hardware, no Vivado build or board result exists.; Uses no GT transceiver, sfp_tx_disable is a constant output.

## state
stage=rtl vivado=2026.1 kb_pin=5e2eab8 build_id=798b2b70
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Internal and synchronous, not a board pin. crc32_rst_gen asserts it while the MMCM is unlocked and releases it through xpm_cdc_async_rst with 4 synchroniser stages.
if clk_25 input, 25 MHz board clock on pin C3 (LVCMOS18): Feeds the MMCM (x40 / 8) that makes the 125 MHz design clock. design.xdc defines the 40 ns period on this port.
if led output, 2 bits, F8 and E8 (LVCMOS18): led[0] is the MMCM lock, led[1] is bit 24 of a free-running heartbeat counter.
if sfp_tx_disable output, 1 bit, Y10 (LVCMOS33): Driven 1 at all times in crc32_top.sv.
if h_we, h_re, h_addr, h_wdata, h_rdata register port, 1, 1, 12, 32 and 32 bits: The spec calls these internal, but crc32_top.sv exposes them as top-level outputs. They link jtag_bus and crc32_core, and h_rdata is driven by the core.
reg 0 ID RO reset=546504705 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 scratch
reg 16 CTRL RW reset=0 0 INIT self-clearing; 31:1 reserved
reg 20 PUSH4 WO reset=0 31:0 four data bytes
reg 24 PUSH_N WO reset=0 31:0 data, low TAIL_LEN bytes used
reg 28 TAIL_LEN RW reset=0 1:0 N 0 to 3
reg 32 CRC RO reset=0 31:0 finalised CRC-32
reg 36 BYTE_COUNT RO reset=0 31:0 bytes pushed
reg 40 BUSY_CYCLES RO reset=0 31:0 busy clocks
param DESIGN_ID=546,504,705 legal=any 32-bit value, spec value 0x20930001
param CRC_POLY=79,764,919 legal=fixed at 0x04C11DB7
param CRC_INIT=4,294,967,295 legal=any 32-bit value, spec value 0xFFFFFFFF
param CRC_XOROUT=4,294,967,295 legal=any 32-bit value, spec value 0xFFFFFFFF
param DATA_BYTES_PER_CLK=4 legal=4 only
param TAIL_LEN_MAX=3 legal=3 only
param READ_LATENCY_CYCLES=1 legal=1 (the spec limit is 2)
param CLK_FREQ_CYCLES=1 legal=1 only

## files (paths under the design directory are relative to it)
spec.md 7848f58263: the request the run started from
spec.yaml 17c9b80fba: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md 4c3e7f0119: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 7f39dda9c7: the machine-checked architecture: blocks, clocks, predicted resources
rtl/crc32_core.sv 9a521a1fb5: RTL written by the Designer
rtl/crc32_rst_gen.sv 9b08da3fa4: RTL written by the Designer
rtl/crc32_top.sv 301dfabce0: RTL written by the Designer
rtl/xilinx_sim_stubs.sv 8e68a49ab0: RTL written by the Designer
design.xdc 5e9d053506: pin, I/O standard and timing constraints
build.yaml 257c3bdde5: the build description read by the flow
model.py 6288fe9c6d: the Modeller's reference model of the visible behaviour
tests/crc_bench.py 3f24f75070: the Verifier's cocotb benches and pytest entries
tests/test_p3_crc_engine_rtl.py b6d6f04981: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml e773c60a83: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/02_rtl-design-creation.html bac3a669c6: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261125-102852-3fd4/p3_crc_engine
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261125-102852-3fd4/p3_crc_engine "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261125-102852-3fd4/p3_crc_engine/tests/test_p3_crc_engine_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261125-102852-3fd4/p3_crc_engine/build/verif/sim python -m pytest -q -x runs/20261125-102852-3fd4/p3_crc_engine/tests/test_p3_crc_engine_rtl.py && python3 flow/verif_gates.py runs/20261125-102852-3fd4/p3_crc_engine --runs runs/20261125-102852-3fd4/p3_crc_engine/build/verif/sim
[heavy] rebuild the bitstream with the flow: flow/run_vivado.sh runs/20261125-102852-3fd4/p3_crc_engine base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261125-102852-3fd4/summary.json 508857e7a6
R2 build/verif/verif_gates.json ec15875c96

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 70); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=2.67122 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-02, REQ-07, REQ-12, REQ-13, REQ-14, REQ-24] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-11, REQ-23] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is pending: no flow gates result
[REQ-18, REQ-19, REQ-20] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: lint not passing FAIL rtl: did not run (no gates record) FAIL
[constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: lint; owned by the rtl role; the same failure on 5 consecutive visits)
[formal] formal checks were planned for REQ-09, REQ-21, REQ-22, REQ-15, REQ-25, REQ-16, REQ-26, REQ-18 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here so INIT is checked by directed simulation against the model.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[cover_vs_functional] Functional bins and cover properties both read 0 of 0 in verif_gates.json, so no coverage was gathered. Line, toggle and mutation results are not measured.
[crc_empty_read] In crc32_core.sv the CRC register reads 0 whenever BYTE_COUNT is 0, not only for an empty message. After INIT, or after a PUSH_N with TAIL_LEN 0, it reads 0 instead of the finalised state. A 4 GiB wrap of BYTE_COUNT back to 0 would also read 0.
[init_priority] INIT wins over a push in the same clock (crc32_core.sv). Only one register write happens per clock, so the two cannot coincide on the register port.
[unmapped_and_ro_access] Reads of unmapped addresses return 0, including 0x00C, 0x014, 0x018 and above 0x028, so PUSH4 and PUSH_N read 0. Writes to RO registers do nothing. CTRL always reads 0.
[tail_len_write] TAIL_LEN stores only bits 1:0 of the write. A PUSH_N uses the value stored before that clock.
[push_latency] A write updates the CRC, counters, SCRATCH and TAIL_LEN on the next clock edge, 1 clock after h_we. A read loads h_rdata 1 clock after h_re and holds it until the next h_re, and reset clears it to 0. jtag_bus delay is not counted.
[busy_cycles] BUSY_CYCLES adds 1 per push with at least 1 byte, and PUSH_N with TAIL_LEN 0 adds nothing. Counters are 32 bits and wrap.
[build_register] In simulation the USR_ACCESSE2 stub gives BUILD = 0, so the BUILD value (REQ-13) can only be checked on hardware.
[spec_vs_rtl_ports] spec.yaml lists h_we, h_re, h_addr, h_wdata and h_rdata as internal, but crc32_top.sv declares them as top-level outputs. design.xdc has no pins for them. This disagreement is unresolved and may block implementation.
[spec_vs_rtl_core_params] crc32_core.sv takes only DESIGN_ID, CRC_INIT and CRC_XOROUT as parameters. CRC_POLY, DATA_BYTES_PER_CLK, TAIL_LEN_MAX, READ_LATENCY_CYCLES and CLK_FREQ_CYCLES are not RTL parameters.
[jtag_bus_source] The spec assumes jtag_bus.sv was not visible, so its port names follow the request. It is not among the listed files, and the lint failure may involve it.

## next_actions
1. Fix the lint failure of rtl-design-creation first. Read the review page build/review/02_rtl-design-creation.html for the failing rule, and check the jtag_bus instance and the h_* ports in crc32_top.sv.
2. Decide whether h_we, h_re, h_addr, h_wdata and h_rdata stay as top-level outputs, and update crc32_top.sv, design.xdc or spec.yaml so they agree.
3. Decide whether CRC must read 0 only for an empty message, and change the BYTE_COUNT test in crc32_core.sv or the spec.
4. Compare the cover results with the functional coverage before any new stimulus, then re-run the Verilator coverage command and the verification gates.
5. Resume with python -m agent resume to reach constraints, synthesis and implementation, then measure resources, timing (WNS at or above 0 ns) and power.
6. Run the hardware tests for the REQ items that have a hardware proof method.

## open_questions
- Should the CRC register read 0 only for an empty message, as the spec says, or whenever BYTE_COUNT is 0, as the RTL does?
- Should the register-port signals be top-level ports, given that the spec calls them internal?

## history
2026-11-25 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
