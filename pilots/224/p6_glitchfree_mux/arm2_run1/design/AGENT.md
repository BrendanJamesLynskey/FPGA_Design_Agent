# AGENT p6_glitchfree_mux (fda-handover/1)
source: runs/20261125-203614-91c8/p6_glitchfree_mux/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261125-203614-91c8/p6_glitchfree_mux

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=p6_clkmux_top tool=Vivado 2026.1
agent_run=20261125-203614-91c8 record=runs/20261125-203614-91c8/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 8 loops, 169 turns, 7,009,619 tokens, 2906.6 s wall time, 4.99015 USD model cost (provider-reported), stopped because: stage 2 visited more than 6 times; last failing gate: design standards; owned by the rtl role; the same failure on 4 consecutive visits

## summary
The design selects between the 25 MHz board clock and the SFP+ MGTREFCLK0 reference (through IBUFDS_GTE4 and BUFG_GT) with a BUFGCTRL, and exposes control, status, a Gray-coded counter checker and a frequency gate through a JTAG register bus. The run stopped at the RTL stage, whose design-standards gate failed on the BUFGCTRL clock mux. Verification reached V2 of V3, no Vivado build passed its gates, and nothing was run on the board. The specification and architecture were accepted automatically, with no human review.
not: Not a general clock manager. It has two inputs, one BUFGCTRL, and no PLL or MMCM.; Does not use any GT transceiver channel; the GT reference buffer feeds only the mux.; Not built, timed or run on hardware in this run; no resource, timing or power figure exists.

## state
stage=rtl vivado=2026.1 kb_pin=6185830 build_id=a072a826
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Internal power-on reset in p6_clkmux_top.sv: a synchronous counter in clk_c3, held for RST_HOLD_CYCLES clocks, with no reset pin. It is brought into mux_clk through xpm_cdc_async_rst.
if clk_c3 input, 25 MHz clock: design.xdc names this port clk_25 on pin C3 (LVCMOS18) with a 40 ns clock, while spec.yaml and the RTL top use clk_c3.
if gtref_p / gtref_n input, differential reference clock, 156.25 MHz: Spec role is SFP+ MGTREFCLK0; design.xdc has no pin or clock constraint for these ports.
if led output, 2 bits: The RTL drives led[0] = ACTIVE_SEL and led[1] = SWITCHING. design.xdc places them on F8 and E8 (LVCMOS18).
if sfp_tx_disable output, 1 bit: Constant 1. design.xdc puts it on Y10 (LVCMOS33).
reg 0 ID RO reset=546701313 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 data
reg 16 SEL RW reset=0 0 clock select (0=A, 1=B)
reg 20 STATUS RO reset=0 0 SWITCHING, 1 ACTIVE_SEL
reg 24 B_DIV RO reset=1 3:0 divide 1 to 8
reg 28 GATE_LEN RW reset=25000000 31:0 gate length in clk_c3 cycles
reg 32 FREQ_CTRL RW reset=0 0 START self-clearing
reg 36 FREQ_STATUS RO reset=0 0 BUSY, 1 DONE
reg 40 FREQ_COUNT RO reset=0 31:0 edges in last gate
reg 44 MUX_ERRS RO reset=0 31:0 error count
reg 48 MUX_COUNT RO reset=0 31:0 counter at last SNAPSHOT
reg 52 SWITCH_COUNT RO reset=0 31:0 switches done
reg 56 SNAPSHOT WO reset=0 any write latches MUX_COUNT
param ID_VALUE=546,701,313 legal=any 32-bit value
param B_DIV=1 legal=1 to 8
param GATE_LEN_DEFAULT=25,000,000 legal=1 to 4294967295
param RST_HOLD_CYCLES=16 legal=1 to 32 (the reset counter is 5 bits)

## files (paths under the design directory are relative to it)
spec.md f0fea2fdef: the request the run started from
spec.yaml 7fc74c75ab: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md 1dff6844cd: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 750c711a9b: the machine-checked architecture: blocks, clocks, predicted resources
rtl/lint_waivers.vlt 27b66ef42f: RTL written by the Designer
rtl/p6_clkmux_core.sv 3e02b51907: RTL written by the Designer
rtl/p6_clkmux_top.sv 3e8582d41a: RTL written by the Designer
rtl/xilinx_sim_stubs.sv a507eb9b82: RTL written by the Designer
design.xdc 713c2601ca: pin, I/O standard and timing constraints
build.yaml 555f84c1c8: the build description read by the flow
model.py 6d25a2fbe9: the Modeller's reference model of the visible behaviour
tests/p6_glitchfree_mux_bench.py 4f02071cdd: the Verifier's cocotb benches and pytest entries
tests/test_p6_glitchfree_mux_rtl.py 598060b69a: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml a9e50bb004: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/02_rtl-design-creation.html d62166d1c2: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261125-203614-91c8/p6_glitchfree_mux
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261125-203614-91c8/p6_glitchfree_mux "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261125-203614-91c8/p6_glitchfree_mux/tests/test_p6_glitchfree_mux_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261125-203614-91c8/p6_glitchfree_mux/build/verif/sim python -m pytest -q -x runs/20261125-203614-91c8/p6_glitchfree_mux/tests/test_p6_glitchfree_mux_rtl.py && python3 flow/verif_gates.py runs/20261125-203614-91c8/p6_glitchfree_mux --runs runs/20261125-203614-91c8/p6_glitchfree_mux/build/verif/sim
[heavy] rebuild the bitstream with the flow (~1.7min): flow/run_vivado.sh runs/20261125-203614-91c8/p6_glitchfree_mux base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261125-203614-91c8/summary.json de098ec895
R2 build/verif/verif_gates.json 6d6cd9974b
R3 build/base/gates.json 19051930b1

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 80); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build fail R3: Vivado base build; flow stages that ran: rtl, post_synth

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=4.99015 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-02, REQ-03, REQ-06, REQ-08, REQ-10, REQ-12, REQ-14] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-07] REQ-07 has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None; hardware (ila_captures) is pending: no bring-up result
[REQ-19] REQ-19 has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
[E3] build evidence is fail: Vivado base build; flow stages that ran: rtl, post_synth
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: standards STD-CLK-01: rtl/p6_clkmux_core.sv:37: instance u_bufgctrl (BUFGCTRL) in p6_clkmux_core: a clock mux not declared in architecture.yaml clock_muxes (declare it with its inputs, condition and reason, or use a clock enable) FAIL
[constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: design standards; owned by the rtl role; the same failure on 4 consecutive visits)
[formal] formal checks were planned for REQ-05 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here, so the read-latency claim is checked by model-compared register reads in simulation.
[simulated_parameters] the benches simulate at values other than the spec's (scaled for simulation speed or otherwise): GATE_LEN_DEFAULT is simulated at 200 (runs/20261125-203614-91c8/p6_glitchfree_mux/tests/test_p6_glitchfree_mux_rtl.py:32) while spec.yaml gives 25000000. Behaviour that depends on the spec's value, such as a divider's timing against the clock, was not simulated at that value; it is stated here, not shown, unless another record covers it
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[clock_port_name] The spec and the top-level RTL call the 25 MHz port clk_c3, but design.xdc constrains a port named clk_25 (pin C3, 40 ns). The names disagree, so the constraint would not match the RTL port as written.
[gtref_constraints] design.xdc has no pin or clock constraint for gtref_p and gtref_n, although the spec gives a 156.25 MHz clock there. It also declares no asynchronous clock groups, which the spec assumes.
[bufgctrl_declaration] The BUFGCTRL at p6_clkmux_core.sv:37 is not declared in architecture.yaml clock_muxes, and this is the failing standards gate (STD-CLK-01).
[cover_vs_functional] Functional bins and cover properties both read 0.0 percent with 0 of 0 bins, so no bin or cover property was counted. Treat this as a measurement fault until the cover results are compared with the functional coverage.
[read_latency] h_rdata is registered in the core on h_re, so it is valid one clk_c3 cycle after h_re (p6_clkmux_core.sv). The spec allows 2. The jtag_bus delay is not counted here, and the value is held until the next h_re.
[unmapped_access] Reads of unmapped addresses return 0 (default of the read case). Writes to them are ignored. Offsets 0x00C, 0x03C and above are unmapped.
[fixed_zero_reads] A read of FREQ_CTRL (0x020) returns 0, so START is never seen as 1. Writes to RO registers are ignored. A write to SNAPSHOT (0x038) copies the most recent hand-over word into MUX_COUNT, with any data. That word comes from a continuous handover, so it can be older than the write.
[freq_start_rules] START is ignored while BUSY. GATE_LEN 0 is treated as 1 at START, and GATE_LEN writes apply at the next START. START clears DONE and FREQ_COUNT. DONE is set after the gate plus 12 settle clocks, so BUSY outlasts the gate.
[sel_write_priority] A SEL write during SWITCHING simply overwrites sel_q, so the latest value wins. SWITCHING is sel_q != active, which also reads 1 after the BUFGCTRL has switched until the detector updates ACTIVE_SEL.
[active_sel_detection] ACTIVE_SEL is inferred by counting toggles of a slow tap bit of the mux counter over 64-clock windows, and needs two consecutive agreeing windows. It assumes clock B is faster than clock A. At B_DIV values where clock B is not faster than 25 MHz, the detector would be wrong. It is not a direct read of BUFGCTRL state, so the switch latency is a multiple of 64 clk_c3 cycles.
[build_in_sim] BUILD reads 0 in simulation because USR_ACCESSE2 exists only under SYNTHESIS. REQ-02 can be proved only on hardware.
[error_count] MUX_ERRS saturates at 0xFFFFFFFF and clears only at reset. The checker skips its first mux_clk after reset (valid flag). The counter and Gray twin are not reset.
[led_mapping] The LED mapping was a defaulted interview answer, not a requirement. led = {SWITCHING, ACTIVE_SEL}.

## next_actions
1. Fix the failing rtl-design-creation gate first: declare the BUFGCTRL u_bufgctrl in architecture.yaml clock_muxes with its inputs, condition and reason, then resume with python -m agent resume.
2. Reconcile design.xdc with the RTL: rename the clk_25 constraint to clk_c3 (or the reverse), add the gtref pins, the 156.25 MHz clock and the asynchronous clock groups.
3. Compare the cover results with the functional coverage before any new stimulus, because both read 0 of 0, then rerun the Verilator coverage simulation and the verification gates to reach V3.
4. Simulate with GATE_LEN_DEFAULT at the spec value, or add a check that covers it.
5. Re-run the later stages (constraints through configuration-and-debug) and the Vivado base build, then record resources, timing and power.
6. Run the hardware bring-up for the pending requirements, including the 1,000 random switches.

## open_questions
- Should the 25 MHz port be named clk_c3 or clk_25 in the final design?
- Is a one-cycle read latency acceptable for REQ-05, given jtag_bus adds its own delay?

## history
2026-11-25 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
