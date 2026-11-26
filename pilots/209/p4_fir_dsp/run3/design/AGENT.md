# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261125-133549-a1e9/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261125-133549-a1e9/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=fir32_top tool=Vivado 2026.1
agent_run=20261125-133549-a1e9 record=runs/20261125-133549-a1e9/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 8 loops, 89 turns, 2,782,739 tokens, 1343.9 s wall time, 3.10723 USD model cost (provider-reported), stopped because: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verification V2; owned by the rtl/tests role; last failing assertion: V2 seeds_run: no seeded results: read runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. ; the same failure on 6 consecutive visits

## summary
The design is a 32-tap symmetric FIR filter on the KR260. It is meant to use 16 DSP multipliers at 250 MHz from an MMCM, two 1024-sample FIFOs, and a register bus on the 25 MHz clock reached over JTAG. The host pushes samples, writes RUN, and pops saturated 16-bit outputs. The run stopped in stage rtl-design-creation after six visits with the same failure. Verification reached V1 of V3, and no Vivado build, timing, power or board result exists.
not: Not built or measured on hardware. Synthesis, implementation, timing, power and bring-up were not run.; Not a general FIR. The coefficients are fixed, symmetric, and loaded from data/coeffs.hex at build time.; Not a transceiver design. sfp_tx_disable is meant to be held at 1 and no GT channel is used.

## state
stage=spec vivado=2026.1 kb_pin=5e2eab8 build_id=None
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Per spec.yaml it is synchronous and held for a few clocks at start by jtag_bus.sv. A copy is synchronised into clk_dsp, and MMCM lock also holds the datapath in reset. This was not confirmed in a passing build.
if clk_25 input clock, pin C3, LVCMOS18, 25 MHz: design.xdc names the port clk_25 and constrains it with a 40 ns period. spec.yaml and ARCHITECTURE.md call it clk25, so the spec disagrees with the XDC on the name.
if led output, 2 bits (F8 and E8, LVCMOS18): Per the spec's assumption led[0] shows BUSY and led[1] shows MMCM lock or heartbeat. The function was defaulted, not specified.
if sfp_tx_disable output, 1 bit (Y10, LVCMOS33): Meant to be constant 1, laser off.
if h_we, h_re, h_addr, h_wdata, h_rdata internal register port (1, 1, 12, 32 and 32 bits): This is the jtag_bus register port in the clk25 domain, not a top-level pin group.
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 scratch
reg 16 CTRL RW reset=0 0 CLEAR self-clearing; 1 RUN self-clearing
reg 20 IN_PUSH WO reset=0 15:0 sample
reg 24 OUT_POP RO reset=0 31 valid; 15:0 oldest output; read pops
reg 28 STATUS RO reset=0 0 BUSY; 15:4 input FIFO count; 31:20 output FIFO count
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs since CLEAR
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed since CLEAR
param NUM_TAPS=32 legal=32 only; the pre-add pairing assumes an even tap count
param UNIQUE_COEFFS=16 legal=NUM_TAPS/2
param DATA_WIDTH=16 legal=16 only
param COEFF_WIDTH=16 legal=16 only
param ACC_WIDTH=37 legal=at least the width of the exact sum
param FIFO_DEPTH=1024 legal=1024 per the spec
param ROUND_CONST=16,384 legal=2^(SHIFT-1)
param SHIFT=15 legal=15 for Q1.15
param DESIGN_ID=546,570,241 legal=any 32-bit value
param MMCM_MULT=10 legal=set by the MMCM VCO range
param MMCM_DIV=1 legal=set by the MMCM VCO range

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml bc104065bd: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md ff60449ad1: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 4a58dafa1a: the machine-checked architecture: blocks, clocks, predicted resources
design.xdc 713c2601ca: pin, I/O standard and timing constraints
model.py 374cc9de6c: the Modeller's reference model of the visible behaviour
tests/fir_bench.py fd11f904c2: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py d949fc541b: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 80ec3e7675: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/02_rtl-design-creation.html 134cb322e4: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261125-133549-a1e9/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261125-133549-a1e9/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261125-133549-a1e9/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim python -m pytest -q -x runs/20261125-133549-a1e9/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py && python3 flow/verif_gates.py runs/20261125-133549-a1e9/p4_fir_dsp --runs runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim
[heavy] rebuild the bitstream with the flow: flow/run_vivado.sh runs/20261125-133549-a1e9/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261125-133549-a1e9/summary.json d08f93c434
R2 build/verif/verif_gates.json 1a489c3f06

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V1 of V3; the run asked for V2; V1 means every spec item is traced to a check and the benches use the blind model; V2 (simulation: seeded runs, a constrained-random test, bound assertions and formal tasks) did not pass: seeds run no seeded results: read runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. The flow's simulation step writes it when the bench runs through flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=N) in tests/test_*_rtl.py: call run() once per seed (for example seed=1, 2, 3; a seed left out counts as seed 1) with the module(s) listed in bench.modules; the flow runs it and checks again. A bench that runs the simulator some other way leaves nothing there. (needs >=1 seed); constrained random test ran not evaluated (no seeded results) (needs True); assertions bound zero failures not evaluated (no seeded results) (needs bound in the run; no failure); V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: seeds run no seeded results: read runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. The flow's simulation step writes it when the bench runs through flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=N) in tests/test_*_rtl.py: call run() once per seed (for example seed=1, 2, 3; a seed left out counts as seed 1) with the module(s) listed in bench.modules; the flow runs it and checks again. A bench that runs the simulator some other way leaves nothing there. (needs >=3); functional bins pct not evaluated (no seeded results) (needs 100); cover properties pct not evaluated (no seeded results) (needs 100); line pct not evaluated (no seeded results) (needs 90); toggle pct not evaluated (no seeded results) (needs 75); mutation score pct not measured (needs 80); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded

## measured
M1 cost -=3.10723 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-03] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_regs_smoke) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-02] REQ-02 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-30, REQ-04, REQ-31, REQ-05, REQ-32] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_regs_smoke) is pending: no simulation results
[REQ-06] REQ-06 has no passing evidence for every proof method: simulation (fir_bench.test_impulse) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-07] REQ-07 has no passing evidence for every proof method: simulation (fir_bench.test_step) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-08] REQ-08 has no passing evidence for every proof method: simulation (fir_bench.test_random_chunks) is pending: no simulation results; hardware (uart_tests) is pending: no bring-up result
[REQ-09, REQ-10, REQ-24, REQ-35, REQ-36, REQ-37, REQ-38] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_history_clear) is pending: no simulation results
[REQ-11, REQ-14, REQ-27, REQ-28] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[REQ-12, REQ-19, REQ-25] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_busy_rate) is pending: no simulation results
[REQ-13, REQ-39, REQ-29] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is pending: no flow gates result
[REQ-15, REQ-17, REQ-34, REQ-33] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_impulse) is pending: no simulation results
[REQ-16] REQ-16 has no passing evidence for every proof method: simulation (fir_bench.test_fifo_full_empty) is pending: no simulation results; formal (fir_bench.test_fifo_full_empty) is pending: re-planned from formal to simulation (SymbiYosys is not installed, so the full-FIFO ignore rule is checked by a directed simulation test against the model.): no simulation results
[REQ-18, REQ-20, REQ-21] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_fifo_full_empty) is pending: no simulation results
[REQ-22, REQ-23] (each of these) has no passing evidence for every proof method: simulation (fir_bench.test_saturation) is pending: no simulation results
[REQ-26] REQ-26 has no passing evidence for every proof method: simulation (fir_bench.test_regs_smoke) is pending: no simulation results; analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: lint not passing FAIL simulate not passing FAIL standards STD-LATCH-01: not checked (no build.yaml top or sources to check) FAIL standards STD-LOOP-01: not checked (no build.yaml top or sources to check) FAIL standards STD-CDC-01: architecture.yaml:1: crossings[0]: inline_in fir32_core is not a module of this design or the shell FAIL standards STD-CDC-01: architecture.yaml:1: crossings[1]: inline_ ...
[constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verification V2; owned by the rtl/tests role; last failing assertion: V2 seeds_run: no seeded results: read runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed*/results.xml and found none. The gate expects runs/20261125-133549-a1e9/p4_fir_dsp/build/verif/sim/seed<N>/results.xml, one directory per seed. ; the same failure on 6 consecutive visits)
[formal] formal checks were planned for REQ-16 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed, so the full-FIFO ignore rule is checked by a directed simulation test against the model.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[clock_port_name] design.xdc constrains a port named clk_25 with a 40 ns period (25 MHz) on C3. spec.yaml and ARCHITECTURE.md name it clk25. The XDC is what was built, so the top level must expose clk_25.
[xdc_clocks] design.xdc has no constraint for the 250 MHz clk_dsp. Whether the MMCM output is auto-derived was not checked, since no build ran.
[spec_sources_unread] spec.yaml records that data/jtag_bus.sv and coeffs.hex were not readable when the spec was written, so the bus interface came from spec.md text only. The 12-bit h_addr and the register timing are therefore unconfirmed against that file.
[defaulted_behaviour] All 8 interview answers were defaulted, not answered by a person. Decided by default: pushes during BUSY are accepted but processed at the next RUN; RUN while BUSY is ignored; RUN with an empty input FIFO completes at once with no output; RUN processes only as many samples as fit in the output FIFO; CLEAR wins over a RUN in the same write and aborts a run; SAT_COUNT and SAMPLES_DONE wrap at 32 bits; OUT_POP bits 30:16 are 0.
[unmapped_access] Per spec.yaml, unmapped addresses read 0 and ignore writes. Writes to the read-only registers are presumably ignored too, but the spec does not say so and no RTL was reviewed.
[read_side_effect] An OUT_POP read removes the oldest output as a side effect. An empty FIFO returns 0, so a valid sample with value 0 is told apart only by bit 31.
[latency_count] The spec promises h_rdata within 2 clk25 cycles of h_re, a write effect 1 clk25 cycle after h_we, and a filter pipeline of a few clk_dsp cycles. None was counted from the RTL here, because no passing simulation or build exists to count from.

## next_actions
1. Fix stage rtl-design-creation first. Make the bench call flow.cocotb_run.run() once per seed (seed=1, 2, 3) so that a results.xml exists for each seed under build/verif/sim, then re-run the verification gates. Then clear the lint, simulate and STD-CDC-01 failures: the inline_in names in architecture.yaml crossings must match real modules.
2. Once seeded results exist, compare the cover results with the functional coverage before adding any new stimulus.
3. Re-run V2 and V3 until the line, toggle, functional, cover, mutation and CDC checks pass.
4. Resume the flow with python -m agent resume to reach constraints, synthesis and implementation. Check the clk_dsp constraint and the clk_25 port name against the spec, and re-count the latencies from the RTL.
5. Run hardware bring-up for the requirements that list hardware proof (ID, BUILD, SCRATCH, impulse, step, random chunks).

## open_questions
- Should the top-level port be named clk25 as in the spec or clk_25 as in design.xdc?
- Are the defaulted behaviours (RUN while BUSY, output FIFO overflow limit, CLEAR priority over RUN) the intended ones?
- Do the offsets in spec.md stay final?

## history
2026-11-25 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
