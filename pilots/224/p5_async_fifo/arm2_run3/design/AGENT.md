# AGENT p5_async_fifo (fda-handover/1)
source: runs/20261126-021747-15f3/p5_async_fifo/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh runs/20261126-021747-15f3/p5_async_fifo

## identity
kind=agent-run produced_by=agent part=xck26-sfvc784-2LV-c board=kr260 top=top tool=Vivado 2026.1
agent_run=20261126-021747-15f3 record=runs/20261126-021747-15f3/summary.json
run: model claude-sonnet-5-5 (deepagents harness), 9 loops, 277 turns, 11,823,092 tokens, 5887.3 s wall time, 7.31545 USD model cost (provider-reported), stopped because: stage 3 visited more than 4 times; last failing gate: post_synth:post_synth_exceptions_clean (EXC-IGNORED design.xdc:33 set_output_delay -clock 

## summary
The design writes a 32-bit PRBS-31 stream at the clk_25 rate into a 512-word asynchronous FIFO. A reader in the gt_refclk domain (SFP+ MGTREFCLK0, 156.25 MHz) checks every word against its own PRBS copy and counts errors and underflows. A host reads and writes the registers over jtag_bus, with counters latched by SNAPSHOT. The run stopped at the constraints stage, whose exit gate failed on an ignored output-delay exception in design.xdc, and verification reached V2 of V3. A Vivado base build is recorded as failed and there is no board result.
not: Not a transceiver design: no GT channel is used, only the reference clock buffer, and sfp_tx_disable is held at 1.; Not hardware-proven: no board result exists, and the build gates did not pass.; Not a general FIFO IP: depth, width and PRBS polynomial are fixed by the parameters and the RTL.

## state
stage=simulated vivado=2026.1 kb_pin=6185830 build_id=69527cd9
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=pass constraints=fail synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk clk_25 25MHz
rst rst active-high: Internal power-on reset in top.sv, held for 8 clk_25 cycles after configuration. It resets the clk_25 logic synchronously and enters the gt_refclk domain through xpm_cdc_async_rst with 4 flops (reset_gen.sv).
if clk_25 input clock, C3, LVCMOS18, 25 MHz: Writer domain, register port and jtag_bus clock.
if gt_refclk_p / gt_refclk_n differential input clock, Y6 / Y5: SFP+ MGTREFCLK0 through IBUFDS_GTE4 and BUFG_GT; reader domain at 156.25 MHz (6.4 ns in design.xdc).
if led[1:0] output, F8 and E8, LVCMOS18: led[0] is RUN. led[1] is set when DATA_ERRS or UNDERFLOWS is non-zero (synchronised) or the writer-side OVERFLOWS count is non-zero.
if sfp_tx_disable output, Y10, LVCMOS33: Constant 1 (laser off).
reg 0 ID RO reset=546635777 [31:0] design ID
reg 4 BUILD RO reset=0 [31:0] USR_ACCESS word
reg 8 SCRATCH RW reset=0 [31:0] read back value
reg 16 CTRL RW reset=0 [0] RUN, [1] SLOW_READ, [2] CLEAR self-clearing only while RUN=0, [3] INJECT self-clearing
reg 20 WORDS_W RO reset=0 [31:0] words written (snapshot)
reg 24 WORDS_R RO reset=0 [31:0] words read and checked (snapshot)
reg 28 DATA_ERRS RO reset=0 [31:0] mismatched words (snapshot)
reg 32 OVERFLOWS RO reset=0 [31:0] (snapshot)
reg 36 UNDERFLOWS RO reset=0 [31:0] (snapshot)
reg 40 STALL_W RO reset=0 [31:0] writer clocks held off (snapshot)
reg 44 OCC_MAX RO reset=0 [31:0] highest fill in words (snapshot)
reg 48 SNAPSHOT WO reset=0 [31:0] any write latches 0x014 to 0x02C; reads 0
param DESIGN_ID=546,635,777 legal=any 32-bit value
param FIFO_DEPTH_WORDS=512 legal=512 only
param DATA_WIDTH=32 legal=32 only
param PRBS_SEED=2,147,483,647 legal=nonzero 31-bit value
param SLOW_READ_DIV_CYCLES=8 legal=1 to 8 (the slow counter is 3 bits)
param PTR_WIDTH=9 legal=9 only
param COUNTER_WIDTH=32 legal=32 only

## files (paths under the design directory are relative to it)
spec.md feff955150: the request the run started from
spec.yaml af7ed601a2: the specification the Clarifier wrote, approved automatically with no human review
ARCHITECTURE.md 02d6ea0dca: the architecture note, accepted automatically before any RTL (no human review)
architecture.yaml 55329d1c16: the machine-checked architecture: blocks, clocks, predicted resources
rtl/async_fifo.sv 4339439a54: RTL written by the Designer
rtl/p5_async_fifo_core.sv bb7aaf19b8: RTL written by the Designer
rtl/p5_async_fifo_wrap.sv 61102a0c21: RTL written by the Designer
rtl/prbs31_word.sv 1866c37453: RTL written by the Designer
rtl/reset_gen.sv dd457c4dee: RTL written by the Designer
rtl/top.sv 6fb1c1f16a: RTL written by the Designer
rtl/xilinx_sim_stubs.sv bb0adc529f: RTL written by the Designer
design.xdc 0183a5e5b1: pin, I/O standard and timing constraints
build.yaml fb2c2ed2dd: the build description read by the flow
model.py 14b3f975c5: the Modeller's reference model of the visible behaviour
tests/bench_p5_async_fifo.py 4fed0cbe8a: the Verifier's cocotb benches and pytest entries
tests/test_p5_async_fifo_rtl.py f0e100cfeb: the Verifier's cocotb benches and pytest entries
verif/testplan.yaml 1de03b7793: the test plan and mutant list read by the verification gates
verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
build/review/03_constraints.html c45cb41eab: the review page of stage constraints: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh runs/20261126-021747-15f3/p5_async_fifo
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume runs/20261126-021747-15f3/p5_async_fifo "<change request>"
run the Verifier's simulation tests: python -m pytest -q runs/20261126-021747-15f3/p5_async_fifo/tests/test_p5_async_fifo_rtl.py
re-run the Verilator coverage simulation and the verification gates (line, toggle, functional and cover results): SIM=verilator FDA_COVERAGE=1 FDA_SIM_RESULTS_DIR=runs/20261126-021747-15f3/p5_async_fifo/build/verif/sim python -m pytest -q -x runs/20261126-021747-15f3/p5_async_fifo/tests/test_p5_async_fifo_rtl.py && python3 flow/verif_gates.py runs/20261126-021747-15f3/p5_async_fifo --runs runs/20261126-021747-15f3/p5_async_fifo/build/verif/sim
[heavy] rebuild the bitstream with the flow (~5.4min): flow/run_vivado.sh runs/20261126-021747-15f3/p5_async_fifo base

## records (path sha256-prefix; claims below cite R<n>)
R1 runs/20261126-021747-15f3/summary.json f13c98c695
R2 build/verif/verif_gates.json 3eaa6ec9ae
R3 build/base/gates.json c488a22f01

## evidence
E1 review partial R1: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 7 questions, 0 answered and 7 defaulted
E2 simulation partial R2: verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V2; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 90); toggle pct not measured (needs 75); mutation score pct not measured (needs 70); cdc structure clean missing (needs no unsafe crossing); cdc injection clean missing (needs pass); no board result (V-HW) is recorded
E3 build fail R3: Vivado base build; flow stages that ran: rtl, post_synth, post_place, post_route, bitstream

## measured
M1 verification -=3 R2#stages.V3.checks.seeds_run.value: simulation seeds run | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran
M2 verification -=not measured % R2#stages.V3.checks.line_pct.value: line coverage | ditto
M3 verification -=not measured % R2#stages.V3.checks.toggle_pct.value: toggle coverage | ditto
M4 verification -=0.0 (0/0) R2#stages.V3.checks.functional_bins_pct.value: functional coverage bins hit | ditto
M5 verification -=0.0 % R2#stages.V3.checks.cover_properties_pct.value: cover properties hit | ditto
M6 timing wns=2.624 ns R3#timing.wns_ns: worst setup slack after routing | post-route, the constrained clock of design.xdc
M7 timing whs=0.012 ns R3#timing.whs_ns: worst hold slack after routing | post-route
M8 resources lut=332 R3#utilization.lut: slice LUTs used | post-route utilization
M9 resources ff=1200 R3#utilization.ff: flip-flops used | ditto
M10 resources bram_tile=0.5 R3#utilization.bram_tile: block RAM tiles used | ditto
M11 resources dsp=0 R3#utilization.dsp: DSP slices used | ditto
M12 power power=0.365 W R3#power.total_w: total on-chip power, vectorless estimate | report_power, vectorless (no switching activity file), default environment
M13 cost -=7.31545 USD R1#cost_usd: model cost of the run, provider-reported | every role and the interview oracle, as the run summary records it

## gaps
[REQ-01, REQ-02, REQ-03, REQ-11, REQ-12, REQ-13, REQ-17, REQ-18, REQ-20, REQ-25, REQ-34] (each of these) has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-07, REQ-26, REQ-27, REQ-30] (each of these) has no passing evidence for every proof method: analysis (post_synth:post_synth_resources_in_range) is pending: no flow gates result
[REQ-09] REQ-09 has no passing evidence for every proof method: hardware (ila_captures) is pending: no bring-up result
[REQ-28, REQ-29, REQ-36] (each of these) has no passing evidence for every proof method: analysis (post_route:setup) is pending: no flow gates result
[REQ-31] REQ-31 has no passing evidence for every proof method: formal (post_route:setup) is pending: re-planned from formal to analysis (SymbiYosys is not installed so the Gray pointer crossing is reviewed by analysis.): no flow gates result; analysis (post_route:setup) is pending: no flow gates result
[E1] review evidence is partial: the specification and the architecture were approved automatically, with no human review (review off; the interview oracle claude-sonnet-5-5 only answered the interview questions); the interview asked 7 questions, 0 answered and 7 defaulted
[E3] build evidence is fail: Vivado base build; flow stages that ran: rtl, post_synth, post_place, post_route, bitstream
[constraints] stage constraints did not pass its gates in this run; at its last visit: post_synth:post_synth_exceptions_clean (EXC-IGNORED design.xdc:33 set_output_delay -clock [get_clocks sys_clk_pin] -max 2.0 $STATUS_OUT Position=8 From=[get_clocks gt_refclk] Through=* To=[get_clocks sys_clk_pin] Setup=max_dpo=6.4 Hold=- Status=Totally overridden path by FP 11 - DPO 12 - DPO 16) FAIL Warnings (recorded, not gates) stage warning value note post_route async_clock_groups_review score ...
[synthesis, implementation, timing-closure, power-closure, drc-closure, configuration-and-debug] stage (each of these) was not run: the run stopped before this stage (stage 3 visited more than 4 times; last failing gate: post_synth:post_synth_exceptions_clean (EXC-IGNORED design.xdc:33 set_output_delay -clock )
[formal] formal checks were planned for REQ-06, REQ-12, REQ-13, REQ-21, REQ-31, REQ-35 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed so the read-response timing is checked by simulation.
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[cover_vs_functional] The draft shows functional bins at 0 of 0 and cover properties at 0 percent; the two coverage results must be compared before any new stimulus.
[unmapped_access] In p5_async_fifo_core.sv unmapped read addresses return 0 and writes to them change nothing. CTRL (0x010) reads back only RUN and SLOW; CLEAR and INJECT always read 0. SNAPSHOT (0x030) and other addresses read 0.
[read_latency] h_rdata is registered on h_re in p5_async_fifo_core.sv, so it is valid 1 clk_25 cycle after h_re and holds until the next h_re. This is within the spec's promise of 2 cycles. It is not measured by the flow.
[ctrl_write_priority] Every write to CTRL replaces RUN and SLOW from bits 0 and 1. CLEAR (bit 2) acts only if the same write has RUN=0 and the current RUN is 0; a write that sets RUN and CLEAR together is ignored for CLEAR. CLEAR also holds the writer off for 6 further clk_25 cycles and the reader for 8 gt_refclk cycles. After reset the reader waits 8 cycles. INJECT toggles a flag that flips bit 0 of the next word read.
[clear_semantics] CLEAR zeroes the writer-side counters at once and the reader counters through a CDC event. The snapshot registers are not cleared by CLEAR; only reset clears them.
[run_fall] Clearing RUN stops the writer at once. The reader keeps draining and checking the remaining words, because its enable does not depend on RUN. This matches the defaulted interview answer. The spec text says the reader acts while RUN is 1, so the RTL differs.
[snapshot_latency] SNAPSHOT is a toggle event crossing clk_25 to gt_refclk, then a 96-bit handshake back. Snapshot values arrive several clk_25 cycles after the write and the RTL gives no fixed bound. The read-side counters (WORDS_R, DATA_ERRS, UNDERFLOWS) come from the reader and the writer counters are sampled at arrival, so the seven values are not captured at one instant. This differs from the spec's single-instant claim.
[occ_max] OCC_MAX is computed in the writer domain from the synchronised read pointer, so it is a conservative upper estimate (fill after the current write). It is not updated during the CLEAR hold.
[led_spec] led[1] in the RTL covers DATA_ERRS, UNDERFLOWS (via the reader flag) and OVERFLOWS, as the defaulted interview answer says. Overflow cannot occur because the writer is gated by full, so OVERFLOWS stays 0 unless the gating changes.
[spec_overflow] OVERFLOWS counts w_en && w_full in async_fifo.sv, but the core drives w_en with do_w (already gated by not full), so the FIFO-level overflow never fires. Writes held off by a full FIFO are counted in STALL_W instead. The spec says OVERFLOWS counts writes attempted while full.
[spec_stall_xdc] design.xdc:33 area: output delays on led and sfp_tx_disable (lines near the end) are overridden by the set_max_delay from sys_clk_pin to gt_refclk, which the exception gate reports as ignored. The spec asked for no output delay; the XDC adds one only to make the outputs constrained.
[sim_stubs] Simulation uses behavioural stand-ins for the XPM and GT primitives (xilinx_sim_stubs.sv). USR_ACCESSE2 reads 0 in simulation, so BUILD is only checkable on hardware.
[assumption_decisions] The spec and architecture were approved automatically, and all 7 interview answers were defaults. Behaviours such as the INJECT bit and the LED meaning come from those defaults.

## next_actions
1. Fix the constraints-stage failure first: the set_output_delay lines on led and sfp_tx_disable (design.xdc:33) are reported as ignored, overridden by the sys_clk_pin to gt_refclk max delay. Remove or narrow that exception, then run python -m agent resume with a change request.
2. Compare the cover results with the functional coverage before any new stimulus; functional bins show 0 of 0 and cover properties 0 percent, so the checkers and the bins may not be wired to the benches.
3. Re-run the Verilator coverage simulation and the verification gates, then close V3 (line, toggle, mutation score, CDC structure and injection checks).
4. When the flow reaches the build again, re-run the Vivado base build and read timing, resources and power from the new gates.json; publish no number from the recorded build.
5. Decide how OVERFLOWS and the snapshot instant should behave (see the gaps spec_overflow and snapshot_latency), then change the spec or the RTL.
6. Bring the design up on the KR260 and collect the hardware results that the requirements list as pending.

## open_questions
- Should OVERFLOWS count writes attempted while full, as the spec says, or stay at the FIFO-level count that the RTL cannot raise?
- Is a single-instant snapshot required across the two clocks, or is a coherent handshake copy acceptable?
- Which value of SLOW_READ_DIV_CYCLES did the benches run, and was the spec's value of 8 simulated?

## history
2026-11-26 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning, rtl-design-creation
