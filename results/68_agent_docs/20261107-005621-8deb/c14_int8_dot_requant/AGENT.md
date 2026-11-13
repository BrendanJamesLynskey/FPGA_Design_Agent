# AGENT c14_int8_dot_requant (fda-handover/1)
source: results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant

## identity
kind=agent-run produced_by=agent part=xc7a100tcsg324-1 board=nexys_a7_100t top=c14_int8_dot_requant_top tool=Vivado 2026.1
agent_run=20261107-005621-8deb record=results/68_agent_docs/20261107-005621-8deb/summary.json

## summary
The design takes eight signed 8-bit activations and eight signed 8-bit weights, a signed 32-bit bias, an unsigned 16-bit multiplier, a 5-bit shift and a relu bit, all loaded through registers. A write to GO runs a pipelined computation: acc is the sum of the eight products plus bias, the scaled value is acc times mult divided by two to the power shift (rounded to nearest, exact halves towards plus infinity), and y is that value clamped to -128..127, or to 0..127 when relu is set. The registers are reached through the UART test shell at 115200 baud (shell/PROTOCOL.md version 1.0). LED0 shows the READY flag. The design uses one clock, CLK100MHZ, and a synchronous reset derived from CPU_RESETN. The run got as far as RTL and the first verification stages. The Clarifier's specification was signed off and board and device planning passed. The RTL stage did not pass its gates. Simulation evidence reached V2 but the run asked for V3, and five cover properties were never hit. The run stopped because stage 2 had been visited too often. Constraints, synthesis, implementation, timing, power, DRC and bring-up were not run. The only Vivado build (stages rtl and post_synth) used an earlier release than 2026.1. The design has no measured resources, timing, power or latency.
not: Not a general matrix or convolution engine. It computes one eight-element dot product per GO and nothing else.; Not safe against operand writes while a result is being computed. The run assumed this is not required.; Not defined for shift outside 1..31, for weights of -128, or for an acc that overflows 32 bits. None of these is tested.; Not a clock-domain-crossing design. There is a single clock, and no MMCM or PLL is used.; Not proven on hardware. No bring-up result exists.

## state
stage=rtl vivado=2026.1 kb_pin=1fc7ed8 build_id=b27eac2c
gates: clarify=pass board-and-device-planning=pass rtl-design-creation=fail constraints=not-run synthesis=not-run implementation=not-run timing-closure=not-run power-closure=not-run drc-closure=not-run configuration-and-debug=not-run

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: Board CPU reset button (pin C12), asynchronous. It goes through reset_sync into an active-high synchronous reset used by the shell, the register block and the core. The reset clears the operand registers, bias, mult, the READY flag, the GO pulse, the core's y, acc and done, and the read-data register. CTRL resets to shift 1 and relu 0. The core's pipeline data registers are not reset, only its valid bits. rtl/reset_sync.sv in this design is an intentionally empty file, and the design uses shell/rtl/reset_sync.sv instead, which was not reviewed in this run.
if CLK100MHZ clock input, 100 MHz board oscillator (pin E3): Single clock domain for the shell and the arithmetic. The XDC creates clock sys_clk_pin with a 10 ns period.
if UART_TXD_IN serial input, host to FPGA (pin C4): USB-UART at 115200 baud, 8N1. Asynchronous, synchronised inside the shell. design.xdc gives it a nominal input delay only so that it has a defined arrival time. doc=shell/PROTOCOL.md
if UART_RXD_OUT serial output, FPGA to host (pin D4): USB-UART transmit side of the shell. design.xdc gives it a nominal output delay. doc=shell/PROTOCOL.md
if LED0 LED output (pin H17), the READY flag: In the RTL and XDC the port is the one-bit bus LED[0] (top port LED, declared [0:0]), not a scalar named LED0. The spec names it LED0.
param CLKS_PER_BIT=868 legal=Positive integer equal to the clock frequency divided by the baud rate. 868 gives 115200 baud at 100 MHz. Any other value changes the baud rate.
param TIMEOUT_CYCLES=100,000,000 legal=Positive integer number of CLK100MHZ cycles. It is the shell's timeout; see shell/PROTOCOL.md for its meaning.
param BUILD_STAMP=0 legal=Any 32-bit value.
param DESIGN_ID=DOTQ legal=Fixed. It is the 32-bit value 0x444F5451 (ASCII D,O,T,Q) and cannot be changed from outside.

## files
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/spec.md 811b45683a: the request the run started from
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/spec.yaml 021c577206: the signed-off specification written by the Clarifier
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/ARCHITECTURE.md faac760747: the architecture note approved before any RTL
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/architecture.yaml 9f1e645344: the machine-checked architecture: blocks, clocks, predicted resources
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/c14_int8_dot_requant_top.sv 76b83756ea: RTL written by the Designer
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/dotq_core.sv e64485f983: RTL written by the Designer
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/dotq_regs.sv 917bee15a9: RTL written by the Designer
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/reset_sync.sv d37a35dba1: RTL written by the Designer
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/design.xdc 56a8767e19: pin, I/O standard and timing constraints
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build.yaml c11f5ef0f7: the build description read by the flow
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/model.py 5f4842bfdf: the Modeller's reference model of the visible behaviour
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/tests/c14_bench.py 899941e8db: the Verifier's cocotb benches and pytest entries
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/tests/test_c14_int8_dot_requant_rtl.py 5dc93c61cd: the Verifier's cocotb benches and pytest entries
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/verif/testplan.yaml 06edae4f30: the test plan and mutant list read by the verification gates
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/verif/checkers/c14_int8_dot_requant_checker.sv 58a6f7fcfa: bound assertion and cover checkers
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/verif/checkers/v_macros.svh 013c1a5444: bound assertion and cover checkers
results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/review/02_rtl-design-creation.html ec65614105: the review page of stage rtl-design-creation: its exit gates and their failures at the last visit

## commands
what changed since this handover (stale records, changed files, tool and knowledge-bank pins): python -m flow.handover fresh results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant
[heavy] pick the work up again from the earliest stage the change or the staleness needs: python -m agent resume results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant "<change request>"
run the Verifier's simulation tests: python -m pytest -q results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/tests/test_c14_int8_dot_requant_rtl.py
[heavy] rebuild the bitstream with the flow: flow/run_vivado.sh results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant base

## records (path sha256-prefix; claims below cite R<n>)
R1 results/68_agent_docs/20261107-005621-8deb/summary.json 1f328382cc
R2 results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/verif_gates.json f2370412ee
R3 results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/mutation.json 13e1631e0d
R4 results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/base/gates.json 8a45ae63f9

## evidence
E1 review pass R1: spec.yaml was signed off after the interview; the questions asked, answered and defaulted are in the run summary
E2 simulation partial R2: verification stages (flow/verif_gates.py) against the Modeller's reference model; reached V2, the run asked for V3
E3 faults pass R3: generated mutants of the RTL run against the Verifier's benches; each must make a test fail
E4 build partial R4: Vivado base build; flow stages that ran: rtl, post_synth; built with an earlier Vivado release than the pinned one, so the result is not current

## measured
M1 verification -=100 % R3#score_pct: mutation score of the Verifier's benches | generated mutants sampled from the RTL, run in the simulation sandbox

## gaps
[REQ-04] REQ-04 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-06] REQ-06 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-07] REQ-07 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-08] REQ-08 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-09] REQ-09 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
[REQ-11] REQ-11 has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None
[E4] the base build was made with an earlier Vivado release than 2026.1: rebuild it before relying on its gates or numbers
[E2] simulation evidence is partial: verification stages (flow/verif_gates.py) against the Modeller's reference model; reached V2, the run asked for V3
[rtl-design-creation] stage rtl-design-creation did not pass its gates in this run; at its last visit: V3 cover_properties_pct: cover properties not hit: C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start: add or extend a test that drives the design into each, or correct the `V_COVER` expression if it can never be true [value 0.0, need 100] FAIL V3 cover_properties_unhit: cover properties not hit: C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start: add or extend a test that drives t ...
[constraints] stage constraints was not run: the run stopped before this stage (stage 2 visited more than 4 times)
[synthesis] stage synthesis was not run: the run stopped before this stage (stage 2 visited more than 4 times)
[implementation] stage implementation was not run: the run stopped before this stage (stage 2 visited more than 4 times)
[timing-closure] stage timing-closure was not run: the run stopped before this stage (stage 2 visited more than 4 times)
[power-closure] stage power-closure was not run: the run stopped before this stage (stage 2 visited more than 4 times)
[drc-closure] stage drc-closure was not run: the run stopped before this stage (stage 2 visited more than 4 times)
[configuration-and-debug] stage configuration-and-debug was not run: the run stopped before this stage (stage 2 visited more than 4 times)
[resources] resources not measured: no current Vivado build of this design has been recorded
[timing] timing not measured: no current Vivado build of this design has been recorded
[power] power not measured: no current Vivado build of this design has been recorded
[latency] latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
[throughput] throughput not measured: the run measured no throughput
[led_port_name] spec.yaml names the output port LED0 with width 1. The RTL and design.xdc (pin H17) use the one-bit bus LED[0] (top port LED, declared [0:0]), and an internal signal LED0 is assigned to it. The spec disagrees with what was built. The RTL and XDC are authoritative.
[design_id_parameter] spec.yaml lists DESIGN_ID as a parameter. In c14_int8_dot_requant_top.sv it is a localparam of 32'h444F5451 and cannot be overridden. Only CLKS_PER_BIT, TIMEOUT_CYCLES and BUILD_STAMP are top-level parameters, which matches REQ-10.
[reset_sync_source] rtl/reset_sync.sv in this design is an intentionally empty file with a comment. The reset synchroniser actually used is shell/rtl/reset_sync.sv, which this run did not review. ARCHITECTURE.md calls it a 2-flop synchroniser, but the RTL here does not show it. The spec's promise that outputs clear within 2 cycles of CPU_RESETN asserting was not measured.
[reset_values] After reset every operand register, bias and mult read 0, CTRL reads 1 (shift 1, relu 0), READY and the GO pulse are 0, and the core's y and acc registers are 0. The reset is synchronous and active high inside the design. The pipeline data registers in dotq_core (products, sums, and so on) are not reset, only the valid bits.
[unmapped_and_ro_access] In dotq_regs.sv a read of any offset without a case arm returns 0. This covers 0x07 (GO), 0x0B and above, and the unused offsets. A write to an unmapped offset or to an RO register (Y, ACC, STATUS) is ignored by the default arm. This matches the spec.
[partial_writes_and_bit_masks] Writes are whole 32-bit words with no byte strobes. MULT keeps only wdata[15:0]. CTRL keeps wdata[4:0] as shift and wdata[8] as relu and drops the other bits, which read back 0. Reads of MULT bits [31:16] return 0. The write data of a GO write is ignored. The shift field is not range-checked, so shift 0 can be stored. With shift 0 the core adds no rounding term and passes acc*mult through. Shift 0 is out of contract and untested.
[read_side_effects] Reads have no side effects. The read-data register changes only on a shell read strobe and otherwise holds its value. Y and ACC read 0 while READY is 0 because the read is gated by ready in dotq_regs.sv. The core's own y and acc registers are not cleared by GO. They are overwritten when the next result is valid.
[go_priority_and_restart] A GO write clears READY and is registered into a one-cycle go pulse to the core. If READY is being set by done in the same cycle as the GO write, the GO write wins and READY is 0. Inside the core a go pulse clears the valid bits of results in flight, so a GO while a computation is running restarts it with the loaded operands. A GO is also accepted when READY is already set.
[go_done_race] Reading dotq_regs.sv and dotq_core.sv, a done pulse can reach dotq_regs in the same cycle as the registered go pulse, if a GO write lands one cycle before done. READY would then be set again, with the old y and acc, until the new done arrives. The run did not test or simulate this case. It could break the spec's rule that READY is set only when y and acc are valid for the latest GO. The shell's UART access time makes it unlikely in practice.
[latency_structure] READY follows the registered go pulse through a fixed chain of valid bits in dotq_core (one per pipeline stage), then a registered done, then the READY flag. The spec promises READY within 8 clocks of GO. The run did not measure this, and it is not counted from the shell write strobe, which adds one clock for the registered go pulse. Only the Verifier's benches check the promise, and verification did not reach V3.
[operand_sampling] The core samples the operand registers every clock and carries mult, shift, relu and bias with the data through the pipeline. An operand write during the computation may be mixed into a result in flight or ignored. The spec does not require it to be safe and the run did not test it.
[assumptions] Assumptions from the interview, kept as made. The clock is the 100 MHz board oscillator, so CLKS_PER_BIT is 868. Weights are never -128, though the design should still compute them correctly. acc never overflows 32 bits for the inputs tested. Operand writes during a computation need not be safe. Shift outside 1..31 is out of contract. TIMEOUT_CYCLES and BUILD_STAMP defaults and the DOTQ ID presentation were defaulted by the oracle, not decided by a user.

## next_actions
1. Open build/review/02_rtl-design-creation.html and the verif_gates record. Make the five unhit cover properties (C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start) hit. Either extend the Verifier's benches so the shell traffic and a READY rise and fall drive them, or correct the V_COVER expressions if they can never be true. Then re-run the simulation tests until V3 passes.
2. Write or run a directed test for the go_done_race gap (a GO write one cycle before done) and fix dotq_regs.sv or dotq_core.sv if READY is set with stale results.
3. Review shell/rtl/reset_sync.sv, since the design's own reset_sync.sv is empty, and confirm the clear-within-2-cycles claim. Decide whether the spec should name the LED port LED[0] and DESIGN_ID as a localparam.
4. Run python -m flow.handover fresh, then resume the flow so the constraints, synthesis, implementation, timing, power and DRC stages run with Vivado 2026.1. This replaces the earlier-release base build.
5. Measure latency from the GO write to READY, plus resources, timing and power, from a current build. Check REQ-11 against the post-route setup gate.
6. Do hardware bring-up over the UART to produce the pending evidence for REQ-04, REQ-06, REQ-07, REQ-08 and REQ-09.

## open_questions
- Should the spec keep the port name LED0, or adopt the built LED[0] bus, given the master XDC?
- Is the go_done_race case acceptable as is, because UART access is slow, or must READY be strictly tied to the latest GO?
- Should an out-of-contract shift value (0, or a value above the legal range) be rejected, ignored or left undefined?

## history
2026-11-07 agent run pr=-: produced by the agent graph; stages that passed: clarify, board-and-device-planning
