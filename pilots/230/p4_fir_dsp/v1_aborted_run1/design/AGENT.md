# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261126-105159-268e/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261126-105159-268e/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=fir32_top tool=Vivado 2026.1
agent_run=20261126-105159-268e record=runs/20261126-105159-268e/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 10 loops, 169 turns, 6,832,515 tokens, 5605.5 s wall time, 6.91115 USD model cost (provider-reported), permission mode auto (12 distinct gated decisions listed in handover.yaml), stopped because: stage 2 visited more than 6 times; last failing gate: post_synth:post_synth_exceptions_clean (EXC-IGNORED position 3 Position=3 From=[get_clocks, report gate RPT-LL-02 timing_summary_synth.rpt:rst25_reg/C->u_core/u_rst_dsp/arststages_ff; the failure was in stage 3 constraints (visit 1), routed to stage 2 rtl-design-creation; stage 2 was refused before any gate ran

## summary
The design is a 32-tap symmetric Q1.15 FIR low-pass filter. Samples are pushed into an input FIFO over a JTAG register bus on clk25, a RUN command filters them on a 250 MHz MMCM clock using 16 multipliers, and the results are read back from an output FIFO. The run got as far as the constraints stage, whose gates failed; synthesis and later stages did not run. Verification reached V2 of V3, and no resource, timing or power number was measured.
not: Not a runtime-programmable filter; the coefficients are fixed, symmetric and written into fir_dsp.sv.; Not a streaming core; samples go in only through the IN_PUSH register and come out through OUT_POP.; No transceiver is used (sfp_tx_disable is a constant output) and no hardware result exists for this design.

## state
stage=simulated vivado=2026.1 kb_pin=eaf6794 build_id=0ce4163c
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=pass constraints=fail synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk25 25MHz
rst rst (internal, no pin) active-high: fir32_top.sv builds rst25 from a 16-clock power-on counter and the MMCM lock, registered in clk25, and feeds it to jtag_bus and fir32_core (synchronous in clk25). It enters clk_dsp through xpm_cdc_async_rst, which asserts asynchronously. The spec says the design has no reset input and uses reprogram; the RTL has this internal reset.
if clk25 input, 25 MHz board clock, pin C3 LVCMOS18: Constrained with a 40.00 ns period named sys_clk_pin in design.xdc.
if led output [1:0], F8 (led[0]) and E8 (led[1]), LVCMOS18: fir32_top.sv drives led[0] with BUSY and led[1] with the synchronised MMCM lock. The XDC has a false path to both.
if sfp_tx_disable output, pin Y10, LVCMOS33: Constant 1 (fir32_core.sv). The XDC has a false path to it.
if h_we, h_re, h_addr, h_wdata, h_rdata internal register port to jtag_bus (no pins), 1, 1, 12, 32 and 32 bits: Runs on clk25. These signals are internal nets between jtag_bus and fir32_core, not top-level ports in fir32_top.sv.
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 scratch
reg 16 CTRL RW reset=0 0 CLEAR self-clearing, 1 RUN self-clearing, 31:2 reserved 0
reg 20 IN_PUSH WO reset=0 15:0 sample pushed
reg 24 OUT_POP RO reset=0 31 valid, 15:0 oldest output, read pops; 0 when empty
reg 28 STATUS RO reset=0 0 BUSY, 15:4 input FIFO count, 31:20 output FIFO count, others 0
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs since CLEAR
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed since CLEAR
param N_TAPS=32 legal=fixed at 32
param N_MULT=16 legal=fixed at 16 (N_TAPS/2)
param DATA_WIDTH=16 legal=fixed at 16
param COEF_WIDTH=16 legal=fixed at 16
param ACC_WIDTH=38 legal=fixed at 38
param FIFO_DEPTH=1024 legal=fixed at 1024
param SHIFT=15 legal=fixed at 15
param ROUND_CONST=16,384 legal=fixed at 16384 (2^(SHIFT-1))
param DESIGN_ID=546,570,241 legal=fixed at 0x20940001
param SFP_TX_DISABLE_VALUE=1 legal=fixed at 1

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml 1131d36fa7: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md e02cf17a93: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 98ee456cd9: the machine-checked architecture: blocks, clocks, predicted resources
rtl/a_lint_waivers.sv 0b5032b54d: RTL written by the Designer
rtl/fir32_core.sv 02325a4cf4: RTL written by the Designer
rtl/fir32_top.sv 42420922a5: RTL written by the Designer
rtl/fir_dsp.sv c266f1cef6: RTL written by the Designer
rtl/xilinx_sim_stubs.sv 84ccaa9625: RTL written by the Designer
design.xdc c34ffcf402: pin, I/O standard and timing constraints
build.yaml 29555f7baf: the build description read by the flow
model.py d516f89e5d: the Modeller's reference model of the visible behaviour
tests/fir_bench.py b884d72eb2: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py 74d2e9b9d4: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 977622f6e1: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/03_constraints.html b6b17c23e1: the review page of stage constraints: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261126-105159-268e/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261126-105159-268e/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261126-105159-268e/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261126-105159-268e/p4_fir_dsp/build/verif/sim python -m pytest -q -x runs/20261126-105159-268e/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py && python3 flow/verif_gates.py runs/20261126-105159-268e/p4_fir_dsp --runs runs/20261126-105159-268e/p4_fir_dsp/build/verif/sim
[heavy] rebuild the bitstream with the flow (~3.3min): flow/run_vivado.sh runs/20261126-105159-268e/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261126-105159-268e/summary.json 8ff3744aa5
R2 build/verif/verif_gates.json 52da275d8b
R3 build/base/gates.json d56ae9b7ca

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 9 questions, 0 answered and 9 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 80); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build fail R3: Vivado base build; flow stages that ran: rtl, post_synth

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=6.91115 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## requirements_report
REQUIREMENTS_REPORT.md

## assumptions_not_confirmed
[high] What is the register map (offset, width, reset value and access of every register)? -> The map given in spec.md: ID 0x000, BUILD 0x004, SCRATCH 0x008, CTRL 0x010, IN_PUSH 0x014, OUT_POP 0x018, STATUS 0x01C, SAT_COUNT 0x020, SAMPLES_DONE 0x024, all 32 bits, resets 0 except ID. (defaulted: nobody answered)
[high] What happens if RUN is written while BUSY is 1? -> The write is ignored. (defaulted: nobody answered)
[high] What happens when IN_PUSH is written while BUSY is 1? -> The sample is accepted if the FIFO is not full, and is processed by the next RUN. (defaulted: nobody answered)
[high] Do SAT_COUNT and SAMPLES_DONE wrap or saturate at 2^32? -> They wrap. (defaulted: nobody answered)
[high] Is the 250 MHz clock a target or may a faster one such as 300 MHz be used? -> 250 MHz exactly from the MMCM. (defaulted: nobody answered)
[high] Does the BUILD register read 0 in simulation? -> Yes, the USR_ACCESSE2 primitive is replaced by a 0 constant (or a testbench word). (defaulted: nobody answered)
[high] This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every register starts from its initial value), or does something restart the running design (then it needs a reset input)? -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers get initial values, control state included, and the design has no reset input. Record it in spec.yaml as reset: {model: reprogram}; a design that restarts while it runs is reset: {model: reset} with a reset port. (defaulted: nobody answered)
[medium] What happens when the output FIFO is full during a run? -> The run is limited so it never overflows: processing stalls until the output FIFO has room (no result is lost). (defaulted: nobody answered)
[medium] What do led[1:0] show? -> led[0] = BUSY, led[1] = MMCM locked. (defaulted: nobody answered)

## gaps
[REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-17, REQ-20, REQ-45, REQ-44, REQ-22, REQ-33, REQ-34] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-12, REQ-13, REQ-31, REQ-37, REQ-38] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None
[REQ-14, REQ-43, REQ-28, REQ-29, REQ-30] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is not run (the stage that makes this evidence did not run): gate post_synth:post_synth_resources_in_range = None
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 9 questions, 0 answered and 9 defaulted
[E3] build evidence is fail: Vivado base build; flow stages that ran: rtl, post_synth
[constraints] stage constraints did not pass its gates in this run; at its last visit: post_synth:post_synth_exceptions_clean (EXC-IGNORED position 3 Position=3 From=[get_clocks usr_cclk] Through=* To=* Setup=false Hold=false Status=Totally overridden path by FP 7) FAIL report gate RPT-LL-02 timing_summary_synth.rpt:rst25_reg/C->u_core/u_rst_dsp/arststages_ff_reg[0]/PRE: setup path rst25_reg/C to u_core/u_rst_dsp/arststages_ff_reg[0]/PRE (sys_clk_pin, requirement 0.0 ns) has slack - ...
[synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: post_synth:post_synth_exceptions_clean (EXC-IGNORED position 3 Position=3 From=[get_clocks, report gate RPT-LL-02 timing_summary_synth.rpt:rst25_reg/C->u_core/u_rst_dsp/arststages_ff; the failure was in stage 3 constraints (visit 1), routed to stage 2 rtl-design-creation; stage 2 was refused before any gate ran)
[formal] formal checks were planned for REQ-09, REQ-10, REQ-15, REQ-42, REQ-25, REQ-26, REQ-35, REQ-27, REQ-36, REQ-28 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed so bit-exact comparison against the model covers the exact sum.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[coverage_vs_cover] The V3 record shows functional bins 0/0 and cover properties at 0.0 while line and toggle coverage were not measured, so these results say nothing about hit bins. Compare the cover results with the functional coverage before any new stimulus.
[reset_model] The spec says the design has no reset input and every reset is a reprogram. The RTL has an internal active-high rst (fir32_top.sv, a power-on counter plus MMCM lock) and clears state on it. Spec.yaml also names a reset "rst" with a port-like description, which is not a pin.
[reset_failing_path] The failing constraints gate reports a setup path from rst25_reg to the PRE pin of the xpm_cdc_async_rst flops in u_rst_dsp (timing_summary_synth.rpt), and an overridden exception on usr_cclk. design.xdc has no clock for the USR_ACCESSE2 CFGCLK domain. Neither is fixed.
[build_register] BUILD reads 0 in simulation because the USR_ACCESSE2 stub in xilinx_sim_stubs.sv returns 0. In fir32_core.sv it passes through a 2-stage xpm_cdc_array_single with a source clock tied to 0.
[reset_values] On rst, fir32_core.sv clears scratch, the counters, h_rdata and the push buffer to 0. ID reads 0x20940001 whatever the reset state.
[unmapped_access] In fir32_core.sv a read of an unmapped address returns 0 and a write to one changes nothing. Writes to ID, BUILD, STATUS, OUT_POP, SAT_COUNT and SAMPLES_DONE have no effect. Reads of IN_PUSH and CTRL return 0 (default branch).
[ctrl_priority] A CTRL write with bit 0 set runs CLEAR only; bit 1 (RUN) is ignored in that write. RUN is also ignored while BUSY is 1 or when the input FIFO is empty. CLEAR is not instant: it resets the input FIFO for 4 clocks and holds OUT_POP and the STATUS output count at 0 for 8 clk25 clocks, and the output FIFO is reset for 16 clk_dsp clocks. OUT_POP reads 0 and does not pop during this window.
[out_pop_read] OUT_POP pops only on an h_re when the FIFO is not empty and not in reset. h_rdata is registered, so it shows the value on the clock after h_re (one clk25 cycle), within the spec's limit of 2. It holds until the next h_re.
[in_push_buffer] The IN_PUSH writes are accepted when STATUS-visible input count (FIFO plus a 4-entry holding buffer) is below 1024, otherwise ignored. The holding buffer covers an FIFO reset or busy window. STATUS input count is the sum of the FIFO count and the buffer.
[busy_sample_push] Pushes while BUSY are accepted and wait for the next RUN, since RUN takes only the count present at the start. The assumption was defaulted; no one confirmed it.
[counters_wrap] SAT_COUNT and SAMPLES_DONE are 32-bit and wrap. They reach clk25 by a 64-bit handshake sent only when a run ends, so they are stale during a run.
[filter_latency] Counted from fir_dsp.sv: history register, pre-add, multiply, 4-way sum, 2-way sum, final sum and shift/saturate give out_valid 6 clk_dsp cycles after in_valid, plus 1 clock for the history register, so about 7 stages. The spec promised about 10 to 12. The run measured none of this.
[fifo_memory] Both FIFOs are FIFO_MEMORY_TYPE distributed in fir32_core.sv; the spec expected BRAM (2 BRAM36). Resource predictions in ARCHITECTURE.md do not match this.
[mmcm_math] The ARCHITECTURE.md clock plan text is garbled; fir32_top.sv sets CLKFBOUT_MULT_F 40 and CLKOUT0_DIVIDE_F 4 (VCO 1000 MHz, output 250 MHz). design.xdc defines only the clk25 clock; the MMCM output is auto-derived.
[led_order] ARCHITECTURE.md says led[1] is MMCM locked and led[0] is BUSY; fir32_top.sv drives led = {locked25, busy}, which matches. fir32_core.sv drives its own led as {1, busy25}, which the top ignores except for bit 0.
[sim_stubs] In simulation the MMCM stub outputs a constant 0 clock (CLKOUT0 = 0) in xilinx_sim_stubs.sv, so the benches must drive clk_dsp another way. How the benches do this was not checked here.
[unseen_inputs] spec.yaml says data/jtag_bus.sv and data/coeffs.hex were not visible when the spec was written. The coefficients in fir_dsp.sv are inlined; whether they match data/coeffs.hex was not checked.

## next_actions
1. Fix the earliest failing stage, constraints: clear the post_synth_exceptions_clean and RPT-LL-02 failures on the rst25 to u_rst_dsp path and the usr_cclk exception (see reset_failing_path), then re-run the base build.
2. Compare the cover results with the functional coverage (0/0 bins, 0.0 cover) before any new stimulus; then re-run the Verilator coverage command and the verification gates to reach V3.
3. When the flow reaches the build again, re-measure resources, timing, power and latency with python -m agent resume.
4. Bring the spec in line with the RTL on reset model, FIFO memory type and latency, or change the RTL to match it.
5. Run hardware bring-up for the requirements that name it.

## open_questions
- Does data/coeffs.hex match the coefficients written in fir_dsp.sv?
- Should the design keep an internal reset, or follow the spec and use reprogram only?
- Should RUN while BUSY and IN_PUSH while BUSY keep the defaulted behaviour (ignore RUN, accept pushes)?

## history
2026-11-26 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning, rtl-design-creation
