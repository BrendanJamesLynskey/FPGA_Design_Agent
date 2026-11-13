# c14_int8_dot_requant: Quantised-layer int8 dot-product unit behind the UART test shell

<!-- Generated from handover.yaml by flow/handover.py (brief 68). Edit handover.yaml, or the text between the prose markers, then run: python -m flow.handover write results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant -->

The design computes an 8-way signed int8 dot product plus a 32-bit bias, multiplies the sum by a 16-bit unsigned multiplier, applies a rounding right shift (halves round towards plus infinity) and clamps the result to a signed 8-bit value, with an optional ReLU. It sits behind the reusable UART test shell on the Nexys A7-100T (xc7a100tcsg324-1) and is driven by register reads and writes over the USB-UART. The run reached simulation level V2 of V3: verification stopped at V3 because five cover properties were never hit, so no synthesis, implementation or hardware result exists. The specification and architecture were accepted automatically by a model, with no human review.

Not in scope:

- Not a general neural-network layer: one 8-element dot product per GO, with no streaming, batching or accumulation across calls.
- Not a design with a defined overflow or wrap behaviour: acc overflow and shift outside 1..31 are out of contract and untested.
- Not hardware-verified, not timing-closed and not measured for resources or power; none of those stages ran.

Kind: agent-run; produced by the agent (agent run `20261107-005621-8deb`, [record](../summary.json)). State: rtl. For an agent: [AGENT.md](AGENT.md).

Run: model claude-sonnet-5-5 (claude_code harness), 6 loops, 101 turns, 2,482,927 tokens, 3379 s wall time, 2.9032 USD plan-cost estimate (not billed), stopped because: stage 2 visited more than 4 times (from the run record).

![Block diagram: the design's blocks and the links between them](docs/handover/architecture.svg)

<!-- prose:what -->
<!-- /prose:what -->

## Technical parameters

| Item | Value |
|---|---|
| Part | `xc7a100tcsg324-1` |
| Board | nexys_a7_100t |
| Top | `c14_int8_dot_requant_top` |
| Tool | Vivado 2026.1 |

Clocks:

- `CLK100MHZ`: 100 MHz (from `results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/design.xdc`)

Resets:

- `CPU_RESETN`, active low: Board button on pin C12. rtl/c14_int8_dot_requant_top.sv passes it through shell/rtl/reset_sync.sv: assertion is asynchronous, release is synchronous after two clock edges, and the resulting active-high reset is applied synchronously in all blocks. It clears the operand registers, y, acc and READY, and sets CTRL to shift 1, relu 0.

Interfaces:

- `CLK100MHZ` (clock input): Board 100 MHz oscillator on pin E3, LVCMOS33; the single clock for shell and arithmetic, constrained at a 10.00 ns period in design.xdc.
- `UART_TXD_IN` (UART serial input (8N1, 115200 baud)): Pin C4: data from the host into the FPGA. Asynchronous; it is synchronised in the shell by sync2. design.xdc gives it a 2.0 max / 0.0 min input delay.
- `UART_RXD_OUT` (UART serial output (8N1, 115200 baud)): Pin D4: data from the FPGA to the host. The shell protocol is shell/PROTOCOL.md. design.xdc gives it a 2.0 max / 0.0 min output delay.
- `LED0` (LED output): Shows the READY flag. The built top-level port is the bus LED[0] on pin H17 (rtl/c14_int8_dot_requant_top.sv, design.xdc); the spec calls it LED0, which is only an internal net in the RTL.

Registers (from spec.yaml; where the RTL differs, the gaps say so):

| Offset | Name | Access | Reset | Bits |
|---|---|---|---|---|
| 0x00 | `A_LO` | RW | 0x00000000 | [31:0] activations 0..3, a_i in bits [8i+7:8i] |
| 0x01 | `A_HI` | RW | 0x00000000 | [31:0] activations 4..7, a_(4+i) in bits [8i+7:8i] |
| 0x02 | `W_LO` | RW | 0x00000000 | [31:0] weights 0..3, same packing |
| 0x03 | `W_HI` | RW | 0x00000000 | [31:0] weights 4..7, same packing |
| 0x04 | `BIAS` | RW | 0x00000000 | [31:0] signed bias |
| 0x05 | `MULT` | RW | 0x00000000 | [15:0] unsigned multiplier; [31:16] read 0 |
| 0x06 | `CTRL` | RW | 0x00000001 | [4:0] shift (1..31), [8] relu; other bits read 0 |
| 0x07 | `GO` | WO | 0x00000000 | any write starts one computation; reads 0 |
| 0x08 | `Y` | RO | 0x00000000 | [7:0] limited answer (two's complement); [31:8] read 0 |
| 0x09 | `ACC` | RO | 0x00000000 | [31:0] the signed accumulator including the bias |
| 0x0A | `STATUS` | RO | 0x00000000 | [0] READY; other bits 0 |

| Parameter | Value | Legal range | Note |
|---|---|---|---|
| `CLKS_PER_BIT` | 868 | Positive integer; only 868 (100 MHz / 115200 baud) was designed for and tested. | UART clocks per bit, giving 115200 baud 8N1 on CLK100MHZ. Any other value changes the baud rate. |
| `TIMEOUT_CYCLES` | 100,000,000 | Positive integer. | Clocks of silence after which the shell drops a partly received frame without a response. The top overrides the shell's own smaller default. |
| `BUILD_STAMP` | 0 | Any 32-bit value. | Read back through the shell at its address 0x02; the spec says the flow overrides the default of 0. It does not affect the arithmetic. |
| `DESIGN_ID` | DOTQ | Fixed: 0x444F5451 (ASCII D,O,T,Q). | This is a localparam in rtl/c14_int8_dot_requant_top.sv, not an overridable top-level parameter. The shell returns it at its address 0x00. |

| Quantity | Value | Source |
|---|---|---|
| Resources | not measured | [Known gaps](#known-gaps-and-limits) |
| Timing | not measured | [Known gaps](#known-gaps-and-limits) |
| Power | not measured | [Known gaps](#known-gaps-and-limits) |
| Latency | not measured | [Known gaps](#known-gaps-and-limits) |
| Throughput | not measured | [Known gaps](#known-gaps-and-limits) |

<!-- prose:parameters -->
<!-- /prose:parameters -->

## How to build, run and reproduce

| Step | Command | Heavy slot | Time |
|---|---|---|---|
| what changed since this handover (stale records, changed files, tool and knowledge-bank pins) | `python -m flow.handover fresh results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant` | no | - |
| pick the work up again from the earliest stage the change or the staleness needs; needs a model (see docs/agent.md); Vivado for any stage from synthesis on | `python -m agent resume results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant "<change request>"` | yes | - |
| run the Verifier's simulation tests; needs Icarus Verilog and cocotb, or the simulation container | `python -m pytest -q results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/tests/test_c14_int8_dot_requant_rtl.py` | no | - |
| rebuild the bitstream with the flow; needs Vivado 2026.1 and a heavy slot | `flow/run_vivado.sh results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant base` | yes | - |

Tool: Vivado 2026.1. Build ID of the inputs at handover: `b27eac2c` (`python flow/manifest.py show results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant`: what a rebuild of today's sources and flow would carry; it changes when any build input or the flow changes, so it can differ from the build ID in an older evidence record). Knowledge-bank pin: `aa71844`.

| File | What |
|---|---|
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/spec.md`](spec.md) | the request the run started from |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/spec.yaml`](spec.yaml) | the specification the Clarifier wrote, accepted automatically by a model (no human review) |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/ARCHITECTURE.md`](ARCHITECTURE.md) | the architecture note, accepted automatically before any RTL (no human review) |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/architecture.yaml`](architecture.yaml) | the machine-checked architecture: blocks, clocks, predicted resources |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/c14_int8_dot_requant_top.sv`](rtl/c14_int8_dot_requant_top.sv) | RTL written by the Designer |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/dotq_core.sv`](rtl/dotq_core.sv) | RTL written by the Designer |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/dotq_regs.sv`](rtl/dotq_regs.sv) | RTL written by the Designer |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/rtl/reset_sync.sv`](rtl/reset_sync.sv) | RTL written by the Designer (empty: it holds no code; the build reads shell/rtl/reset_sync.sv for this module instead) |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/design.xdc`](design.xdc) | pin, I/O standard and timing constraints |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build.yaml`](build.yaml) | the build description read by the flow; its sources also include shared shell files the agent did not write (read from the repository, not copied here): shell/rtl/fpga_shell.sv, shell/rtl/reset_sync.sv, shell/rtl/shell_core.sv, shell/rtl/sync2.sv, shell/rtl/uart_rx.sv, shell/rtl/uart_tx.sv |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/model.py`](model.py) | the Modeller's reference model of the visible behaviour |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/tests/c14_bench.py`](tests/c14_bench.py) | the Verifier's cocotb benches and pytest entries |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/tests/test_c14_int8_dot_requant_rtl.py`](tests/test_c14_int8_dot_requant_rtl.py) | the Verifier's cocotb benches and pytest entries |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/verif/testplan.yaml`](verif/testplan.yaml) | the test plan and mutant list read by the verification gates |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/verif/checkers/c14_int8_dot_requant_checker.sv`](verif/checkers/c14_int8_dot_requant_checker.sv) | bound assertion and cover checkers |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/verif/checkers/v_macros.svh`](verif/checkers/v_macros.svh) | bound assertion and cover checkers |
| [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/review/02_rtl-design-creation.html`](build/review/02_rtl-design-creation.html) | the review page of stage rtl-design-creation: its exit gates and their failures at the last visit |

<!-- prose:build -->
<!-- /prose:build -->

## Verified

![Verification matrix: each activity and its result](docs/handover/verification.svg)

| ID | Activity | Result | What | Evidence | Conditions |
|---|---|---|---|---|---|
| E1 | review | partial | the specification and the architecture were approved automatically by a model, with no human review (review off; interview oracle claude-haiku-5-5); the interview asked 6 questions, 3 answered and 3 defaulted | [`results/68_agent_docs/20261107-005621-8deb/summary.json`](../summary.json) | - |
| E2 | simulation | partial | verification (flow/verif_gates.py) against the Modeller's reference model reached V2 of V3; the run asked for V3; V2 means simulation: seeded runs, a constrained-random test, bound assertions and formal tasks; V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: cover properties pct 0.0 (needs 100); cover properties unhit C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start; no board result (V-HW) is recorded | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/verif_gates.json`](build/verif/verif_gates.json) | - |
| E3 | faults | pass | generated mutants of the RTL run against the Verifier's benches, each of which must make a test fail: 17 sampled of 32 candidates, 17 evaluated, 17 killed, 0 survived, 0 timed out | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/mutation.json`](build/verif/mutation.json) | - |
| E4 | build | partial | Vivado base build under an earlier Vivado release than the pinned one: it reached post_synth, the gates of the stages it ran all passed; every number from that build is withdrawn (it cannot be re-measured on Vivado 2026.1 without a rebuild), so none is published | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/base/gates.json`](build/base/gates.json) | - |

Gates at handover: `clarify` pass, `board-and-device-planning` pass, `rtl-design-creation` fail, `constraints` not-run, `synthesis` not-run, `implementation` not-run, `timing-closure` not-run, `power-closure` not-run, `drc-closure` not-run, `configuration-and-debug` not-run.

<!-- prose:verified -->
<!-- /prose:verified -->

## Measured

Every value is read from the record by `python -m flow.handover fill`, not typed.

| ID | What | Value | Runs | Source | Conditions |
|---|---|---|---|---|---|
| M1 | simulation seeds run | 3 | 1 | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/verif_gates.json`](build/verif/verif_gates.json) `stages.V3.checks.seeds_run.value` | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran |
| M2 | line coverage | 100 % | 1 | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/verif_gates.json`](build/verif/verif_gates.json) `stages.V3.checks.line_pct.value` | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran |
| M3 | toggle coverage | 100 % | 1 | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/verif_gates.json`](build/verif/verif_gates.json) `stages.V3.checks.toggle_pct.value` | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran |
| M4 | functional coverage bins hit | 100.0 (50/50) | 1 | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/verif_gates.json`](build/verif/verif_gates.json) `stages.V3.checks.functional_bins_pct.value` | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran |
| M5 | cover properties hit | 0.0 % | 1 | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/verif_gates.json`](build/verif/verif_gates.json) `stages.V3.checks.cover_properties_pct.value` | Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran |
| M6 | mutation score of the Verifier's benches | 100 % | 1 | [`results/68_agent_docs/20261107-005621-8deb/c14_int8_dot_requant/build/verif/mutation.json`](build/verif/mutation.json) `score_pct` | generated mutants sampled from the RTL, run in the simulation sandbox |

<!-- prose:measured -->
<!-- /prose:measured -->

## Known gaps and limits

- **REQ-04**: REQ-04 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
- **REQ-06**: REQ-06 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
- **REQ-07**: REQ-07 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
- **REQ-08**: REQ-08 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
- **REQ-09**: REQ-09 has no passing evidence for every proof method: hardware (uart_tests) is pending: no bring-up result
- **REQ-11**: REQ-11 has no passing evidence for every proof method: analysis (post_route:setup) is not run (the stage that makes this evidence did not run): gate post_route:setup = None
- **cover_properties**: cover properties C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start read 0.0 % while the functional bins were all hit (100.0 (50/50)) and 3 seeds ran. The benches did drive the design, so a missing stimulus is unlikely to be the whole cause; the cover results and the functional coverage disagree. Compare the two before proposing any new stimulus. The checker c14_int8_dot_requant_checker.sv binds clk to CLK100MHZ, rst to CPU_RESETN, led to LED0, rxd_out to UART_RXD_OUT, txd_in to UART_TXD_IN into c14_int8_dot_requant_top (outside Icarus only). Every bound name is declared in the top RTL, so a misspelt binding is not the cause. The cause is not settled by the records.
- **E4**: the base build was made under an earlier Vivado release than 2026.1: its result is not current and no number from it is published. Re-measure it, when the flow reaches the build again, with the resume command in How to build (python -m agent resume), and only then rely on its gates
- **E1**: review evidence is partial: the specification and the architecture were approved automatically by a model, with no human review (review off; interview oracle claude-haiku-5-5); the interview asked 6 questions, 3 answered and 3 defaulted
- **E2**: simulation evidence is partial: verification reached V2 of V3 (the run asked for V3); the checks that did not pass or did not run are listed in the evidence row
- **rtl-design-creation**: stage rtl-design-creation did not pass its gates in this run; at its last visit: V3 cover_properties_pct: cover properties not hit: C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start: add or extend a test that drives the design into each, or correct the `V_COVER` expression if it can never be true [value 0.0, need 100] FAIL V3 cover_properties_unhit: cover properties not hit: C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start: add or extend a test that drives t ...
- **constraints**: stage constraints was not run: the run stopped before this stage (stage 2 visited more than 4 times)
- **synthesis**: stage synthesis was not run: the run stopped before this stage (stage 2 visited more than 4 times)
- **implementation**: stage implementation was not run: the run stopped before this stage (stage 2 visited more than 4 times)
- **timing-closure**: stage timing-closure was not run: the run stopped before this stage (stage 2 visited more than 4 times)
- **power-closure**: stage power-closure was not run: the run stopped before this stage (stage 2 visited more than 4 times)
- **drc-closure**: stage drc-closure was not run: the run stopped before this stage (stage 2 visited more than 4 times)
- **configuration-and-debug**: stage configuration-and-debug was not run: the run stopped before this stage (stage 2 visited more than 4 times)
- **oracle_record**: BUILD_NOTE.md names the interview oracle as openai/gpt-6-luna, while summary.json names claude-haiku-5-5; the two records disagree and neither is confirmed, so the specification's provenance is uncertain
- **formal**: formal checks were planned for REQ-01, REQ-02, REQ-03, REQ-05, REQ-06 and did not run; each was replaced by a simulation check (verif/testplan.yaml replan). Reason recorded: SymbiYosys is not installed here, so exactness of acc is checked by directed extremes and random cases against the model.
- **assertions**: assertions that cannot fail: A_led_boolean (c14_int8_dot_requant_checker.sv:20) asserts that led is 0 or 1, which is always true; A_tx_boolean (c14_int8_dot_requant_checker.sv:21) asserts that rxd_out is 0 or 1, which is always true. They show only that the signal exists, not that the design behaves
- **resources**: resources not measured: no current Vivado build of this design has been recorded
- **timing**: timing not measured: no current Vivado build of this design has been recorded
- **power**: power not measured: no current Vivado build of this design has been recorded
- **latency**: latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
- **throughput**: throughput not measured: the run measured no throughput
- **latency_count**: Counted from rtl/dotq_core.sv and rtl/dotq_regs.sv: with the one-cycle go pulse in cycle 0, v1..v5 follow, done is high in cycle 6 and READY is high in cycle 7, so READY rises 7 clocks after the go pulse, or 8 clocks after the shell write strobe because dotq_regs registers go. This meets the spec's "within 8 clocks" only if the count starts at the go pulse or the write strobe exactly; it has no margin. ARCHITECTURE.md describes five stages, but the RTL has a sixth register stage (the y/acc output register) before done.
- **go_priority**: A GO write always wins over a simultaneous done in dotq_regs.sv (READY ends 0). A new go while a computation is in flight also cancels it in dotq_core.sv: every valid stage is gated with ~go, so the earlier result is dropped, and the new computation restarts from the loaded operands. Operand writes during a computation are not blocked and can corrupt that result; the spec calls this out of contract.
- **result_visibility**: Y and ACC are not cleared by GO; the core keeps the old values and dotq_regs.sv only masks them to 0 on reads while READY is 0. The y/acc registers in the core are overwritten when a computation completes, slightly before READY rises.
- **unmapped_access**: Reads of GO and of every offset above STATUS return 0; writes to the RO registers (Y, ACC, STATUS) and to every offset above STATUS are ignored with no error response (dotq_regs.sv default branches). A write to any address other than GO never starts a computation. Writes to MULT keep only bits [15:0]; writes to CTRL keep only bits [4:0] and [8].
- **window_address**: The register offsets in this document are window-relative. The shell reaches the design only for shell addresses with bit 7 set, and the window offset is the low 7 bits (shell_core.sv: win_addr is addr[6:0]), so A_LO is at shell address 0x80 and each later register follows at the next address. Shell addresses with bit 7 clear are the shell's own registers (design ID, version, build stamp, scratch, error counters, build ID). A window read returns its data after a registered read, one cycle after win_rd.
- **ctrl_shift_range**: CTRL accepts any 5-bit shift. The RTL handles shift 0 (no rounding constant is added, so the result is the plain product) although the spec only defines 1..31. Reset value of shift is 1, of relu 0.
- **clamp_order**: dotq_core.sv checks the upper clamp (127) first, then relu (below 0 gives 0), then the lower clamp (-128 gives the byte 0x80). Y is returned as 8 bits, zero-extended in the register read; a negative y therefore reads as its two's-complement byte in bits [7:0] with bits [31:8] zero, not sign-extended.
- **port_name_spec**: spec.yaml names the LED port LED0; the built top-level port is the bus LED[0] (rtl/c14_int8_dot_requant_top.sv, design.xdc, pin H17). The RTL and XDC are what was built. LED0 exists only as an internal net, which is what the checker binds to.
- **reset_timing**: The spec says outputs and READY clear within 2 cycles of CPU_RESETN asserting. In the RTL (shell/rtl/reset_sync.sv) assertion of rst is asynchronous, but the design flops clear on the next clock edge while rst is high; release needs two clock edges after the button is let go. The 2-cycle figure was not measured.
- **design_id_parameter**: The spec lists DESIGN_ID among the parameters; in the RTL it is a localparam in the top file and cannot be set from outside. It reaches the shell at address 0x00.
- **assumptions**: Assumptions made by the run (spec.yaml): the clock is 100 MHz so CLKS_PER_BIT is 868; weights are never -128 (the design still computes correctly with them); acc never overflows 32 bits for the tested inputs; operand writes during a computation are not required to be safe; shift outside 1..31 is out of contract. TIMEOUT_CYCLES and BUILD_STAMP defaults and the DOTQ ID presentation were defaulted by the oracle, not answered.

<!-- prose:gaps -->
<!-- /prose:gaps -->

## Next steps

1. First, compare the cover results with the functional coverage before any new stimulus: the five cover properties (C_led_fall, C_led_high, C_led_rise, C_rx_start, C_tx_start) read 0.0 % while all functional bins were hit. Check the V_COVER expressions and the checker bindings (including the clk/rst names and the polarity of CPU_RESETN) in verif/checkers/c14_int8_dot_requant_checker.sv, then fix the checker or add stimulus, and re-run V3.
2. Replace or strengthen the two assertions that cannot fail (A_led_boolean, A_tx_boolean) with checks on READY timing, the GO/done priority and the reads-0-while-not-ready rule.
3. Re-run verification until V3 passes (coverage, three seeds, mutation score), then let the flow continue to constraints, synthesis, implementation and the closure stages.
4. When the flow reaches the build again, re-measure it on Vivado 2026.1 with python -m agent resume; publish no number from the existing base build.
5. Have a human review spec.yaml and ARCHITECTURE.md, since both were accepted automatically by a model, and settle which interview oracle record (BUILD_NOTE.md or summary.json) is right.
6. After a successful build, run the shell bring-up tests on the board for REQ-04, REQ-06, REQ-07, REQ-08 and REQ-09, and record the actual READY latency.

Open questions:

- Why do the five cover properties read 0.0 % while the functional bins were all hit? The records do not settle it.
- Is READY at 7 clocks after the go pulse (8 after the write strobe) acceptable as "within 8 clocks", or does the spec intend a stricter count?
- Should the spec's port name LED0 be corrected to LED[0] to match the master XDC?

<!-- prose:next -->
<!-- /prose:next -->

## History

| Date | Brief | PR | What |
|---|---|---|---|
| 2026-11-07 | agent run | - | produced by the agent graph; stages that passed: clarify, board-and-device-planning |

<!-- prose:history -->
<!-- /prose:history -->
