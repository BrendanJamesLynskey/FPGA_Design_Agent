# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261126-152242-3f5c/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261126-152242-3f5c/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=fir32_top tool=Vivado 2026.1
agent_run=20261126-152242-3f5c record=runs/20261126-152242-3f5c/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 8 loops, 121 turns, 5,290,559 tokens, 2537.7 s wall time, 5.11191 USD model cost (provider-reported), permission mode auto (8 distinct gated decisions listed in handover.yaml), stopped because: stage 2 visited more than 6 times; last failing gate: report gates; owned by the rtl role

## summary
The design is a 32-tap symmetric FIR filter on the KR260. Samples are pushed through a JTAG register bus into an input memory, a RUN command streams them through a pre-add plus 16-multiplier datapath on a 250 MHz clock made by an MMCM from the 25 MHz board clock, and the saturated 16-bit results are read back from an output memory. The run stopped at rtl-design-creation, which did not pass its gates (a setup path on the reset synchroniser in the post-synthesis timing report). Verification reached V2 of V3, and no routed build, power or hardware result exists. The specification and architecture were approved automatically, with no human review.
not: Not a general FIR; the 32 coefficients are fixed at build time and symmetric.; No transceiver is used and sfp_tx_disable is held at 1.; No AXI or other bus is offered; the only host path is the JTAG register bus (data/jtag_bus.sv).; Not verified on hardware, and no timing closure at 250 MHz is shown.

## state
stage=rtl vivado=2026.1 kb_pin=eaf6794 build_id=c99205ef
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Internal only, there is no reset port. rtl/reset_gen.sv holds it for RESET_CYCLES clk_25 cycles after the MMCM locks. rtl/reset_sync.sv (xpm_cdc_async_rst) derives the clk_dp reset, which asserts asynchronously and releases synchronously. Registers have initial values (reprogram model).
if clk_25 input clock, 25 MHz, pin C3 LVCMOS18: Board clock; the MMCM makes clk_dp (250 MHz) from it in rtl/fir32_top.sv.
if led output, 2 bits, F8 and E8 LVCMOS18: led[0] is BUSY and led[1] is sticky saturation since CLEAR (rtl/fir32_core.sv).
if sfp_tx_disable output, 1 bit, Y10 LVCMOS33: Constant 1.
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 read back value
reg 16 CTRL RW reset=0 0 CLEAR self-clearing, 1 RUN self-clearing
reg 20 IN_PUSH WO reset=0 15:0 sample
reg 24 OUT_POP RO reset=0 31 valid, 15:0 oldest output, read pops
reg 28 STATUS RO reset=0 0 BUSY, 15:4 input FIFO count, 31:20 output FIFO count
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs since CLEAR
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed since CLEAR
param NUM_TAPS=32 legal=fixed at 32
param UNIQUE_COEFFS=16 legal=fixed at 16
param DATA_WIDTH=16 legal=fixed at 16
param COEFF_WIDTH=16 legal=fixed at 16
param FIFO_DEPTH=1024 legal=fixed at 1024
param ROUND_CONST=16,384 legal=fixed at 16384 (0x4000)
param SHIFT=15 legal=fixed at 15
param RESET_CYCLES=16 legal=1 to 31 (5-bit counter)
param DESIGN_ID=546,570,241 legal=any 32-bit value

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml e95700bd4f: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md c6a41834f7: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 40cb4689bb: the machine-checked architecture: blocks, clocks, predicted resources
rtl/fir32_core.sv 620074f6d5: RTL written by the Designer
rtl/fir32_top.sv 255a040a9f: RTL written by the Designer
rtl/fir_datapath.sv 5751fc5991: RTL written by the Designer
rtl/lint_waivers.sv c5e87e4c38: RTL written by the Designer
rtl/reset_gen.sv 2c2a480d6e: RTL written by the Designer
rtl/reset_sync.sv 7d52a58c7e: RTL written by the Designer
rtl/xilinx_sim_stubs.sv 8ddd957da5: RTL written by the Designer
design.xdc 713c2601ca: pin, I/O standard and timing constraints
build.yaml c2b73740da: the build description read by the flow
model.py 72af5479fe: the Modeller's reference model of the visible behaviour
tests/fir_bench.py 416567c745: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py 43d59442d4: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml e75e45eeff: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/02_rtl-design-creation.html 33e7b34123: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261126-152242-3f5c/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261126-152242-3f5c/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261126-152242-3f5c/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261126-152242-3f5c/p4_fir_dsp/build/verif/sim python -m pytest -q -x runs/20261126-152242-3f5c/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py && python3 flow/verif_gates.py runs/20261126-152242-3f5c/p4_fir_dsp --runs runs/20261126-152242-3f5c/p4_fir_dsp/build/verif/sim
[heavy] rebuild the bitstream with the flow (~3min): flow/run_vivado.sh runs/20261126-152242-3f5c/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261126-152242-3f5c/summary.json 3858e9b24e
R2 build/verif/verif_gates.json 06f09538a9
R3 build/base/gates.json 395caf26ea

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 80); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build fail R3: Vivado base build; flow stages that ran: rtl, post_synth

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 cost -=5.11191 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## requirements_report
REQUIREMENTS_REPORT.md

## assumptions_not_confirmed
[high] What is the register map (offset, width, reset value and access of every register)? -> The map in registers.map: ID 0x000, BUILD 0x004, SCRATCH 0x008, CTRL 0x010, IN_PUSH 0x014, OUT_POP 0x018, STATUS 0x01C, SAT_COUNT 0x020, SAMPLES_DONE 0x024, all 32 bits, resets 0 except ID. (defaulted: nobody answered)
[high] What does a read of SAT_COUNT or SAMPLES_DONE do on overflow? -> 32-bit counters that wrap. (defaulted: nobody answered)
[high] What happens if IN_PUSH is written while BUSY? -> The push is accepted if the FIFO is not full, and it is not part of the running batch. (defaulted: nobody answered)
[high] What happens if the output FIFO would overflow during RUN? -> Not possible when the output FIFO is empty at RUN. RUN is limited to the free output space, and leftover input stays in the input FIFO. (defaulted: nobody answered)
[high] What happens if CLEAR is written while BUSY? -> CLEAR aborts the run and empties everything. (defaulted: nobody answered)
[high] What is the exact filter latency in clocks? -> Any fixed pipeline depth, since only results through the FIFO are observed. (defaulted: nobody answered)
[high] This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every register starts from its initial value), or does something restart the running design (then it needs a reset input)? -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers get initial values, control state included, and the design has no reset input. Record it in spec.yaml as reset: {model: reprogram}; a design that restarts while it runs is reset: {model: reset} with a reset port. (defaulted: nobody answered)
[medium] What do the two LEDs show? -> led[0] = BUSY, led[1] = 1 once any output has saturated since CLEAR. (defaulted: nobody answered)

## gaps
[REQ-01, REQ-02, REQ-03, REQ-06, REQ-07, REQ-08, REQ-09, REQ-19] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-11, REQ-12, REQ-38, REQ-31, REQ-32] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[REQ-14, REQ-15, REQ-16] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is pending: no flow gates result
[REQ-30] REQ-30 has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result; hardware (uart_tests) is pending: no bring-up result
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 8 questions, 0 answered and 8 defaulted
[E3] build evidence is fail: Vivado base build; flow stages that ran: rtl, post_synth
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: report gate RPT-LL-02 timing_summary_synth.rpt:u_rst/rst_reg/C->u_core/u_rsync/u_rst/arststages_ff_reg[0]/PRE: setup path u_rst/rst_reg/C to u_core/u_rsync/u_rst/arststages_ff_reg[0]/PRE (sys_clk_pin, requirement 0.0 ns) has slack -0.477 ns with 0.157 ns of net delay; with the net delay removed it is still -0.320 ns, so no placement can close it (UG949 p.200): 0 logic levels, logic delay 0.084 ns. ...
[constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 2 visited more than 6 times; last failing gate: report gates; owned by the rtl role)
[formal] formal checks were planned for REQ-23, REQ-40, REQ-33 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here, so the input-count check is done by model-compared simulation at empty, partial and full.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[coefficients] The coefficients are literals in rtl/fir_datapath.sv, not read from data/coeffs.hex via $readmemh as spec.yaml and ARCHITECTURE.md say. This run did not check that they match the file.
[filter_latency] Counting the RTL, the datapath takes 11 clk_dp cycles from v_in to v_out (rtl/fir_datapath.sv). Reads of the input memory add one more cycle, and results reach the host through the handshake CDC. No total latency was measured.
[clock_ratio] ARCHITECTURE.md describes the MMCM as VCO 1000 MHz with x40 and divide 4, and the RTL sets CLKFBOUT_MULT_F 40.0 and CLKOUT0_DIVIDE_F 4.0. spec.yaml calls it 25 MHz x 10. The RTL gives 250 MHz.
[cdc_style] spec.yaml and ARCHITECTURE.md describe async FIFOs. The RTL uses dual-clock xpm_memory_sdpram blocks plus xpm_cdc_handshake for commands and done messages (rtl/fir32_core.sv), and the CDC structure and injection checks have no result.
[reset_style] spec.yaml describes a reset port with polarity and sync_to, but the top level has no reset input and the interview chose the reprogram model. In the RTL, rst is generated internally and used synchronously on clk_25, and clk_dp logic uses a synchronised copy.
[reset_timing] The post-synthesis timing report shows a negative setup slack from u_rst/rst_reg to the clk_dp reset synchroniser's first flop (-0.477 ns), which no placement can close. This is the open failure at rtl-design-creation.
[run_semantics] RUN is ignored while BUSY and when CLEAR is also written in the same write (CLEAR has priority). RUN is also ignored if n_calc is 0. The batch is min(input count, free output space), and leftover samples stay in the input FIFO.
[clear_while_busy] CLEAR aborts the run, empties both FIFOs, zeroes counters and the sticky LED, and sends a clear message to clk_dp, which drops samples in flight and zeroes history.
[unmapped_access] Reads of any unmapped address return 0 and writes to unmapped addresses do nothing. Write-only IN_PUSH reads 0, and CTRL reads 0 because there is no read case for it.
[read_side_effects] Reading OUT_POP at 0x018 pops the oldest entry only when the output count is non-zero; an empty read returns 0 with bit 31 clear. Only a read pops.
[counters] SAT_COUNT and SAMPLES_DONE are 32-bit and wrap. They are updated when a run finishes, not per sample, so they can lag the output FIFO count.
[simulation_stubs] rtl/xilinx_sim_stubs.sv provides simulation models of the MMCM, BUFG, USR_ACCESSE2 and XPM blocks, so BUILD reads 0 and the clock ratio is 1:1 in simulation. These do not represent the real primitives.

## next_actions
1. Fix the earliest failure first, at rtl-design-creation. The setup path from the reset register in reset_gen to the clk_dp reset synchroniser is a clk_25 to clk_dp crossing with a 40 ns requirement in the report. Look at how the rst crossing is constrained and structured, then rebuild.
2. Compare the cover results with the functional coverage before any new stimulus, since functional bins show 0 of 0 and cover properties show 0 percent. Then re-run the Verilator coverage command to get line, toggle, seed and mutation results.
3. Check the literal coefficients in rtl/fir_datapath.sv against data/coeffs.hex, and decide whether the spec should say literals.
4. Once the RTL gates pass, continue with constraints, synthesis, implementation and timing closure at 250 MHz, then bring up on the board.

## open_questions
- Should the reset crossing to clk_dp be restructured, or constrained, to remove the failing synthesis path?
- Is the 11-cycle datapath depth, plus the handshake delay, acceptable as the filter latency the spec leaves open?

## history
2026-11-26 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
