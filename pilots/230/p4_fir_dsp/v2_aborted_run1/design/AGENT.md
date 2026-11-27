# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261126-132847-e69d/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261126-132847-e69d/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=fir_top tool=Vivado 2026.1
agent_run=20261126-132847-e69d record=runs/20261126-132847-e69d/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 8 loops, 220 turns, 9,679,960 tokens, 5407.2 s wall time, 7.25326 USD model cost (provider-reported), permission mode auto (17 distinct gated decisions listed in handover.yaml), stopped because: stage 1 visited more than 4 times; last failing gate: check_constraints failed

## summary
The design is a 32-tap symmetric low-pass FIR filter that uses 16 multipliers. A host pushes 16-bit samples into a 1024-deep input FIFO over a JTAG register port on the 25 MHz clock. RUN streams them through a datapath clocked at 250 MHz by an MMCM, and the results go to a 1024-deep output FIFO that the host pops. The run reached simulation level V2 of V3. It stopped in board-and-device-planning, where check_constraints failed repeatedly. Synthesis ran once and its resource gate failed. No implementation, timing, power or hardware result exists.
not: Not proven on hardware, and not timing-closed. No post-route result exists.; Not a runtime-loadable coefficient filter. The 16 unique coefficients are constants in rtl/fir_datapath.sv.; Not a design with a reset input. Resets come from reprogramming plus an internal power-up reset.; No GT transceiver is used. sfp_tx_disable is a constant output.

## state
stage=simulated vivado=2026.1 kb_pin=eaf6794 build_id=ee4e179e
gates: clarify=pass board-and-device-planning=fail rtl-design-creation=pass constraints=pass synthesis=fail implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst (internal) active-high: Generated in rtl/fir_top.sv by a 4-bit counter on clk_25 and held for 15 clocks after configuration. There is no reset port. fir_core also resets the datapath asynchronously through xpm_cdc_async_rst until the MMCM is locked, and every register has an initial value.
if clk_25 input, 25 MHz clock, pin C3 LVCMOS18: design.xdc names the port clk_25 and fir_top.sv uses it. spec.yaml names it clk25. fir_top also declares an unused input clk25 that has no pin in design.xdc.
if led output [1:0], pins F8 (led[0]) and E8 (led[1]), LVCMOS18: led[0] is BUSY and led[1] is the MMCM locked flag after synchronisation to clk25.
if sfp_tx_disable output, pin Y10 LVCMOS33: Constant 1 in rtl/fir_core.sv.
if JTAG register bus (internal) h_we, h_re, h_addr[11:0], h_wdata, h_rdata from data/jtag_bus.sv, on clk_25: Not a top-level port. It is the host access path to the register map.
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 scratch
reg 16 CTRL RW reset=0 0 CLEAR self-clearing; 1 RUN self-clearing; 31:2 reserved
reg 20 IN_PUSH WO reset=0 15:0 sample pushed
reg 24 OUT_POP RO reset=0 31 valid; 15:0 oldest output; read pops
reg 28 STATUS RO reset=0 0 BUSY; 15:4 input FIFO count; 31:20 output FIFO count
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs since CLEAR
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed since CLEAR
param NUM_TAPS=32 legal=32 only
param UNIQUE_COEFFS=16 legal=16 only
param DATA_WIDTH=16 legal=16 only
param COEFF_WIDTH=16 legal=16 only
param FIFO_DEPTH=1024 legal=1024 only
param ACC_WIDTH=38 legal=38 only
param ROUND_CONST=16,384 legal=16384 only
param SHIFT=15 legal=15 only
param DESIGN_ID=546,570,241 legal=any 32-bit value
param MMCM_MULT=40 legal=40 with a 25 MHz input
param MMCM_OUT_DIVIDE=4 legal=4 for 250 MHz

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml 06aa0b133b: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md b57c34710d: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml cb9d00fa7c: the machine-checked architecture: blocks, clocks, predicted resources
rtl/fir_core.sv 363ea7f279: RTL written by the Designer
rtl/fir_datapath.sv cd58f2cb48: RTL written by the Designer
rtl/fir_top.sv e7b6d03da1: RTL written by the Designer
rtl/jtag_bus_waivers.vlt 3a1bd79259: RTL written by the Designer
rtl/xilinx_sim_stubs.sv fa21931018: RTL written by the Designer
design.xdc 713c2601ca: pin, I/O standard and timing constraints
build.yaml dd8fdcbdb7: the build description read by the flow
model.py 7c79e312dd: the Modeller's reference model of the visible behaviour
tests/bench_fir.py 8ddc065b30: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py 39739082d9: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 82cf485b73: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/01_board-and-device-planning.html 9870e3b2d7: the review page of stage board-and-device-planning: its exit gates and their failures at the last visit
build/review/04_synthesis.html e60ae2a0f0: the review page of stage synthesis: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261126-132847-e69d/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261126-132847-e69d/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261126-132847-e69d/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261126-132847-e69d/p4_fir_dsp/build/verif/sim python -m pytest -q -x runs/20261126-132847-e69d/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py && python3 flow/verif_gates.py runs/20261126-132847-e69d/p4_fir_dsp --runs runs/20261126-132847-e69d/p4_fir_dsp/build/verif/sim
[heavy] rebuild the bitstream with the flow (~3.4min): flow/run_vivado.sh runs/20261126-132847-e69d/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261126-132847-e69d/summary.json efaf433d82
R2 build/verif/verif_gates.json 418a07ecef
R3 build/base/gates.json 74e3c9abe0

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 70); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build fail R3: Vivado base build; flow stages that ran: rtl, post_synth

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=7.25326 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## requirements_report
REQUIREMENTS_REPORT.md

## assumptions_not_confirmed
[high] Is the register map exactly the offsets in the request (0x000-0x008 common, 0x010-0x024 FIR)? -> Yes, use the map in registers.map with the offsets, widths, reset values and access of every register as in the request. (defaulted: nobody answered)
[high] What happens if the output FIFO would overflow (input count plus output count above 1024)? -> Processing stalls until the output FIFO has room (no sample lost). (defaulted: nobody answered)
[high] This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every register starts from its initial value), or does something restart the running design (then it needs a reset input)? -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers get initial values, control state included, and the design has no reset input. Record it in spec.yaml as reset: {model: reprogram}; a design that restarts while it runs is reset: {model: reset} with a reset port. (defaulted: nobody answered)
[medium] What do writes to IN_PUSH while BUSY, and RUN with an empty input FIFO, do? -> IN_PUSH while BUSY is accepted if not full; RUN with empty FIFO finishes at once with no output. (defaulted: nobody answered)
[medium] Reading OUT_POP when BUSY or STATUS counts while BUSY: are they coherent? -> Counts are the live values, synchronised to clk25 with at most a few cycles of lag. (defaulted: nobody answered)
[medium] Do CLEAR and RUN written in the same CTRL write both act? -> CLEAR wins and RUN is ignored. (defaulted: nobody answered)
[medium] What do the LEDs show? -> led[0] = BUSY, led[1] = MMCM locked. (defaulted: nobody answered)
[medium] Does RUN written while BUSY restart or queue? -> Ignored while BUSY. (defaulted: nobody answered)

## gaps
[REQ-01, REQ-02, REQ-03, REQ-06, REQ-07, REQ-08, REQ-28] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-11, REQ-14, REQ-26, REQ-27] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is fail: gate post_synth:post_synth_resources_in_range = False
[REQ-13] REQ-13 has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None
[REQ-25] REQ-25 has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is fail: gate post_synth:post_synth_resources_in_range = False; hardware (uart_tests) is pending: no bring-up result
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
[E3] build evidence is fail: Vivado base build; flow stages that ran: rtl, post_synth
[board-and-device-planning] stage board-and-device-planning did not pass its gates in this run; at its last visit: check_constraints failed FAIL
[synthesis] stage synthesis did not pass its gates in this run; at its last visit: post_synth:post_synth_resources_in_range FAIL resources: bram_tile used 0 outside the predicted [2.0, 4.0] by more than 2x (below; allowed [1.0, 8.0]) FAIL
[implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 1 visited more than 4 times; last failing gate: check_constraints failed)
[formal] formal checks were planned for REQ-05, REQ-15, REQ-18, REQ-30, REQ-31 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed so the read-latency bound is checked by the cocotb bench.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[coverage_disagreement] Functional bins show 0 of 0 and cover properties show 0 percent, so no coverage was collected. Treat the V3 coverage numbers as missing, not as a result.
[port_name] spec.yaml names the clock port clk25, but design.xdc constrains clk_25 (pin C3, period 40.00 ns) and fir_top.sv drives everything from clk_25. The unused extra input clk25 in fir_top.sv has no pin constraint. The RTL and XDC are what was built.
[reset_style] spec.yaml describes a reset from jtag_bus and an active-high rst. The RTL generates rst in fir_top.sv from a 15-clock counter and there is no reset port. The reset model is reprogram, so registers carry initial values. The reset values of the map match the spec.
[unmapped_access] Reads of unmapped addresses return 0 (default case in fir_core.sv). Writes to unmapped addresses change nothing. Writes to ID, BUILD, OUT_POP, STATUS, SAT_COUNT and SAMPLES_DONE have no effect. CTRL bits 31:2 are ignored.
[read_side_effects] A read of OUT_POP pops the FIFO when it is not empty. On an empty FIFO it returns 0 and pops nothing. h_rdata is updated only on h_re and holds its value between reads. It is registered, so it appears one clk25 cycle after h_re, inside the spec bound of 2.
[ctrl_priority] In one CTRL write, CLEAR wins and RUN is ignored. RUN is also ignored while BUSY. RUN with an empty input FIFO ends with no output. CLEAR holds the input FIFO in reset for several clk25 cycles. IN_PUSH writes made in that window wait in a 64-entry queue and are dropped only when the queue is full.
[push_when_full] IN_PUSH goes through a 64-entry queue and then the FIFO, which ignores writes when full. The spec says a push to a full FIFO is ignored. A push dropped for a full queue is also silent.
[output_backpressure] Issue stalls when the output FIFO has no room, so no result is lost. The room check uses a registered, synchronised pop count, so it is conservative.
[pipeline_latency] The spec says about 20 clk_dp cycles of filter latency. The RTL valid chain in fir_datapath.sv is 9 stages, with the history register and the FIFO read added outside it. No measurement was made.
[coefficient_source] The spec says the coefficients come from data/coeffs.hex. The RTL hard-codes them in a case table in fir_datapath.sv and does not read the file. Whether the table matches the file was not checked in this handover.
[fifo_sim_model] The benches use the behavioural stand-ins in rtl/xilinx_sim_stubs.sv for the XPM FIFOs, the CDC cells, USR_ACCESSE2 and the MMCM. USR_ACCESSE2 returns 0 there, so BUILD reads 0 in simulation. The real XPM models were not simulated.
[bram_prediction] The synthesis gate found 0 BRAM tiles against a predicted 2 to 4. The FIFOs may have been mapped to other memory, or the FIFO depth was reduced. The architecture also names xpm_cdc_array_single, which fir_core.sv does not use. Check this before anything else in synthesis.
[assumption_defaults] All 8 interview questions were defaulted with nobody answering. The defaults set the register map, output FIFO stall, the reprogram reset model, the CLEAR over RUN priority, the LED meanings and the RUN-while-BUSY behaviour. All are in the RTL as described.

## next_actions
1. Fix board-and-device-planning first: read build/review/01_board-and-device-planning.html and find why check_constraints fails. The XDC names clk_25 while spec.yaml names clk25 and fir_top.sv has an extra unused clk25 input, so start there.
2. Compare the cover results with the functional coverage before any new stimulus: 0 of 0 bins and 0 percent cover mean nothing was collected. Then re-run the Verilator coverage command and reach V3.
3. Explain the 0 BRAM tiles in synthesis (build/review/04_synthesis.html) and re-run synthesis.
4. Rebuild with flow/run_vivado.sh, then run implementation, check setup slack at 250 MHz and the DSP count. Use python -m agent resume to continue the flow.
5. Run the hardware checks with a bring-up, reading ID, BUILD, SCRATCH and an impulse response over JTAG.

## open_questions
- Should the spec follow the built port name clk_25, or should the RTL and XDC be changed to clk25?
- Is the 64-entry push queue after CLEAR acceptable, or should IN_PUSH be dropped during the CLEAR window?

## history
2026-11-26 agent run pr=-: produced by the agent graph; stages that passed: clarify, rtl-design-creation, constraints
