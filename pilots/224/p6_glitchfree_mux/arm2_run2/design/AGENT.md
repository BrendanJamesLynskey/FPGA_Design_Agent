# AGENT p6_glitchfree_mux (fda-handover/1)
source: runs/20261126-011553-f268/p6_glitchfree_mux/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261126-011553-f268/p6_glitchfree_mux

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=p6_clkmux_top tool=Vivado 2026.1
agent_run=20261126-011553-f268 record=runs/20261126-011553-f268/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 8 loops, 194 turns, 7,847,196 tokens, 2176.8 s wall time, 4.36906 USD model cost (provider-reported), stopped because: stage 2 visited more than 6 times; last failing gate: design standards; owned by the rtl role; the same failure on 3 consecutive visits

## summary
The design switches a BUFGCTRL clock mux between the 25 MHz board clock (clock A) and the SFP+ 156.25 MHz GT reference clock divided by B_DIV (clock B). A counter with a Gray-coded twin runs on the muxed clock and counts its own errors. A JTAG register bus controls the select, a frequency gate, error and switch counters and a counter snapshot. The run stopped at rtl-design-creation, which failed its design-standards gate; no constraints, synthesis or implementation stage ran. Verification reached V2 of V3 and no board result exists.
not: Not a transceiver design; no GT channel is used and sfp_tx_disable is held at 1.; Not proven on hardware, and no resource, timing or power figure exists for it.; Not a clock-failure tolerant mux; both clocks must keep running during a switch.

## state
stage=rtl vivado=2026.1 kb_pin=6185830 build_id=4c855de1
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk 25MHz
clk gtref_p 156.25MHz
rst rst active-high: Internal power-on reset generated in rtl/p6_clkmux_top.sv from a counter with initial values (no reset pin), synchronous to clk. It reaches the muxed domain through xpm_cdc_async_rst (rtl/p6_clkmux_core.sv).
if clk input, 25 MHz board clock on pin C3 (LVCMOS18): Clock A, the register bus clock and the gate timer clock; design.xdc creates a 40 ns clock on it.
if gtref_p input, differential GT reference clock, positive leg: Clock B source through IBUFDS_GTE4 and BUFG_GT; design.xdc creates a 6.4 ns clock on it but assigns no PACKAGE_PIN to it.
if gtref_n input, differential GT reference clock, negative leg: No pin constraint in design.xdc; ARCHITECTURE.md says the pins are still to be resolved.
if sfp_tx_disable output, 1 bit on pin Y10 (LVCMOS33): Driven to 1 at all times.
if led output, 2 bits, F8 for led[0] and E8 for led[1] (LVCMOS18): led[0] is the synchronised ACTIVE_SEL; led[1] is set when the synchronised MUX_ERRS is nonzero.
reg 0 ID RO reset=546701313 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 data
reg 16 SEL RW reset=0 0 select (0 clock A, 1 clock B)
reg 20 STATUS RO reset=0 0 SWITCHING, 1 ACTIVE_SEL
reg 24 B_DIV RO reset=1 3:0 divide 1 to 8
reg 28 GATE_LEN RW reset=25000000 31:0 gate length in C3 cycles
reg 32 FREQ_CTRL RW reset=0 0 START self-clearing
reg 36 FREQ_STATUS RO reset=0 0 BUSY, 1 DONE
reg 40 FREQ_COUNT RO reset=0 31:0 edges in last gate
reg 44 MUX_ERRS RO reset=0 31:0 error count
reg 48 MUX_COUNT RO reset=0 31:0 counter low 32 bits at last SNAPSHOT
reg 52 SWITCH_COUNT RO reset=0 31:0 switches carried out
reg 56 SNAPSHOT WO reset=0 any write latches MUX_COUNT
param DESIGN_ID=546,701,313 legal=any 32-bit value
param B_DIV=1 legal=1 to 8
param GATE_LEN_DEFAULT=25,000,000 legal=1 to 4294967295 (0 acts as 1)
param GATE_LEN_BITS=32 legal=fixed at 32
param RST_HOLD_CYCLES=8 legal=fixed at 8
param ADDR_WIDTH=12 legal=fixed at 12

## files (paths under the design directory are relative to it)
spec.md f0fea2fdef: the request the run started from
spec.yaml ad5b676850: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md 3539d66a86: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml da1b2bbda1: the machine-checked architecture: blocks, clocks, predicted resources
rtl/p6_clkmux_core.sv 92c08db997: RTL written by the Designer
rtl/p6_clkmux_top.sv 670e360cb4: RTL written by the Designer
rtl/p6_clkmux_wrap.sv 162605266e: RTL written by the Designer
rtl/p6_lint_cfg.sv 3927ac0068: RTL written by the Designer
rtl/p6_mux_domain.sv 9a8ccf7f32: RTL written by the Designer
rtl/xilinx_sim_stubs.sv 3ee097abc9: RTL written by the Designer
design.xdc f341dc43f1: pin, I/O standard and timing constraints
build.yaml 288ad9d1f3: the build description read by the flow
model.py da5bf41275: the Modeller's reference model of the visible behaviour
tests/p6_bench.py 6fb385dac7: the Verifier's cocotb benches and pytest entries
tests/test_p6_glitchfree_mux_rtl.py c6d62fc551: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 414a86d802: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/02_rtl-design-creation.html b2898d256c: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261126-011553-f268/p6_glitchfree_mux
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261126-011553-f268/p6_glitchfree_mux "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261126-011553-f268/p6_glitchfree_mux/tests/test_p6_glitchfree_mux_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261126-011553-f268/p6_glitchfree_mux/build/verif/sim python -m pytest -q -x runs/20261126-011553-f268/p6_glitchfree_mux/tests/test_p6_glitchfree_mux_rtl.py && python3 flow/verif_gates.py runs/20261126-011553-f268/p6_glitchfree_mux --runs runs/20261126-011553-f268/p6_glitchfree_mux/build/verif/sim
[heavy] rebuild the bitstream with the flow (~2.2min): flow/run_vivado.sh runs/20261126-011553-f268/p6_glitchfree_mux base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261126-011553-f268/summary.json d0f4c880ad
R2 build/verif/verif_gates.json bdb33446b1
R3 build/base/gates.json a0f5905a44

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 80); cdc structure clean U5 u_core/u_core/u_err/dest_graysync_ff_reg[0][0]: xpm_gray bus without its Max Delay Datapath Only exception (exception: 'Asynch Clock Groups'): the macro's constraints did not reach the netlist, U5 u_core/u_core/u_err/dest_graysync_ff_reg[0][10]: xpm_gray bus without its Max Delay Datapath Only exception (exception: 'Asynch Clock Groups'): the macro's constraints did not reach the netlist, U5 u_core/u_core/u_err/dest_graysync_ff_reg[0][11]: xpm_gray bus without its Max Delay Datapath Only exception (exception: 'Asynch Clock Groups'): the macro's constraints did not reach the netlist, U5 u_core/u_core/u_err/dest_graysync_ff_reg[0][12]: xpm_gray bus without its Max Delay Datapath Only exception (exception: 'Asynch Clock Groups'): the macro's constraints did not reach the netlist, U5 u_core/u_core/u_err/dest_graysync_ff_reg[0][13]: xpm_gray bus without its Max Delay Datapath Only exception (exception: 'Asynch Clock Groups'): the macro's constraints did not reach the netlist, U5 u_core/u_core/u_err/dest_graysync_ff_reg[0][14]: xpm_gray bus without its Max Delay Datapath Only exception (exception: 'Asynch Clock Groups'): the macro's constraints did not reach the netlist ... (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build fail R3: Vivado base build; flow stages that ran: rtl, post_synth

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=4.36906 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-02, REQ-03, REQ-07, REQ-29, REQ-08, REQ-10, REQ-13, REQ-31, REQ-14, REQ-15, REQ-18, REQ-19, REQ-21] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-24] REQ-24 has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
[E3] build evidence is fail: Vivado base build; flow stages that ran: rtl, post_synth
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: standards STD-ARCH-00: :0: the checker could not read the design: KeyError: 'id' FAIL
[constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: design standards; owned by the rtl role; the same failure on 3 consecutive visits)
[formal] formal checks were planned for REQ-05, REQ-28, REQ-16, REQ-17, REQ-22 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here, so the read latency is checked in simulation against the model.
[simulated_parameters] the benches simulate at values other than the spec's (scaled for simulation speed or otherwise): GATE_LEN_DEFAULT is simulated at 300 (runs/20261126-011553-f268/p6_glitchfree_mux/tests/test_p6_glitchfree_mux_rtl.py:21) while spec.yaml gives 25000000. Behaviour that depends on the spec's value, such as a divider's timing against the clock, was not simulated at that value; it is stated here, not shown, unless another record covers it
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[GATE_LEN_BITS_RST_HOLD] GATE_LEN_BITS, RST_HOLD_CYCLES and ADDR_WIDTH are listed as parameters in spec.yaml but are literals in the RTL, so they cannot be changed from the top level.
[reset_hold_length] The reset counter in rtl/p6_clkmux_top.sv counts rst_cnt from 0 to 8 before releasing rst, so reset is held for about 9 clk cycles, not the 8 the spec states. The RTL is what was built.
[register_decode] Unmapped addresses read 0 and ignore writes. Writes to RO registers are ignored. FREQ_CTRL reads 0 always. Reading SNAPSHOT (0x038) returns 0 (default arm).
[start_behaviour] A START write is ignored while BUSY. GATE_LEN is sampled at START, and a value of 0 is treated as 1. The gate timer does not count down in the cycle of a START write.
[sel_during_switching] A SEL write is stored in sel immediately, but the mux only follows after the current change completes (latest value wins). SWITCH_COUNT is incremented when a switch completes, after a minimum wait of 16 clk cycles (SW_MIN).
[read_latency] In rtl/p6_clkmux_core.sv h_rdata is registered on h_re, so it is valid 1 clk after h_re and held until the next h_re. This is within the spec's 2 clk promise. The latency was checked only in simulation. A write takes effect 1 clk after h_we.
[build_register] BUILD reads USR_ACCESSE2 only under SYNTHESIS; in simulation it reads 0.
[bufgctrl_sim_model] In simulation BUFGCTRL and BUFG_GT are ideal stubs (rtl/xilinx_sim_stubs.sv), so glitch-free switching and the clock B divide are not exercised by the benches.
[cdc_finding] The verification gate reports unsafe crossings on the xpm_cdc_gray bus u_err (MUX_ERRS), saying the macro's Max Delay Datapath Only exception is missing and that only an Asynch Clock Groups exception is present. design.xdc uses set_clock_groups, so it needs checking after a build. The cdc injection check is missing.
[gt_pins] design.xdc has no PACKAGE_PIN for gtref_p or gtref_n, although the spec names SFP+ MGTREFCLK0. The pin assignment is unresolved.
[spec_disagrees_ids] The spec requirement gaps for hardware proof (uart_tests) refer to a bring-up that was never run, and REQ-24 needs post_route timing that never ran.
[approval] The specification and architecture were approved automatically with no human review; the interview oracle only answered the interview questions.
[coverage_disagreement] Functional bins read 0 of 0 and cover properties 0.0 percent, and line, toggle and mutation figures were not measured, so coverage is unproven rather than shown.

## next_actions
1. Fix the design-standards failure at rtl-design-creation (STD-ARCH-00, the checker raises KeyError 'id' while reading the design; look at architecture.yaml for a missing id field), then resume with python -m agent resume.
2. Compare the cover results with the functional coverage before adding any new stimulus, since both read 0 of 0.
3. Resolve the gtref_p and gtref_n pin assignments in design.xdc and review the clock-group constraints against the u_err Gray crossing finding.
4. Run constraints through implementation, then check timing, and plan a hardware bring-up for the hardware-proof requirements.

## open_questions
- Which package pins carry SFP+ MGTREFCLK0 on the KR260, so gtref_p and gtref_n can be constrained?
- Should the spec's reset hold of 8 clk cycles be restated to match the longer hold the RTL implements, or the RTL changed?

## history
2026-11-26 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
