# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261125-174731-a2e5/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261125-174731-a2e5/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=fir32_top tool=Vivado 2026.1
agent_run=20261125-174731-a2e5 record=runs/20261125-174731-a2e5/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 7 loops, 245 turns, 10,232,224 tokens, 5773.6 s wall time, 7.22547 USD model cost (provider-reported), stopped because: stage 3 visited more than 4 times; last failing gate: none recorded

## summary
A 32-tap symmetric low-pass FIR filter with 16-bit samples, built for the K26 on the KR260. A host pushes samples through a JTAG register bus into a 1024-sample input FIFO, writes RUN, and pops the saturated, rounded 16-bit results from an output FIFO. The datapath runs at 250 MHz from an MMCM on the 25 MHz board clock and uses 16 DSP multipliers through coefficient symmetry. The run reached simulation level V2 of V3 against the Modeller's model. It stopped at synthesis, whose gates failed. Nothing was implemented or measured on a board.
not: Not an AXI design. The register port is the supplied jtag_bus simple port.; Not a runtime-programmable filter. The 16 unique coefficients are fixed in rtl/fir_datapath.sv.; Not timing-closed, power-checked or run on hardware. No Vivado resource, timing or power figure is recorded.; Uses no GT transceiver. sfp_tx_disable is a plain output held at 1.

## state
stage=simulated vivado=2026.1 kb_pin=6185830 build_id=68b24bea
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=pass constraints=pass synthesis=fail implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: rtl/reset_gen.sv makes it, not jtag_bus as the spec says. A power-on counter holds rst_bus for 15 clk_25 cycles, and rst_dp is released synchronously by xpm_cdc_async_rst while the MMCM is unlocked or rst_bus is high. The reset is synchronous inside each domain. Register reset values are in the register table.
if clk_25 input clock, pin C3 LVCMOS18, 40 ns period in design.xdc: Board clock. It is the bus clock and the MMCM input.
if led output [1:0], F8 and E8 LVCMOS18: led[0] is BUSY delayed by three clk_bus cycles and led[1] is output FIFO not empty. This is an assumption of the run, since the request gave no LED function.
if sfp_tx_disable output, Y10 LVCMOS33: Constant 1 (fir32_core.sv).
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 scratch
reg 16 CTRL RW reset=0 0 CLEAR self-clearing; 1 RUN self-clearing; others 0
reg 20 IN_PUSH WO reset=0 15:0 sample pushed
reg 24 OUT_POP RO reset=0 31 valid; 15:0 oldest output; read pops
reg 28 STATUS RO reset=0 0 BUSY; 15:4 input count; 31:20 output count; rest 0
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed
param NUM_TAPS=32 legal=32 only
param DATA_WIDTH=16 legal=16 only
param COEFF_WIDTH=16 legal=16 only
param ACC_WIDTH=40 legal=40 only
param FIFO_DEPTH=1024 legal=1024 only
param ROUND_CONST=16,384 legal=16384 only
param SHIFT=15 legal=15 only
param DESIGN_ID=546,570,241 legal=any 32-bit value

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml da7565ea4f: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md ed2e94f11c: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml d658923cd0: the machine-checked architecture: blocks, clocks, predicted resources
rtl/fir32_core.sv b53cbb0094: RTL written by the Designer
rtl/fir32_core_wrap.sv 4643154f99: RTL written by the Designer
rtl/fir32_top.sv a6a4d453ea: RTL written by the Designer
rtl/fir_datapath.sv b7aa531507: RTL written by the Designer
rtl/in_fifo.sv 4f5dfcaf07: RTL written by the Designer
rtl/lint_waivers.sv a78b4567f7: RTL written by the Designer
rtl/out_fifo.sv 813422d91a: RTL written by the Designer
rtl/reset_gen.sv 2001039e6a: RTL written by the Designer
rtl/xilinx_sim_stubs.sv 0593810d15: RTL written by the Designer
design.xdc a2f0475f39: pin, I/O standard and timing constraints
build.yaml d76fdc7bec: the build description read by the flow
model.py 8f287f375d: the Modeller's reference model of the visible behaviour
tests/fir_bench.py e38825c834: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py 65b2b8364f: the Verifier's cocotb benches and pytest entries
verif/mutants.yaml 59fcc28749: the test plan and mutant list read by the verification gates
verif/testplan.yaml 0074618d2b: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/04_synthesis.html 868ee819a9: the review page of stage synthesis: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261125-174731-a2e5/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261125-174731-a2e5/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261125-174731-a2e5/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261125-174731-a2e5/p4_fir_dsp/build/verif/sim python -m pytest -q -x runs/20261125-174731-a2e5/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py && python3 flow/verif_gates.py runs/20261125-174731-a2e5/p4_fir_dsp --runs runs/20261125-174731-a2e5/p4_fir_dsp/build/verif/sim
[heavy] rebuild the bitstream with the flow (~2.2min): flow/run_vivado.sh runs/20261125-174731-a2e5/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261125-174731-a2e5/summary.json 522c0e2a92
R2 build/verif/verif_gates.json 3b23d166af
R3 build/base/gates.json b7dd51f0ae

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 6 questions, 0 answered and 6 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 80); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build pass R3: Vivado base build; flow stages that ran: rtl

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=7.22547 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-02, REQ-03, REQ-30, REQ-07, REQ-08, REQ-09, REQ-18, REQ-25] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-11, REQ-26, REQ-27, REQ-28] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is not run (the stage that makes this evidence did not run): gate post_synth:post_synth_resources_in_range = None
[REQ-13, REQ-35, REQ-29] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 6 questions, 0 answered and 6 defaulted
[synthesis] stage synthesis did not pass its gates in this run; at its last visit: post_synth:post_synth_cdc_no_critical FAIL post_synth:post_synth_resources_in_range FAIL resources: bram_tile used 0 outside the predicted [2.0, 4.0] by more than 2x (below; allowed [1.0, 8.0]) FAIL
[implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 3 visited more than 4 times; last failing gate: none recorded)
[formal] formal checks were planned for REQ-06, REQ-31, REQ-14, REQ-32, REQ-16, REQ-34, REQ-25 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed so the property is checked by a directed simulation test.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[fir_latency] The spec asks for a pipeline depth of about 8 to 12 clk_dp cycles. Counting from fir_datapath.sv, LAT is 9 cycles from accept (the input FIFO read) to out_wr_en. The first result is readable after the output FIFO crossing, which adds further clocks that the RTL does not bound.
[bus_read_latency] In fir32_core.sv h_rdata is a register loaded on the clock after h_re, so one bus cycle in the core. The spec allows 2. The delay inside jtag_bus.sv was not counted. h_rdata holds its value until the next h_re.
[unmapped_access] Decoded read addresses are 0x000, 0x004, 0x008, 0x018, 0x01C, 0x020 and 0x024. Any other address reads 0, including CTRL (0x010) and IN_PUSH (0x014). Writes are decoded only for SCRATCH, CTRL and IN_PUSH, and all other writes, including writes to RO registers, are ignored.
[ctrl_priority] A CTRL write with bit 0 set does CLEAR and ignores bit 1, so writing 3 does not RUN. CLEAR also holds the input FIFO in reset for 16 clk_bus cycles and the output FIFO for 64 clk_dp cycles, and a RUN issued in that window is dropped. IN_PUSH writes are ignored while the input FIFO is in reset.
[run_edge_cases] RUN is ignored while busy or when the input FIFO is empty. It takes min(input count, output free space) samples, taken from the FIFO levels as they stand at the RUN. CLEAR during a run aborts it. BUSY stays high for 64 clk_dp cycles after the last result, and led[0] lags BUSY by three more clk_bus cycles.
[reset_values] SCRATCH, h_rdata and the counters reset to 0. Counters and history are cleared by reset and by CLEAR. The histories of the two pending-push counters that guard the input FIFO level are cleared by reset only.
[status_counts] STATUS counts cross clock domains and may lag. The input count is the write-side count and the output count is the read-side count. The input push limit adds the pushes of the last 4 clocks to the count so that 1024 is not exceeded. Pushing to a full FIFO is dropped by this check.
[spec_vs_rtl] The spec says the reset comes from jtag_bus, coefficients come from data/coeffs.hex, and the parameters are adjustable. In the RTL (reset_gen.sv, fir_datapath.sv, fir32_core.sv) the reset is a power-on counter plus MMCM lock, the coefficients are literals and the parameters are fixed. The RTL is what was built.
[unsigned_samples] fir_datapath.sv zero-extends samples in the pre-add, so they are treated as unsigned 16-bit words. The comment says this matches the reference model, but the spec does not say whether samples are signed. Check against model.py and the request.
[bram_zero] The architecture predicts 2 to 4 BRAM36 for the two FIFOs, but the synthesis gate reports 0 BRAM tiles used. The cause is not recorded. The XPM FIFOs in in_fifo.sv and out_fifo.sv request block memory.
[build_sim_value] BUILD reads 0 in simulation because the stub USR_ACCESSE2 returns 0. The real word is only seen on hardware.
[extra_clocks] design.xdc declares jtag_tck (100 ns) and usr_cclk (10 ns) clocks and puts them in asynchronous groups with sys_clk_pin. The spec lists neither. LEDs and sfp_tx_disable are false-pathed.

## next_actions
1. Open build/review/04_synthesis.html and fix the synthesis gate failures first. These are the CDC critical warnings and the BRAM count of 0 against the predicted 2 to 4. Then re-run synthesis, since the run stopped after more than 4 visits to this stage.
2. Get the V3 verification checks to run. Line, toggle and mutation score are not measured, and the functional bins report 0 of 0 and the cover properties 0 percent, so first compare the cover results with the functional coverage. Then re-run the verification gates with the command listed.
3. Decide the sample sign convention (unsigned in the RTL) against the request and model.py, and fix whichever is wrong.
4. Re-run python -m agent resume once the flow reaches the build again, to take resource, timing and power numbers. Publish none until then.
5. Run the hardware bring-up for the REQs that name it, and a human review of the spec and architecture.

## open_questions
- Should the input samples be signed? The RTL treats them as unsigned and the spec is silent.
- Why does synthesis report 0 BRAM tiles for the two FIFOs?

## history
2026-11-25 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning, rtl-design-creation, constraints
