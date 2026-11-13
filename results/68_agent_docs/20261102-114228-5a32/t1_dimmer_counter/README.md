# t1_dimmer_counter: T1 LED dimmer and push-button counter for the Nexys A7-100T

<!-- Generated from handover.yaml by flow/handover.py (brief 68). Edit handover.yaml, or the text between the prose markers, then run: python -m flow.handover write results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter -->

A single-clock design for the Nexys A7-100T. A 16-bit up/down counter is driven by three debounced push-buttons (up, down, centre-clear) and can also be read and written over the USB-UART through the repository fpga_shell register window. The counter value is shown on the 16 LEDs, gated by an 8-bit linear PWM brightness. Brightness comes either from a UART-written register or from the eight switches, chosen by a control bit. The counter and the active brightness are also shown on the eight-digit seven-segment display. The run produced RTL, constraints, a reference model and simulation tests, and the Vivado base build ran through bitstream with an earlier Vivado release than the pinned 2026.1. The timing-closure and configuration-and-debug stages did not pass their gates, so the design is not signed off on hardware or on current timing.

Not in scope:

- not a general UART bridge; the UART framing and command syntax belong to the repository's fpga_shell, which this design only instantiates
- not a multi-clock design; every function runs from the single 100 MHz clk with clock-enable style counters and no derived clocks
- not a design with measured resources, timing or power; no current Vivado build is recorded
- no register read side effects, no interrupts and no hold-to-repeat on the buttons

Kind: agent-run; produced by the agent (agent run `20261102-114228-5a32`, [record](../summary.json)). State: built. For an agent: [AGENT.md](AGENT.md).

<!-- prose:what -->
<!-- /prose:what -->

## Technical parameters

| Item | Value |
|---|---|
| Part | `xc7a100tcsg324-1` |
| Board | nexys_a7_100t |
| Top | `t1_led_dimmer_counter` |
| Tool | Vivado 2026.1 |

Clocks:

- `clk`: 100 MHz (from `results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/design.xdc`)

Resets:

- `cpu_reset_n`, active low: Pin C12, red CPU reset button. design: rtl/t1_led_dimmer_counter.sv asserts it asynchronously and releases it synchronously through a two-flop chain on clk. It clears the counter, brightness, control, the three press counts, the button and switch synchronizers, debounce state, PWM and display scan state, the registered LED and display outputs, and the register read data; the fpga_shell receives the same internal reset. Reset values are listed in the gaps.

Interfaces:

- `clk` (clock input): Pin E3, 100 MHz board oscillator, constrained with a 10.00 ns period in design.xdc.
- `button_up` (input, active high): Pin M18. Two-flop synchronizer, then debounce; one event per debounced rising edge increments the counter.
- `button_down` (input, active high): Pin P18. Same path as button_up; one event decrements the counter.
- `button_center` (input, active high): Pin N17. Same path as button_up; one event clears the counter and has priority over up and down.
- `switches` (input, 8 bits): SW0 to SW7 on J15, L16, M13, R15, R17, T18, U18, R13. Sampled through one register stage; they set the active brightness when CONTROL bit 0 is set and are readable at SWITCH_STATE.
- `uart_rx` (UART input): Pin C4 per design.xdc (the board's USB-UART TX to FPGA). Handled by fpga_shell.
- `uart_tx` (UART output) ([datasheet](ARCHITECTURE.md)): Pin D4 per design.xdc (FPGA to the board's USB-UART RX). Handled by fpga_shell.
- `leds` (output, 16 bits, active high): LD0 to LD15. The counter value gated by PWM, registered once before the pins.
- `segments_n` (output, 8 bits, active low): Segments CA to CG and DP. In the RTL the DP bit is always off.
- `digit_enable_n` (output, 8 bits, active low): AN0 to AN7. AN3 to AN0 show the counter, AN7 and AN6 show active brightness, AN5 and AN4 are blank. CONTROL bit 1 blanks all.

| Parameter | Value | Legal range | Note |
|---|---|---|---|
| `DEBOUNCE_CYCLES` | 1,000,000 | positive integer clock-cycle count; the RTL treats a value of one or less as immediate acceptance | A button level change is accepted only after the new level has been stable this many clk cycles, about 10 ms at 100 MHz. |
| `PWM_PERIOD_CYCLES` | 256 | positive integer; the exact linear compare is used only at the default 256, other values use a scaled compare, and only the default has been described by the spec | PWM period in clk cycles, about 390.625 kHz at 100 MHz. Brightness 0 is off and 255 is always on. |
| `DISPLAY_SCAN_CYCLES` | 100,000 | positive integer clock-cycle count per digit | Cycles each digit stays selected; a full eight-digit frame takes eight times this value. |
| `UART_BAUD_DIVIDER` | 868 | positive integer; passed to fpga_shell as CLKS_PER_BIT | Clock cycles per UART bit, about 115207 baud at 100 MHz, close to 115200 baud. |

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
| what changed since this handover (stale records, changed files, tool and knowledge-bank pins) | `python -m flow.handover fresh results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter` | no | - |
| pick the work up again from the earliest stage the change or the staleness needs; needs a model (see docs/agent.md); Vivado for any stage from synthesis on | `python -m agent resume results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter "<change request>"` | yes | - |
| run the Verifier's simulation tests; needs Icarus Verilog and cocotb, or the simulation container | `python -m pytest -q results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/tests/test_t1_dimmer_counter_rtl.py` | no | - |
| rebuild the bitstream with the flow; needs Vivado 2026.1 and a heavy slot | `flow/run_vivado.sh results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter base` | yes | - |

Tool: Vivado 2026.1. Build ID of the inputs at handover: `b566fd35` (`python flow/manifest.py show results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter`: what a rebuild of today's sources and flow would carry; it changes when any build input or the flow changes, so it can differ from the build ID in an older evidence record). Knowledge-bank pin: `1fc7ed8`.

| File | What |
|---|---|
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/spec.md`](spec.md) | the request the run started from |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/spec.yaml`](spec.yaml) | the signed-off specification written by the Clarifier |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/ARCHITECTURE.md`](ARCHITECTURE.md) | the architecture note approved before any RTL |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/rtl/t1_led_dimmer_counter.sv`](rtl/t1_led_dimmer_counter.sv) | RTL written by the Designer |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/design.xdc`](design.xdc) | pin, I/O standard and timing constraints |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/build.yaml`](build.yaml) | the build description read by the flow |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/model.py`](model.py) | the Modeller's reference model of the visible behaviour |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/tests/test_t1_dimmer_counter_rtl.py`](tests/test_t1_dimmer_counter_rtl.py) | the Verifier's cocotb benches and pytest entries |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/verif/testplan.yaml`](verif/testplan.yaml) | the test plan and mutant list read by the verification gates |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/build/review/06_timing-closure.html`](build/review/06_timing-closure.html) | the review page of stage timing-closure: its exit gates and their failures at the last visit |
| [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/build/review/09_configuration-and-debug.html`](build/review/09_configuration-and-debug.html) | the review page of stage configuration-and-debug: its exit gates and their failures at the last visit |

<!-- prose:build -->
<!-- /prose:build -->

## Verified

![Verification matrix: each activity and its result](docs/handover/verification.svg)

| ID | Activity | Result | What | Evidence | Conditions |
|---|---|---|---|---|---|
| E1 | review | pass | spec.yaml was signed off after the interview; the questions asked, answered and defaulted are in the run summary | [`results/68_agent_docs/20261102-114228-5a32/summary.json`](../summary.json) | - |
| E2 | simulation | pass | verification stages (flow/verif_gates.py) against the Modeller's reference model; reached V1, the run asked for V1 | [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/build/verif/verif_gates.json`](build/verif/verif_gates.json) | - |
| E3 | build | partial | Vivado base build; flow stages that ran: rtl, post_synth, post_place, post_route, bitstream; built with an earlier Vivado release than the pinned one, so the result is not current | [`results/68_agent_docs/20261102-114228-5a32/t1_dimmer_counter/build/base/gates.json`](build/base/gates.json) | - |

Gates at handover: `clarify` pass, `board-and-device-planning` pass, `rtl-design-creation` pass, `constraints` pass, `synthesis` pass, `implementation` pass, `timing-closure` fail, `power-closure` pass, `drc-closure` pass, `configuration-and-debug` fail.

<!-- prose:verified -->
<!-- /prose:verified -->

## Measured

Every value is read from the record by `python -m flow.handover fill`, not typed.

| ID | What | Value | Runs | Source | Conditions |
|---|---|---|---|---|---|
| M1 | model cost of the run, provider-reported | 0.170661 USD | 1 | [`results/68_agent_docs/20261102-114228-5a32/summary.json`](../summary.json) `cost_usd` | every role and the interview oracle, as the run summary records it |

<!-- prose:measured -->
<!-- /prose:measured -->

## Known gaps and limits

- **E3**: the base build was made with an earlier Vivado release than 2026.1: rebuild it before relying on its gates or numbers
- **timing-closure**: stage timing-closure did not pass its gates in this run; at its last visit: bitstream: did not run FAIL
- **configuration-and-debug**: stage configuration-and-debug did not pass its gates in this run; at its last visit: bitstream: did not run FAIL
- **resources**: resources not measured: no current Vivado build of this design has been recorded
- **timing**: timing not measured: no current Vivado build of this design has been recorded
- **power**: power not measured: no current Vivado build of this design has been recorded
- **latency**: latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
- **throughput**: throughput not measured: the run measured no throughput
- **uart_pins**: design.xdc puts uart_rx on C4 and uart_tx on D4, which matches spec.yaml. The pin table in ARCHITECTURE.md has them the other way round (uart_rx D4, uart_tx C4). design.xdc is what was built; ARCHITECTURE.md disagrees.
- **reset_values**: rtl/t1_led_dimmer_counter.sv resets BRIGHTNESS and CONTROL to zero, which matches the register map in spec.yaml. An answer recorded in spec.yaml (resolved_questions) says brightness resets to 0x40 and CTRL to 0x2 with the display enabled; the RTL does not do this. With CONTROL zero the switch source is off and the display is enabled (bit 1 set would blank it). The RTL is what was built; the spec disagrees with itself.
- **pwm_period**: The RTL runs the PWM phase counter once per clk cycle with a period of PWM_PERIOD_CYCLES (256), about 390.625 kHz, as the timing section of spec.yaml says. A recorded answer in spec.yaml describes a prescale giving 1024 cycles and about 97.7 kHz; the RTL has no prescale, so that answer disagrees with what was built.
- **register_reads**: Reads of any offset other than 0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C and 0x20 return zero. Reads have no side effects. The read data register updates on the cycle after win_rd, so the value is registered one cycle late and is cleared by reset.
- **register_writes**: Writes to unmapped offsets and to read-only registers (DESIGN_ID, BUTTON_STATE, SWITCH_STATE and the three press counts) are silently ignored. COUNTER takes the low 16 bits and BRIGHTNESS the low 8 bits of the write data; the upper bits are dropped. CONTROL stores all 32 bits and reads them back, although only bits 0 and 1 have any effect; the other bits are reserved but writable. There are no byte enables, so there are no partial writes.
- **counter_priorities**: A UART write to COUNTER in the same cycle as a button event wins over the event; the press counts still increment. Among button events, centre clear wins over up and down, and simultaneous up and down cancel. A held button gives one event only, and an event is produced when the debounce interval ends, on a rising edge only; releasing a button changes the debounced level but gives no event.
- **brightness_source**: With CONTROL bit 0 set, the switches set the active brightness and the display shows that value; the stored BRIGHTNESS register is not overwritten and stays readable and writable. The recorded answer on whether UART writes are kept in switch mode is not firm, but the RTL keeps them.
- **synchronizers**: The three buttons pass through two flops; the eight switches pass through one register stage only, which is weaker than the buttons. This is an assumption of the Designer that switch changes are slow.
- **display_details**: Digit 0 to 3 are AN0 to AN3 showing counter nibbles, least significant at AN0. AN7 shows the high nibble of active brightness and AN6 the low nibble. AN5 and AN4 are enabled but have all segments off. The DP segment is always off. LED and display outputs are registered, so they lag the internal state by one clock cycle.
- **input_timing**: design.xdc applies set_false_path from all the asynchronous inputs (reset, buttons, switches, uart_rx), so setup and hold on those paths are not analysed; the input delay lines document the board budget only.
- **unchecked_hardware**: No evidence entry records a run on the board, so button, UART, LED and display behaviour on hardware is unverified.

<!-- prose:gaps -->
<!-- /prose:gaps -->

## Next steps

1. Rebuild the base build with Vivado 2026.1 (flow/run_vivado.sh in the commands list) and read build/base/gates.json; this clears gap E3 and shows why the bitstream stage did not run.
2. Read the review pages of timing-closure and configuration-and-debug, fix the failure that stopped the bitstream, and rerun those stages.
3. Decide the reset values for BRIGHTNESS and CONTROL (the RTL uses zero, a recorded answer says 0x40 and 0x2), then update spec.yaml or the RTL and the model and tests to agree.
4. Decide the PWM period (256 cycles as built, or the prescaled period in the recorded answer) and make spec.yaml, the model and the RTL consistent.
5. Correct the UART pin table in ARCHITECTURE.md to match design.xdc, then record resources, timing and power from the current build.
6. Test on the board over the UART at 115200 baud, including the buttons, switch brightness mode and the display.

Open questions:

- Should BRIGHTNESS reset to 0x40 and CONTROL to 0x2 as one recorded answer says, or to zero as built?
- Should the PWM have a prescale (a period of 1024 clock cycles) or stay at 256 cycles as built?
- Should the switches get a second synchronizer stage like the buttons?
- Should writes to the reserved bits of CONTROL be stored, as built, or dropped?

<!-- prose:next -->
<!-- /prose:next -->

## History

| Date | Brief | PR | What |
|---|---|---|---|
| 2026-11-02 | agent run | - | produced by the agent graph; stages that passed: clarify, board-and-device-planning, rtl-design-creation, constraints, synthesis, implementation, power-closure, drc-closure |

<!-- prose:history -->
<!-- /prose:history -->
