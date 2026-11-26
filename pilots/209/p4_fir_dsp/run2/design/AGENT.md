# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261125-130418-8166/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261125-130418-8166/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=fir_top tool=Vivado 2026.1
agent_run=20261125-130418-8166 record=runs/20261125-130418-8166/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 7 loops, 107 turns, 3,813,241 tokens, 1555.5 s wall time, 3.46926 USD model cost (provider-reported), stopped because: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verification V2; owned by the rtl/tests role; last failing assertion: V2 seeds_run: no seeded results: read runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. ; the same failure on 6 consecutive visits

## summary
The design is a 32-tap symmetric FIR filter. It adds mirrored taps before 16 multiplications, takes input samples through an input FIFO and returns saturated 16-bit results through an output FIFO. A host drives it over a simple register port behind a JTAG bridge. The run stopped in rtl-design-creation, after the clarify and board-and-device-planning stages passed. Verification reached V1 of V3, no Vivado build was made, and nothing was measured on hardware.
not: Not a general FIR core. Coefficients come from data/coeffs.hex at build time and cannot be changed at run time.; Not an AXI4-Lite design. The host port is the h_we/h_re register port and no interface profile is declared.; Not a transceiver design. No GT channel is used and sfp_tx_disable is a constant output.; Not built, routed or run on a board. No bitstream was produced in this run.

## state
stage=spec vivado=2026.1 kb_pin=5e2eab8 build_id=None
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Per spec.yaml it is synchronous in each clock domain, held by a power-up counter in the clk_bus domain and released only after MMCM lock. The RTL was not shown in this review, so the reset style actually built is unchecked.
if clk_25 input clock, 25 MHz, pin C3, LVCMOS18: Board clock. It feeds the MMCM and is also the register bus clock (design.xdc, period 40.00 ns).
if led 2-bit output, F8 and E8, LVCMOS18: The spec proposes led[0] = BUSY and led[1] = MMCM locked. This is a default and not confirmed by hardware. design.xdc maps led[0] to F8 and led[1] to E8.
if sfp_tx_disable 1-bit output, Y10, LVCMOS33: Constant 1, which turns the laser off.
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESSE2 word
reg 8 SCRATCH RW reset=0 31:0 read back what was written
reg 16 CTRL RW reset=0 0 CLEAR self-clearing, 1 RUN self-clearing
reg 20 IN_PUSH WO reset=0 15:0 sample pushed
reg 24 OUT_POP RO reset=0 31 valid, 15:0 oldest output, read pops
reg 28 STATUS RO reset=0 0 BUSY, 15:4 input FIFO count, 31:20 output FIFO count
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs since CLEAR
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed since CLEAR
param NUM_TAPS=32 legal=32 only; the symmetric pre-add structure assumes it
param UNIQUE_COEFFS=16 legal=NUM_TAPS/2
param DATA_WIDTH=16 legal=16 only
param COEFF_WIDTH=16 legal=16 only
param FIFO_DEPTH=1024 legal=1024 as specified
param SHIFT=15 legal=15 only
param ROUND_CONST=16,384 legal=2^(SHIFT-1)
param ID_VALUE=546,570,241 legal=any 32-bit value
param SFP_TX_DISABLE_VALUE=1 legal=1 (laser off) as specified

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml 897d3845e6: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md c6722b3670: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 1257cfd9d6: the machine-checked architecture: blocks, clocks, predicted resources
design.xdc 713c2601ca: pin, I/O standard and timing constraints
model.py e90e272cde: the Modeller's reference model of the visible behaviour
tests/fir_bench.py 59d74d8410: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py d690761019: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 51ab3aafe2: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/02_rtl-design-creation.html ca2834af9a: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261125-130418-8166/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261125-130418-8166/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261125-130418-8166/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim python -m pytest -q -x runs/20261125-130418-8166/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py && python3 flow/verif_gates.py runs/20261125-130418-8166/p4_fir_dsp --runs runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim
[heavy] rebuild the bitstream with the flow: flow/run_vivado.sh runs/20261125-130418-8166/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261125-130418-8166/summary.json bf010155d5
R2 build/verif/verif_gates.json 48e0681209

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 7 questions, 0 answered and 7 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V1 of V3; the run asked for V2; V1 means every spec item is traced to a check and the benches use the blind model; V2 (simulation: seeded runs, a constrained-random test, bound assertions and formal tasks) did not pass: seeds run no seeded results: read runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. The flow's simulation step writes it when the bench runs through flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=N) in tests/test_*_rtl.py: call run() once per seed (for example seed=1, 2, 3; a seed left out counts as seed 1) with the module(s) listed in bench.modules; the flow runs it and checks again. A bench that runs the simulator some other way leaves nothing there. (needs >=1 seed); constrained random test ran not evaluated (no seeded results) (needs True); assertions bound zero failures not evaluated (no seeded results) (needs bound in the run; no failure); V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: seeds run no seeded results: read runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. The flow's simulation step writes it when the bench runs through flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=N) in tests/test_*_rtl.py: call run() once per seed (for example seed=1, 2, 3; a seed left out counts as seed 1) with the module(s) listed in bench.modules; the flow runs it and checks again. A bench that runs the simulator some other way leaves nothing there. (needs >=3); functional bins pct not evaluated (no seeded results) (needs 100); cover properties pct not evaluated (no seeded results) (needs 100); line pct not evaluated (no seeded results) (needs 90); toggle pct not evaluated (no seeded results) (needs 75); mutation score pct not measured (needs 80); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded

## measured
M1 cost -=3.46926 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-03] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_reset_and_id) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-02] REQ-02 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-37] REQ-37 has no passing evidence for every proof method: simulation (fir_bench.test_scratch_unmapped) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-04] REQ-04 has no passing evidence for every proof method: simulation (fir_bench.test_reset_and_id) is pending: no simulation results
[REQ-38] REQ-38 has no passing evidence for every proof method: simulation (fir_bench.test_scratch_unmapped) is pending: no simulation results
[REQ-05] REQ-05 has no passing evidence for every proof method: simulation (fir_bench.test_rdata_hold) is pending: no simulation results; formal (fir_bench.test_rdata_hold) is pending: re-planned from formal to simulation (SymbiYosys is not installed here so the read latency claim is checked by simulation.): no simulation results
[REQ-39] REQ-39 has no passing evidence for every proof method: simulation (fir_bench.test_rdata_hold) is pending: no simulation results; formal (fir_bench.test_rdata_hold) is pending: re-planned from formal to simulation (SymbiYosys is not installed here so the hold claim is checked by simulation.): no simulation results
[REQ-06, REQ-11, REQ-32] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_random_chunks) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-07] REQ-07 has no passing evidence for every proof method: simulation (fir_bench.test_impulse_unit) is pending: no simulation results
[REQ-08] REQ-08 has no passing evidence for every proof method: simulation (fir_bench.test_impulse) is pending: no simulation results
[REQ-09] REQ-09 has no passing evidence for every proof method: simulation (fir_bench.test_impulse) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-10] REQ-10 has no passing evidence for every proof method: simulation (fir_bench.test_step) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-12, REQ-13, REQ-16, REQ-34, REQ-35] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[REQ-14, REQ-24] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_busy_and_throughput) is pending: no simulation results
[REQ-15, REQ-44, REQ-36] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is pending: no flow gates result
[REQ-17, REQ-40, REQ-18, REQ-25, REQ-26] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_fifo_capacity) is pending: no simulation results
[REQ-19] REQ-19 has no passing evidence for every proof method: simulation (fir_bench.test_chunked_equals_single) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-20, REQ-27, REQ-28, REQ-29, REQ-42, REQ-30, REQ-43] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_control_clear_history) is pending: no simulation results
[REQ-21, REQ-23] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_chunked_equals_single) is pending: no simulation results
[REQ-22] REQ-22 has no passing evidence for every proof method: simulation (fir_bench.test_chunked_equals_single) is pending: no simulation results; formal (fir_bench.test_chunked_equals_single) is pending: re-planned from formal to simulation (SymbiYosys is not installed here so the OUT_POP format is checked by simulation.): no simulation results
[REQ-41] REQ-41 has no passing evidence for every proof method: simulation (fir_bench.test_chunked_equals_single) is pending: no simulation results; formal (fir_bench.test_chunked_equals_single) is pending: re-planned from formal to simulation (SymbiYosys is not installed here so pop removing the oldest is checked by simulation.): no simulation results
[REQ-31] REQ-31 has no passing evidence for every proof method: simulation (fir_bench.test_saturation) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-33] REQ-33 has no passing evidence for every proof method: formal (fir_bench.test_led_sfp) is pending: re-planned from formal to simulation (SymbiYosys is not installed here so the constant output is checked by simulation.): no simulation results; analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 7 questions, 0 answered and 7 defaulted
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: lint not passing FAIL simulate not passing FAIL standards STD-LATCH-01: not checked (no build.yaml top or sources to check) FAIL standards STD-LOOP-01: not checked (no build.yaml top or sources to check) FAIL standards STD-CDC-01: architecture.yaml:1: crossings[0]: inline_in fir_core is not a module of this design or the shell FAIL standards STD-CDC-01: architecture.yaml:1: crossings[1]: inline_in ...
[constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verification V2; owned by the rtl/tests role; last failing assertion: V2 seeds_run: no seeded results: read runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-130418-8166/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. ; the same failure on 6 consecutive visits)
[formal] formal checks were planned for REQ-05, REQ-39, REQ-22, REQ-41, REQ-33 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here so the read latency claim is checked by simulation.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[busy_behaviour] By interview defaults in spec.yaml, IN_PUSH and CLEAR are ignored while BUSY is 1, and a RUN during BUSY is ignored. OUT_POP works normally during BUSY. These come from the spec, not from checked RTL.
[clear_run_priority] By default in spec.yaml, if CLEAR and RUN are written in the same write, CLEAR wins and RUN is dropped. RUN on an empty input FIFO does nothing and BUSY stays 0.
[run_partial] By default in spec.yaml, RUN processes only min(input count, output free space) samples and leaves the rest in the input FIFO. It drops no outputs.
[unmapped_registers] Per spec.yaml, unmapped and reserved offsets read 0 and ignore writes. Writes to read-only registers are presumed ignored but the spec does not say so.
[counter_width] SAT_COUNT and SAMPLES_DONE are 32-bit counters that wrap at 2^32 (spec default). The STATUS FIFO count fields are 12 bits and a full FIFO reads 1,024.
[latency_count] The spec expects a filter pipeline of about 8 clk_dsp cycles and leaves it to the design. The count was not taken from the RTL in this review, so the real figure is unknown. Bus read latency is specified as at most 2 clk_bus cycles and was not simulated.
[architecture_crossings] The standards gate reports that architecture.yaml names inline_in fir_core, which is not a module of this design or the shell. This is a mismatch between architecture.yaml and the RTL and must be fixed before the CDC checks can run.
[assumptions] The run assumed the bus runs on clk_25 directly, BUILD (USR_ACCESSE2) is not simulated, jtag_bus.sv is used unchanged and excluded from simulation, and the coefficients are loaded by $readmemh of data/coeffs.hex.
[pin_voltage] design.xdc puts sfp_tx_disable on Y10 at LVCMOS33 and the other pins at LVCMOS18. design.xdc defines only the clk_25 clock (40.00 ns). The 250 MHz clk_dsp period is not constrained there and depends on the MMCM being derived.

## next_actions
1. Fix the verification stage first: make the benches call flow.cocotb_run.run() once per seed (seeds 1, 2, 3) so that seeded results exist under build/verif/sim, then re-run the verification gates.
2. Fix lint, simulate and the design-standards failures in rtl-design-creation, including the architecture.yaml inline_in fir_core crossing entries.
3. Compare the cover results with the functional coverage once seeded results exist, before adding any new stimulus.
4. When the flow reaches the build again, run synthesis, implementation and timing closure, and check the 250 MHz clk_dsp target and the 16 DSP48E2 count against the reports.
5. Run the hardware bring-up for the requirements that list hardware proof (ID, BUILD, SCRATCH, impulse, step, random chunks).

## open_questions
- Should the design stay with the defaults the interview produced (BUSY blocking, CLEAR priority, LED meaning), since no human answered the interview?
- What is the real filter pipeline latency in clk_dsp cycles, to be counted from the RTL once it passes lint?

## history
2026-11-25 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
