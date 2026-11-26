# AGENT p5_async_fifo (fda-handover/1)
source: runs/20261125-233045-dfe1/p5_async_fifo/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261125-233045-dfe1/p5_async_fifo

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=p5_async_fifo_soak tool=Vivado 2026.1
agent_run=20261125-233045-dfe1 record=runs/20261125-233045-dfe1/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 11 loops, 300 turns, 13,569,382 tokens, 6165.3 s wall time, 9.24096 USD model cost (provider-reported), stopped because: budget: run turns limit 300 reached (300)

## summary
The design writes PRBS-31 words from a 25 MHz writer domain (clk_c3) into an asynchronous 32-bit FIFO and reads and checks them in a 156.25 MHz reader domain (clk_gt156, from the SFP+ MGTREFCLK0 buffer, no GT channel). Counters for words, errors, overflow, underflow, stalls and peak fill are read over the jtag_bus register port. The run reached V2 of V3 in verification and stopped at the constraints stage, where the Vivado post-synthesis exception check failed on an invalid site name; no bitstream, timing, power or hardware result exists.
not: Not a transceiver design. No GT channel is used, only the reference clock buffer, and SFP+ TX is held disabled.; Not a throughput or latency measurement. Neither was measured in this run.; Not hardware-verified. No board result is recorded.

## state
stage=simulated vivado=2026.1 kb_pin=6185830 build_id=6e2a48db
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=pass constraints=fail synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_c3 25MHz
clk gt_refclk_p 156.25MHz
rst rst active-high: Internal power-up generator in clk_c3 (rtl/p5_async_fifo_soak.sv), held for RESET_HOLD_CYCLES clocks, no pin. It reaches clk_gt156 through xpm_cdc_async_rst.
if clk_c3 input clock, 25 MHz, pin C3 (LVCMOS18): Writer clock and register-bus clock.
if gt_refclk_p / gt_refclk_n differential input clock, SFP+ MGTREFCLK0, 156.25 MHz: Enters an IBUFDS_GTE4; its ODIV2 output drives a BUFG_GT that clocks the reader.
if led[1:0] output, pins F8 and E8 (LVCMOS18): led[0] is RUN; led[1] is set when a snapshotted DATA_ERRS, OVERFLOWS or UNDERFLOWS is non-zero.
if sfp_tx_disable output, pin Y10 (LVCMOS33): Constant 1.
if h_we / h_re / h_addr / h_wdata / h_rdata internal register port (no pins), clk_c3: In the top these ports are declared but the live port is wired internally to jtag_bus; h_we, h_re, h_addr and h_wdata are unused there.
reg 0 ID RO reset=546635777 [31:0] design ID
reg 4 BUILD RO reset=0 [31:0] USR_ACCESS word
reg 8 SCRATCH RW reset=0 [31:0] scratch
reg 16 CTRL RW reset=0 [0] RUN, [1] SLOW_READ, [2] CLEAR self-clearing only while RUN=0, [3] INJECT self-clearing
reg 20 WORDS_W RO reset=0 [31:0] words written (snapshot)
reg 24 WORDS_R RO reset=0 [31:0] words read and checked (snapshot)
reg 28 DATA_ERRS RO reset=0 [31:0] mismatching words (snapshot)
reg 32 OVERFLOWS RO reset=0 [31:0] writes while full (snapshot)
reg 36 UNDERFLOWS RO reset=0 [31:0] reads while empty (snapshot)
reg 40 STALL_W RO reset=0 [31:0] writer clocks held off (snapshot)
reg 44 OCC_MAX RO reset=0 [31:0] highest fill in words (snapshot)
reg 48 SNAPSHOT WO reset=0 any write latches 0x014 to 0x02C; reads 0
param FIFO_DEPTH_WORDS=512 legal=512 only as built
param DATA_WIDTH=32 legal=32 only
param PRBS_SEED=2,147,483,647 legal=non-zero 31-bit value
param DESIGN_ID=546,635,777 legal=any 32-bit value
param SLOW_READ_PERIOD_CYCLES=8 legal=2 to 16 (the slow counter is 4 bits)
param COUNTER_WIDTH=32 legal=32 only
param RESET_HOLD_CYCLES=8 legal=0 to 31 (5-bit hold counter)

## files (paths under the design directory are relative to it)
spec.md feff955150: the request the run started from
spec.yaml 9062cca5bf: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md a39e95b4af: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml d555ab5615: the machine-checked architecture: blocks, clocks, predicted resources
rtl/p5_async_fifo_soak.sv e57f914d38: RTL written by the Designer
rtl/prbs31_word.sv 9c0d78ee91: RTL written by the Designer
rtl/soak_core.sv d63fb09c75: RTL written by the Designer
rtl/soak_fifo.sv ae0dd943f3: RTL written by the Designer
rtl/soak_reader.sv 2daeb8dd18: RTL written by the Designer
rtl/xilinx_sim_stubs.sv 6ff63deef2: RTL written by the Designer
rtl/zz_lint_waive.sv 875d04163e: RTL written by the Designer
design.xdc 1901951723: pin, I/O standard and timing constraints
build.yaml 37745bf6e2: the build description read by the flow
model.py 5b88b21901: the Modeller's reference model of the visible behaviour
tests/bench_p5_async_fifo.py db4b0826a8: the Verifier's cocotb benches and pytest entries
tests/test_p5_async_fifo_rtl.py 71ac30be07: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 2a5fe7716f: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/03_constraints.html 86dd988ba4: the review page of stage constraints: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261125-233045-dfe1/p5_async_fifo
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261125-233045-dfe1/p5_async_fifo "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261125-233045-dfe1/p5_async_fifo/tests/test_p5_async_fifo_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261125-233045-dfe1/p5_async_fifo/build/verif/sim python -m pytest -q -x runs/20261125-233045-dfe1/p5_async_fifo/tests/test_p5_async_fifo_rtl.py && python3 flow/verif_gates.py runs/20261125-233045-dfe1/p5_async_fifo --runs runs/20261125-233045-dfe1/p5_async_fifo/build/verif/sim
[heavy] rebuild the bitstream with the flow (~2.3min): flow/run_vivado.sh runs/20261125-233045-dfe1/p5_async_fifo base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261125-233045-dfe1/summary.json a177c1e23e
R2 build/verif/verif_gates.json 93a42aee7d
R3 build/base/gates.json eb96806242

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 70); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build fail R3: Vivado base build; flow stages that ran: rtl, post_synth

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=9.24096 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-02, REQ-03, REQ-11, REQ-36, REQ-12, REQ-35, REQ-16, REQ-18, REQ-19, REQ-20] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-08, REQ-24] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[REQ-21] REQ-21 has no passing evidence for every proof method: hardware (ila_captures) is pending: no bring-up result
[REQ-23] REQ-23 has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result; hardware (uart_tests) is pending: no bring-up result
[REQ-25, REQ-34, REQ-26, REQ-37, REQ-27, REQ-28] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is pending: no flow gates result
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
[E3] build evidence is fail: Vivado base build; flow stages that ran: rtl, post_synth
[constraints] stage constraints did not pass its gates in this run; at its last visit: post_synth:post_synth_methodology_no_critical FAIL post_synth:post_synth_exceptions_clean (EXC-XDC-MSG design.xdc:21 set_property LOC IBUFDS_GTE4_X0Y1 [get_cells { u_ibufds_gt }] Command failed: 'IBUFDS_GTE4_X0Y1' is not a valid site name.) FAIL
[synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (budget: run turns limit 300 reached (300))
[formal] formal checks were planned for REQ-18, REQ-19, REQ-27 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed, so the no-overflow property is shown in simulation with the FIFO driven full, and by the hardware soak.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[fifo_depth] soak_fifo.sv instantiates xpm_fifo_async with depth 512 passed in, but its file comment says 1024 x 32 in one RAMB36 and the macro uses FIFO_MEMORY_TYPE distributed, while the spec and ARCHITECTURE.md say one BRAM. The 512-word claim (REQ-08) is not confirmed by a Vivado build.
[xdc_site] design.xdc as built has LOC IBUFDS_GTE4_X0Y0 at line 21 (its comment names X0Y0), but the failing check quotes X0Y1 as an invalid site name. The XDC and the check disagree; re-run to confirm which site Vivado accepts.
[spec_vs_rtl_registers] The RTL read mux (soak_core.sv) returns 0 for unmapped addresses, including 0x030 SNAPSHOT, and writes to unmapped addresses change nothing. CTRL reads back only RUN and SLOW_READ; CLEAR and INJECT always read 0.
[clear_priority] CLEAR is honoured only if written while RUN is 0 (clr_req = write to CTRL with bit 2, and not run). The same write can set RUN, but the test uses the old RUN value. CLEAR also holds the FIFO in reset for 8 clk_c3 clocks, and the writer is blocked meanwhile.
[counters_run_gated] Stall, overflow and OCC_MAX counting is gated by RUN and by the FIFO not being in reset. The reader counts words read independently of RUN.
[snapshot_latency] A write to 0x030 does not latch at once. The request is delayed about 50 clocks (64 for the first snapshot after reset) and aligned to an 8-clock grid, then crosses through a handshake, so the snapshot registers update tens of clocks after the write. Reading too soon returns the previous snapshot. The spec does not state this delay.
[read_latency] h_rdata is registered in soak_core.sv, so it updates one clk_c3 clock after h_re, inside the spec's 2-clock promise, and holds until the next h_re. The jtag_bus latency was not counted here.
[build_stamp] In simulation USR_ACCESSE2 is a stub returning 0, so BUILD is 0 in the benches; only hardware shows the real word.
[sim_stubs] The benches use behavioural models of the Xilinx primitives and XPM macros (rtl/xilinx_sim_stubs.sv); their timing is not the real macros' timing.

## next_actions
1. Compare the cover results with the functional coverage (functional bins 0 of 0 and cover properties 0 percent are recorded) before any new stimulus, then run the coverage, CDC and mutation checks that did not run to reach V3.
2. Resolve the IBUFDS_GTE4 LOC in design.xdc (the failing check names X0Y1 as an invalid site while the file shows X0Y0) and re-run the base build with flow/run_vivado.sh.
3. Resolve the FIFO memory type and depth mismatch in soak_fifo.sv against the spec's one-BRAM expectation.
4. Continue through synthesis, implementation, timing, power and DRC closure, then bring up on the KR260 for the hardware proofs.

## open_questions
- Should the snapshot delay of about 50 to 64 clocks be kept, or should the snapshot latch sooner?
- Is distributed memory acceptable for the FIFO, or must it use one block RAM as the spec says?

## history
2026-11-25 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning, rtl-design-creation
