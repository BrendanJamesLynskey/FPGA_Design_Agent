# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261125-122959-66c4/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261125-122959-66c4/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=p4_fir32_top tool=Vivado 2026.1
agent_run=20261125-122959-66c4 record=runs/20261125-122959-66c4/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 8 loops, 98 turns, 3,619,268 tokens, 1724.1 s wall time, 3.88835 USD model cost (provider-reported), stopped because: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verification V2; owned by the rtl/tests role; last failing assertion: V2 seeds_run: no seeded results: read runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. ; the same failure on 6 consecutive visits

## summary
The design is a 32-tap symmetric low-pass FIR filter (Q1.15 coefficients, 16 unique, pre-adder plus 16 DSP multipliers) for the KR260. It has 1024-sample input and output FIFOs and is controlled through a 32-bit register port fed by jtag_bus. The run stopped at rtl-design-creation after clarify and board-and-device-planning passed. Simulation produced no seeded results, verification reached V1 of V3, and no Vivado build was made. The specification and architecture were approved automatically, with no human review.
not: Not built or measured on hardware; no synthesis, implementation, timing, power or bitstream result exists from this run.; Not an AXI4-Lite design; the host port is the simple h_* register port.; Does not use any GT transceiver channel; sfp_tx_disable is a static output.; jtag_bus.sv is not part of the simulation; it is used unchanged and contains Xilinx primitives.

## state
stage=spec vivado=2026.1 kb_pin=5e2eab8 build_id=None
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Comes from jtag_bus, not a board pin. The spec says it is synchronised into clk_dsp and the datapath uses synchronous reset; that was not checked against the RTL here. CLEAR also resets FIFOs, history and counters.
if clk input clock, 25 MHz board clock on pin C3: The spec calls this port clk; design.xdc constrains a port named clk_25 with a 40 ns period (see gap).
if led output, 2 bits: design.xdc puts led[0] on F8 and led[1] on E8, LVCMOS18. Per spec, led[0] is BUSY and led[1] is MMCM lock.
if sfp_tx_disable output, 1 bit: design.xdc puts it on Y10, LVCMOS33. Spec requires it to be 1 at all times.
if h_we, h_re, h_addr, h_wdata, h_rdata internal register port to jtag_bus (1, 1, 12, 32, 32 bits): Not board pins. h_addr is a byte address and the port runs on the 25 MHz clock.
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESSE2 word
reg 8 SCRATCH RW reset=0 31:0 scratch
reg 16 CTRL RW reset=0 0 CLEAR self-clearing, 1 RUN self-clearing
reg 20 IN_PUSH WO reset=0 15:0 sample to push
reg 24 OUT_POP RO reset=0 31 valid, 15:0 oldest output, read pops
reg 28 STATUS RO reset=0 0 BUSY, 15:4 input FIFO count, 31:20 output FIFO count
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs since CLEAR
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed since CLEAR
param NUM_TAPS=32 legal=32 only; the pre-adder structure assumes 2 x UNIQUE_COEFFS
param UNIQUE_COEFFS=16 legal=NUM_TAPS / 2
param DATA_WIDTH=16 legal=16 only; the register fields are fixed at 16 bits
param COEFF_WIDTH=16 legal=16 only (signed Q1.15)
param FIFO_DEPTH=1024 legal=1024; the STATUS count fields are 12 bits wide
param ACC_WIDTH=38 legal=at least 37 bits
param SHIFT=15 legal=15 for Q1.15
param ROUND_CONST=16,384 legal=2^(SHIFT-1)
param DESIGN_ID=546,570,241 legal=any 32-bit value
param MMCM_MULT=10 legal=must keep the MMCM VCO in range
param MMCM_DIV=1 legal=1 or more, keeping clk_dsp at 250 MHz or faster

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml f90461a6af: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md 3a9b1f4f41: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 150b606043: the machine-checked architecture: blocks, clocks, predicted resources
design.xdc 713c2601ca: pin, I/O standard and timing constraints
model.py f049ffb571: the Modeller's reference model of the visible behaviour
tests/p4_fir_bench.py 720c4b3e9e: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py 88ec05fe9a: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 85f458be25: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/02_rtl-design-creation.html 7b4cf2aa6e: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261125-122959-66c4/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261125-122959-66c4/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261125-122959-66c4/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim python -m pytest -q -x runs/20261125-122959-66c4/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py && python3 flow/verif_gates.py runs/20261125-122959-66c4/p4_fir_dsp --runs runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim
[heavy] rebuild the bitstream with the flow: flow/run_vivado.sh runs/20261125-122959-66c4/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261125-122959-66c4/summary.json 87c7ff3c95
R2 build/verif/verif_gates.json a7d191c843

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 9 questions, 0 answered and 9 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V1 of V3; the run asked for V2; V1 means every spec item is traced to a check and the benches use the blind model; V2 (simulation: seeded runs, a constrained-random test, bound assertions and formal tasks) did not pass: seeds run no seeded results: read runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. The flow's simulation step writes it when the bench runs through flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=N) in tests/test_*_rtl.py: call run() once per seed (for example seed=1, 2, 3; a seed left out counts as seed 1) with the module(s) listed in bench.modules; the flow runs it and checks again. A bench that runs the simulator some other way leaves nothing there. (needs >=1 seed); constrained random test ran not evaluated (no seeded results) (needs True); assertions bound zero failures not evaluated (no seeded results) (needs bound in the run; no failure); V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: seeds run no seeded results: read runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. The flow's simulation step writes it when the bench runs through flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=N) in tests/test_*_rtl.py: call run() once per seed (for example seed=1, 2, 3; a seed left out counts as seed 1) with the module(s) listed in bench.modules; the flow runs it and checks again. A bench that runs the simulator some other way leaves nothing there. (needs >=3); functional bins pct not evaluated (no seeded results) (needs 100); cover properties pct not evaluated (no seeded results) (needs 100); line pct not evaluated (no seeded results) (needs 90); toggle pct not evaluated (no seeded results) (needs 75); mutation score pct not measured (needs 80); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded

## measured
M1 cost -=3.88835 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-03, REQ-37] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_smoke_reset_id_scratch) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-02] REQ-02 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-04, REQ-05] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_unmapped) is pending: no simulation results
[REQ-06] REQ-06 has no passing evidence for every proof method: simulation (p4_fir_bench.test_read_latency_hold) is pending: no simulation results; formal (p4_fir_bench.test_read_latency_hold) is pending: re-planned from formal to simulation (SymbiYosys is not installed here, so the read latency is checked in simulation.): no simulation results
[REQ-07] REQ-07 has no passing evidence for every proof method: simulation (p4_fir_bench.test_random_register_traffic) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-08, REQ-11] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_impulse) is pending: no simulation results
[REQ-09] REQ-09 has no passing evidence for every proof method: simulation (p4_fir_bench.test_step) is pending: no simulation results
[REQ-10, REQ-23] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_random_chunks_10x1000) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-12, REQ-27, REQ-28, REQ-29] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_clear) is pending: no simulation results
[REQ-13, REQ-24] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_busy_and_throughput) is pending: no simulation results
[REQ-14, REQ-17, REQ-33] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is pending: no flow gates result
[REQ-15, REQ-16, REQ-35, REQ-36] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[REQ-18] REQ-18 has no passing evidence for every proof method: simulation (p4_fir_bench.test_input_fifo_full) is pending: no simulation results; formal (p4_fir_bench.test_input_fifo_full) is pending: re-planned from formal to simulation (SymbiYosys is not installed here, so the 1024 depth is checked by filling the FIFO in simulation.): no simulation results
[REQ-19] REQ-19 has no passing evidence for every proof method: simulation (p4_fir_bench.test_input_fifo_full) is pending: no simulation results; formal (p4_fir_bench.test_input_fifo_full) is pending: re-planned from formal to simulation (SymbiYosys is not installed here, so the full-FIFO push is checked in simulation.): no simulation results
[REQ-20, REQ-26] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_output_fifo_full_stall) is pending: no simulation results
[REQ-21] REQ-21 has no passing evidence for every proof method: simulation (p4_fir_bench.test_pop_empty_and_valid) is pending: no simulation results; formal (p4_fir_bench.test_pop_empty_and_valid) is pending: re-planned from formal to simulation (SymbiYosys is not installed here, so OUT_POP behaviour is checked in simulation.): no simulation results
[REQ-22] REQ-22 has no passing evidence for every proof method: simulation (p4_fir_bench.test_pop_empty_and_valid) is pending: no simulation results
[REQ-25] REQ-25 has no passing evidence for every proof method: simulation (p4_fir_bench.test_input_fifo_full) is pending: no simulation results
[REQ-30, REQ-39] (each of these) has no passing evidence for every proof method: simulation (p4_fir_bench.test_write_latency_ctrl_selfclear) is pending: no simulation results
[REQ-31] REQ-31 has no passing evidence for every proof method: simulation (p4_fir_bench.test_saturation) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-32] REQ-32 has no passing evidence for every proof method: simulation (p4_fir_bench.test_saturation) is pending: no simulation results
[REQ-34] REQ-34 has no passing evidence for every proof method: simulation (p4_fir_bench.test_sfp_tx_disable) is pending: no simulation results; formal (p4_fir_bench.test_sfp_tx_disable) is pending: re-planned from formal to simulation (SymbiYosys is not installed here, so the constant-1 output is checked in simulation under random traffic and reset.): no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-38] REQ-38 has no passing evidence for every proof method: simulation (p4_fir_bench.test_read_latency_hold) is pending: no simulation results; formal (p4_fir_bench.test_read_latency_hold) is pending: re-planned from formal to simulation (SymbiYosys is not installed here, so h_rdata hold is checked in simulation.): no simulation results
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 9 questions, 0 answered and 9 defaulted
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: lint not passing FAIL simulate not passing FAIL standards STD-LATCH-01: not checked (no build.yaml top or sources to check) FAIL standards STD-LOOP-01: not checked (no build.yaml top or sources to check) FAIL standards STD-CDC-01: architecture.yaml:1: crossings[0]: inline_in fir_regs is not a module of this design or the shell FAIL standards STD-CDC-01: architecture.yaml:1: crossings[1]: inline_in ...
[constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verification V2; owned by the rtl/tests role; last failing assertion: V2 seeds_run: no seeded results: read runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-122959-66c4/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. ; the same failure on 6 consecutive visits)
[formal] formal checks were planned for REQ-06, REQ-18, REQ-19, REQ-21, REQ-34, REQ-38 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here, so the read latency is checked in simulation.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[clock_port_name] spec.yaml names the clock port clk, but design.xdc constrains a port named clk_25 (pin C3, 40 ns period, LVCMOS18). The XDC is what was built; the spec disagrees. The spec's clk_dsp (250 MHz from the MMCM) has no constraint in design.xdc and is not listed as a clock in this handover.
[spec_vs_rtl_unchecked] The RTL sources were not shown to the Designer for this handover, so reset style, reset values, unmapped accesses and the read and write latencies are given as the spec states them. They are not confirmed from the RTL; the benches that would check them produced no results.
[defaulted_behaviour] All 9 interview answers were defaulted, not given by a person. Behaviours a user could guess wrong: CLEAR wins over RUN when both are written together; RUN while BUSY is ignored; CTRL reads 0 because both bits self-clear; a read of OUT_POP on an empty FIFO returns 0 with no side effect; IN_PUSH while full is ignored; IN_PUSH during a run may or may not be processed in that run; the datapath stalls when the output FIFO is full so no result is lost; SAT_COUNT and SAMPLES_DONE are 32 bits and wrap at 2^32; unmapped addresses read 0 and ignore writes.
[latency_promise] The spec promises h_rdata within 2 clk cycles of h_re, writes effective 1 clk cycle after h_we, and a filter pipeline of about 6 to 8 clk_dsp cycles. None of these was counted from the RTL here.
[architecture_crossings] The standards gate reports architecture.yaml crossings that name inline_in fir_regs, which is not a module of the design or the shell. The CDC description in architecture.yaml needs to match the real module names.

## next_actions
1. Fix the earliest failing stage, rtl-design-creation: first make the benches run through flow.cocotb_run.run(...) once per seed (seed 1, 2, 3) so that seeded results.xml files exist under build/verif/sim, then clear the lint, simulate and STD-CDC-01 failures listed on the review page.
2. Correct the crossings in architecture.yaml so inline_in names a real module, and rerun the design standards check.
3. Re-run the Verilator coverage command and flow/verif_gates.py. If cover properties are unhit while functional bins are hit, compare the cover results with the functional coverage before adding any new stimulus.
4. Reconcile the clock port name between spec.yaml (clk) and design.xdc (clk_25), and add a clk_dsp constraint.
5. Once verification passes, resume with python -m agent resume to run constraints, synthesis and implementation, then record resources, timing at 250 MHz and power.

## open_questions
- Should the spec or the XDC change to settle the clock port name (clk or clk_25)?
- Should the formal checks be restored if SymbiYosys becomes available, or stay as simulation checks?

## history
2026-11-25 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
