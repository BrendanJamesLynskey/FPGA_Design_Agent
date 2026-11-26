# AGENT p4_fir_dsp (fda-handover/1)
source: runs/20261126-015902-dd64/p4_fir_dsp/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261126-015902-dd64/p4_fir_dsp

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=fir32_top tool=Vivado 2026.1
agent_run=20261126-015902-dd64 record=runs/20261126-015902-dd64/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 2 loops, 50 turns, 1,622,442 tokens, 763.9 s wall time, 2.10816 USD model cost (provider-reported), stopped because: reply too long: no file written; the rtl role's last 2 replies were cut off at the output limit (max_tokens), and no file was written in between

## summary
The design is specified as a 32-tap symmetric low-pass FIR filter on the KR260 (xck26). Samples are pushed through a register bus behind jtag_bus into an input FIFO, a RUN command streams them through a 16-DSP datapath at 250 MHz from an MMCM, and results are popped from an output FIFO. The run stopped after the clarify and board-and-device-planning stages passed; no RTL was written, so nothing was simulated, synthesised or measured.
not: Not a runtime-loadable coefficient filter; coefficients are fixed, symmetric, and come from data/coeffs.hex.; Not an AXI4-Lite peripheral and does not use a GT transceiver channel; the SFP+ transmitter is only held disabled.; Not built or verified; there is no RTL, bitstream, or timing, power or resource result.

## state
stage=spec vivado=2026.1 kb_pin=6185830 build_id=None
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=not-run constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Per spec.yaml it is driven by jtag_bus, synchronous to clk, and synchronised into clk_dsp with MMCM lock gating the datapath reset. No RTL exists to confirm this.
if clk25 input, 1 bit, 25 MHz board clock: spec.yaml names it clk25 but design.xdc constrains and places a port named clk_25 on pin C3 with a 40 ns period.
if led output, 2 bits: design.xdc places led[0] on F8 and led[1] on E8, LVCMOS18. Per spec, led[0] shows BUSY and led[1] a heartbeat.
if sfp_tx_disable output, 1 bit: design.xdc places it on Y10, LVCMOS33. Per spec it is constant 1 and no GT channel is used.
reg 0 ID RO reset=546570241 31:0 design ID
reg 4 BUILD RO reset=0 31:0 USR_ACCESS word
reg 8 SCRATCH RW reset=0 31:0 read back what was written
reg 16 CTRL RW reset=0 0 CLEAR self-clearing; 1 RUN self-clearing
reg 20 IN_PUSH WO reset=0 15:0 sample
reg 24 OUT_POP RO reset=0 31 valid; 15:0 oldest output; read pops
reg 28 STATUS RO reset=0 0 BUSY; 15:4 input FIFO count; 31:20 output FIFO count
reg 32 SAT_COUNT RO reset=0 31:0 saturated outputs since CLEAR
reg 36 SAMPLES_DONE RO reset=0 31:0 samples processed since CLEAR
param TAPS=32 legal=fixed at 32 by the symmetric structure
param UNIQUE_COEFFS=16 legal=TAPS/2
param DATA_WIDTH=16 legal=16 (signed)
param COEFF_WIDTH=16 legal=16 (signed Q1.15)
param FIFO_DEPTH=1024 legal=1024 as specified; the 12-bit STATUS count fields bound any larger depth
param SHIFT=15 legal=15 (Q1.15 coefficients); changing it also changes ROUND_CONST
param ROUND_CONST=16,384 legal=16384 (0x4000, half of 2^SHIFT)
param ID_VALUE=546,570,241 legal=546570241 (0x20940001)
param READ_LATENCY_CYCLES=2 legal=2 or fewer clk cycles

## files (paths under the design directory are relative to it)
spec.md 7efe165f5f: the request the run started from
spec.yaml 81de32a5a7: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md 2c2d7bd8bd: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml e3aff21d5c: the machine-checked architecture: blocks, clocks, predicted resources
design.xdc 713c2601ca: pin, I/O standard and timing constraints
model.py 321f3d9767: the Modeller's reference model of the visible behaviour
tests/bench_p4_fir_dsp.py 649d85e7c7: the Verifier's cocotb benches and pytest entries
tests/test_p4_fir_dsp_rtl.py 086ee981cd: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 2f86b26c70: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261126-015902-dd64/p4_fir_dsp
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261126-015902-dd64/p4_fir_dsp "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261126-015902-dd64/p4_fir_dsp/tests/test_p4_fir_dsp_rtl.py
[heavy] rebuild the bitstream with the flow: flow/run_vivado.sh runs/20261126-015902-dd64/p4_fir_dsp base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261126-015902-dd64/summary.json 0e4158237b

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 7 questions, 0 answered and 7 defaulted

## measured
M1 cost -=2.10816 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 7 questions, 0 answered and 7 defaulted
[rtl-design-creation, constraints, synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (reply too long: no file written; the rtl role's last 2 replies were cut off at the output limit (max_tokens), and no file was written in between)
[formal] formal checks were planned for REQ-06, REQ-32, REQ-13, REQ-33, REQ-25 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here, so the read-latency property is checked in simulation.
[resources, timing, power] (each of these) not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[clock_name] spec.yaml and ARCHITECTURE.md name the board clock clk25, but design.xdc constrains a port named clk_25 (period 40.00 ns). The XDC is what was built; the top-level port name must match it or the constraint will not bind.
[rtl-absent] No RTL exists, so the reset style, reset values, read latency and filter pipeline depth are spec intent only. Spec leaves the filter pipeline depth to the implementation.
[busy-and-full-behaviour] Defaulted answers, not built. RUN while BUSY is ignored. IN_PUSH while BUSY is accepted if the FIFO is not full and is held for the next RUN. CLEAR during BUSY aborts the run. A result arriving at a full output FIFO is dropped, though SAMPLES_DONE still counts it.
[register-access] Per spec, unmapped addresses (including 0x00C and the gaps between the mapped registers) read 0 and ignore writes. OUT_POP on an empty FIFO reads 0, and a valid read pops as a side effect. IN_PUSH on a full FIFO is ignored. CTRL bits read back 0 the clock after the write.
[snapshot] Each register read is a single-register snapshot; STATUS counts, SAT_COUNT and SAMPLES_DONE are not read atomically together.
[build_sim] BUILD reads USR_ACCESSE2, which does not exist in simulation; the behavioural model returns 0 or a testbench-set word.
[unread_sources] spec.yaml records that data/jtag_bus.sv and data/coeffs.hex were not readable when the spec was written, so their contents come only from the description in spec.md.
[led1_proposal] The led[1] heartbeat is a proposal in the spec, not a requirement.

## next_actions
1. Re-run the rtl-design-creation stage (python -m agent resume) with the RTL split into several smaller files, so that no reply is cut off at the output limit.
2. Once RTL exists, run the Verifier's simulation tests and compare the cover results with the functional coverage before adding any stimulus.
3. Resolve the clk25 versus clk_25 naming between the spec and design.xdc, then run synthesis and implementation and check 250 MHz timing, the 16 DSP count and the read latency against the spec.
4. Replace the planned formal checks with simulation checks or install SymbiYosys, and confirm the readable jtag_bus.sv and coeffs.hex contents against the spec.

## open_questions
- Should the clock port be named clk25 as in the spec or clk_25 as in design.xdc?

## history
2026-11-26 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
