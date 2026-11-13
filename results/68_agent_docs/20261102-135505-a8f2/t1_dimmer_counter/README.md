# t1_dimmer_counter: T1 LED dimmer and push-button counter on the Nexys A7-100T

<!-- Generated from handover.yaml by flow/handover.py (brief 68). Edit handover.yaml, or the text between the prose markers, then run: python -m flow.handover write results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter -->

The design keeps a 16-bit up/down counter driven by three debounced push-buttons (up, down, clear) and by writes over the USB-UART test shell. It shows the counter on 16 LEDs gated by a PWM brightness waveform and on a multiplexed seven-segment display, and exposes the counter, brightness, control bits, input status, three press counters and a design ID as a register window. The run reached a base bitstream, but under an earlier Vivado release than the pinned one, so none of its numbers are published. Stages clarify to drc-closure passed their gates; configuration-and-debug did not, because the ILA debug build did not complete. Simulation verification reached V1 of V3.

Not in scope:

- Not a processor or a general bus; it is a fixed register window behind the shared UART test shell (shell/rtl), whose framing the Designer did not write.
- The switches and the raw button levels have no debounce or synchronisation in the RTL; only the press events that update the counter are debounced.
- No decimal-point output, no per-digit brightness, and no scrolling or blanking of leading zeros on the display.
- Not verified on the board, and not measured for resources, timing, power, latency or throughput in a current build.

Kind: agent-run; produced by the agent (agent run `20261102-135505-a8f2`, [record](../summary.json)). State: built. For an agent: [AGENT.md](AGENT.md).

Run: model openai/gpt-6-luna (deepagents harness), 5 loops, 208 turns, 6,466,831 tokens, 3623.4 s wall time, 0.164748 USD model cost (provider-reported), stopped because: stage 9 visited more than 4 times (from the run record).

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

- `clk`: 100 MHz (from `results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/design.xdc`)

Resets:

- `cpu_resetn`, active low: Pin C12. In t1_led_dimmer_counter.sv the registers of the top level use rst = ~cpu_resetn directly, so a reset asserts at once and releases without synchronisation to clk. Only the shell receives a two-flop synchronised release (shell_rst). The shared reset_sync.sv is listed in the build but not instantiated; the top level has its own inline copy.

Interfaces:

- `clk` (clock input): Port clk, pin E3 in design.xdc, 10.00 ns period (100 MHz), LVCMOS33.
- `cpu_resetn` (reset input): Port cpu_resetn, pin C12; behaviour is described under resets.
- `btn_up` (input): BTNU, pin M18, active high; two flip-flop stage then debounce; increments the counter.
- `btn_down` (input): BTND, pin P18, active high; two flip-flop stage then debounce; decrements the counter.
- `btn_center` (input): BTNC, pin N17, active high; two flip-flop stage then debounce; clears the counter.
- `switches` (input, 8 bits): SW[7:0], pins J15, L16, M13, R15, R17, T18, U18, R13. Used unsynchronised as the brightness when CONTROL bit 0 is set, and read into INPUT_STATUS bits 7:0.
- `leds` (output, 16 bits): LED[15:0], pins H17, K15, J13, N14, R18, V17, U17, U16, V16, T15, U14, T16, V15, V14, V12, V11. Shows the counter when the PWM phase is on, otherwise all off.
- `seg` (output, 7 bits): Segments CA to CG on seg[0] to seg[6], active low, pins T10, R10, K16, K13, P15, T11, L18.
- `dp` (output): Pin H15, active low; held high (off) permanently.
- `an` (output, 8 bits): AN[7:0], active low, pins J17, J18, T9, J14, P14, T14, K2, U13. AN[3:0] show the counter nibbles (AN[0] least significant), AN[7] the high nibble and AN[6] the low nibble of the effective brightness, AN[5:4] always off.
- `uart_rxd` (UART input): Pin C4, 115200 baud 8-N-1 into the shared shell. Shell address bit 7 selects the register window, so a window register at offset N is addressed with that bit set plus N.
- `uart_txd` (UART output): Pin D4, 115200 baud 8-N-1 from the shared shell.

| Parameter | Value | Legal range | Note |
|---|---|---|---|
| `DEBOUNCE_CYCLES` | 1,000,000 | Integer of 2 or more; the counter width is derived with $clog2. Other values were not simulated. | Consecutive stable sys_clk cycles needed to accept a press or release, about 10 ms at 100 MHz (spec timing section). Spec timing: 1000000 sys_clk cycles of stable input, approximately 10 ms at 100 MHz. |
| `PWM_PERIOD_CYCLES` | 4096 | Integer of 2 or more; any value works in the RTL, a power of two is not required. Other values were not simulated. | PWM period in sys_clk cycles, about 24.4 kHz at 100 MHz, chosen to avoid visible flicker (spec timing section). Spec timing: 4096 sys_clk cycles, approximately 24.4 kHz at 100 MHz. Spec timing: 4096 sys_clk cycles, approximately 24.4 kHz at 100 MHz; selected to avoid visible flicker. |
| `DISPLAY_DIGIT_CYCLES` | 100,000 | Integer of 2 or more. Other values were not simulated. | Cycles per digit slot; eight slots per scan, about 1 ms per digit and 125 Hz refresh at 100 MHz (spec timing section). The interview answer asks for 131072 cycles instead; the RTL default is 100000. Spec timing: 100000 sys_clk cycles per digit, approximately 1 ms per digit and 125 Hz for an eight-digit scan. |
| `UART_BAUD_DIVIDER_CYCLES` | 868 | Integer of 2 or more, because the receiver samples at half a bit. Must match the host baud rate; only 868 was planned. | Passed to the shell as CLKS_PER_BIT; 868 gives 115200 baud at 100 MHz, the nearest integer divider (spec timing section). The shell frame timeout is fixed at 100000 cycles in the top-level instance, not a parameter. Spec timing: 115200 baud with UART_BAUD_DIVIDER_CYCLES=868, the nearest integer divider for a 100 MHz clock. |

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
| what changed since this handover (stale records, changed files, tool and knowledge-bank pins) | `python -m flow.handover fresh results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter` | no | - |
| pick the work up again from the earliest stage the change or the staleness needs; needs a model (see docs/agent.md); Vivado for any stage from synthesis on | `python -m agent resume results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter "<change request>"` | yes | - |
| run the Verifier's simulation tests; needs Icarus Verilog and cocotb, or the simulation container | `python -m pytest -q results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/tests/test_t1_dimmer_counter_rtl.py` | no | - |
| rebuild the bitstream with the flow; needs Vivado 2026.1 and a heavy slot | `flow/run_vivado.sh results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter base` | yes | - |

Tool: Vivado 2026.1. Build ID of the inputs at handover: `f966b384` (`python flow/manifest.py show results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter`: what a rebuild of today's sources and flow would carry; it changes when any build input or the flow changes, so it can differ from the build ID in an older evidence record). Knowledge-bank pin: `aa71844`.

| File | What |
|---|---|
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/spec.md`](spec.md) | the request the run started from |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/spec.yaml`](spec.yaml) | the signed-off specification written by the Clarifier |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/ARCHITECTURE.md`](ARCHITECTURE.md) | the architecture note approved before any RTL |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/rtl/t1_led_dimmer_counter.sv`](rtl/t1_led_dimmer_counter.sv) | RTL written by the Designer |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/design.xdc`](design.xdc) | pin, I/O standard and timing constraints |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/build.yaml`](build.yaml) | the build description read by the flow; its sources also include shared shell files the agent did not write (read from the repository, not copied here): shell/rtl/fpga_shell.sv, shell/rtl/reset_sync.sv, shell/rtl/shell_core.sv, shell/rtl/sync2.sv, shell/rtl/uart_rx.sv, shell/rtl/uart_tx.sv |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/model.py`](model.py) | the Modeller's reference model of the visible behaviour |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/tests/t1_dimmer_counter_bench.py`](tests/t1_dimmer_counter_bench.py) | the Verifier's cocotb benches and pytest entries |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/tests/test_t1_dimmer_counter_rtl.py`](tests/test_t1_dimmer_counter_rtl.py) | the Verifier's cocotb benches and pytest entries |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/verif/testplan.yaml`](verif/testplan.yaml) | the test plan and mutant list read by the verification gates |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/probes.yaml`](probes.yaml) | the ILA probe list of the debug build; ILA t1_counter_ila on clk_IBUF_BUFG, depth 512; probes: counter (16 bits), pwm_phase (12 bits), display_digit (3 bits) |
| [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/build/review/09_configuration-and-debug.html`](build/review/09_configuration-and-debug.html) | the review page of stage configuration-and-debug: its exit gates and their failures at the last visit |

<!-- prose:build -->
<!-- /prose:build -->

## Verified

![Verification matrix: each activity and its result](docs/handover/verification.svg)

| ID | Activity | Result | What | Evidence | Conditions |
|---|---|---|---|---|---|
| E1 | review | pass | spec.yaml was signed off after the interview; the questions asked, answered and defaulted are in the run summary | [`results/68_agent_docs/20261102-135505-a8f2/summary.json`](../summary.json) | - |
| E2 | simulation | partial | verification (flow/verif_gates.py) against the Modeller's reference model reached V1 of V3; the run asked for V1; V1 means every spec item is traced to a check and the benches use the blind model; V2 (simulation: seeded runs, a constrained-random test, bound assertions and formal tasks) did not pass: seeds run none (needs >=1); constrained random test ran False (needs True); assertions bound zero failures none (needs bound in the run; no failure); V3 (coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score) did not pass: seeds run 0 (needs >=3); functional bins pct 0.0 (0/0) (needs 100); cover properties pct 0.0 (needs 100); line pct not measured (needs 95); toggle pct not measured (needs 80); mutation score pct not measured (needs 80); no board result (V-HW) is recorded | [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/build/verif/verif_gates.json`](build/verif/verif_gates.json) | - |
| E3 | build | partial | Vivado base build under an earlier Vivado release than the pinned one: it reached bitstream, the gates of the stages it ran all passed and its timing was met; every number from that build is withdrawn (it cannot be re-measured on Vivado 2026.1 without a rebuild), so none is published | [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/build/base/gates.json`](build/base/gates.json) | - |
| E4 | build | fail | Vivado debug build with the ILA: its gates record is an error stub (JSONDecodeError: Expecting value: line 2 column 1 (char 1)) with no flow stages, and the build has no run record (build/ila/run.json): the build did not complete | [`results/68_agent_docs/20261102-135505-a8f2/t1_dimmer_counter/build/ila/gates.json`](build/ila/gates.json) | - |

Gates at handover: `clarify` pass, `board-and-device-planning` pass, `rtl-design-creation` pass, `constraints` pass, `synthesis` pass, `implementation` pass, `timing-closure` pass, `power-closure` pass, `drc-closure` pass, `configuration-and-debug` fail.

<!-- prose:verified -->
<!-- /prose:verified -->

## Measured

Every value is read from the record by `python -m flow.handover fill`, not typed.

| ID | What | Value | Runs | Source | Conditions |
|---|---|---|---|---|---|
| M1 | model cost of the run, provider-reported | 0.164748 USD | 1 | [`results/68_agent_docs/20261102-135505-a8f2/summary.json`](../summary.json) `cost_usd` | every role and the interview oracle, as the run summary records it |

<!-- prose:measured -->
<!-- /prose:measured -->

## Known gaps and limits

- **E3**: the base build was made under an earlier Vivado release than 2026.1: its result is not current and no number from it is published. Re-measure first, with the resume command in How to build (python -m agent resume), and only then rely on its gates
- **E4**: the debug build with the ILA did not complete: build/ila/gates.json is an error stub, so there is no gate result for it
- **E2**: simulation evidence is partial: verification reached V1 of V3 (the run asked for V1); the checks that did not pass or did not run are listed in the evidence row
- **configuration-and-debug**: stage configuration-and-debug did not pass its gates in this run; at its last visit: bitstream: did not run FAIL. Build records: build/base/gates.json shows the base build's bitstream stage ran and its bitstream_present gate is true; build/ila/gates.json is an error stub (JSONDecodeError: Expecting value: line 2 column 1 (char 1)) with no flow stages and there is no build/ila/run.json. The build that did not complete is the debug build with the ILA, not the base build.
- **resources**: resources not measured: no current Vivado build of this design has been recorded
- **timing**: timing not measured: no current Vivado build of this design has been recorded
- **power**: power not measured: no current Vivado build of this design has been recorded
- **latency**: latency not measured: the run measured no latency; the spec's latency promise is checked only by the benches
- **throughput**: throughput not measured: the run measured no throughput
- **latency_counts**: Counted from the RTL, not measured. A button passes two synchroniser flops and the debounce counter; the counter, the debounced state and the press count all update on the same clock edge, so the spec's "next sys_clk edge after qualification" holds. A software write takes effect on the edge after win_wr. A register read returns its data one cycle after win_rd, registered in win_rdata. The PWM comparison and the segment decode are combinational from registers, so a brightness or counter change shows at the next phase compare or digit slot.
- **clk_pin**: spec.yaml gives the clk pin as W5; design.xdc, which was built, puts clk on E3 with a 10.00 ns clock. All other pins in the spec match the XDC. The XDC governs.
- **reset_style**: spec.yaml says reset releases synchronously and resets all design state. The RTL synchronises the release only for the shell; the top-level registers use ~cpu_resetn directly (see resets). design.xdc also marks cpu_resetn as a false path, so the reset release is not timed.
- **display_scan_period**: The spec timing section and the RTL use 100000 cycles per digit, but an interview answer asks for 131072 cycles (2^17). The RTL and ARCHITECTURE.md use 100000; ARCHITECTURE.md already notes the conflict. The 131072 request was not built.
- **press_count_width**: An interview answer says the press counters are 8-bit and wrap at 256, but spec.yaml registers and the RTL use 32-bit counters wrapping at 2^32. The RTL is what was built.
- **segment_order**: The glyph table in the RTL looks written with segment a on bit 6 (zero is 7'h01), while design.xdc maps seg[0] to CA, segment a. If so, glyphs appear mirrored on the board (a swaps with g, b with f, c with e). This was not checked in simulation against the pins or on hardware.
- **reset_values**: After reset, COUNTER is 0, BRIGHTNESS is 255, CONTROL is 0 (switch brightness off, display enabled), all three press counts are 0, and DESIGN_ID reads 0x54314443 (ASCII T1DC). INPUT_STATUS has no stored state: it always shows live inputs, so its spec reset value of 0 only holds while all inputs are low.
- **input_status_raw**: INPUT_STATUS bits 7:0 are the switches, bit 8 up, bit 9 down, bit 10 centre. They are the raw pin levels captured by one flop in win_rdata, not synchronised or debounced; a read during a bounce can return any level.
- **unmapped_access**: Only offsets 0, 4, 8, 12, 16, 20, 24 and 28 decode, with exact match. A read of any other window offset returns 0. A write to any other offset, or to a read-only register, is ignored, and the shell still returns an OK status, so no error is reported.
- **partial_write**: Writes are always 32 bits; only the low bits are kept (COUNTER 16, BRIGHTNESS 8, CONTROL 2) and the upper bits are dropped without notice. Reads are zero-extended. There are no byte strobes. Reading has no side effects: reads do not clear any counter.
- **counter_priority**: Any window write, to any address including unmapped or read-only ones, suppresses a button update of COUNTER in that cycle, not only a write to COUNTER. Otherwise centre beats up, and up beats down. The three press counters increment independently of this priority, so a suppressed press is still counted.
- **control_masking**: CONTROL bit 1 blanks all digits (an high, segments off) but the scan keeps running and the LEDs are unaffected. CONTROL bit 0 swaps the brightness for both the LED duty and the two brightness digits on AN[7:6]; BRIGHTNESS is not changed.
- **pwm_rounding**: Brightness 0 is always off and 255 always on. Other values turn the LEDs on while pwm_phase is below ceil(brightness x PWM_PERIOD_CYCLES / 255), so the on-time is rounded up rather than exactly linear.
- **io_timing**: design.xdc sets input and output delays and then declares false paths from every input and to every output, so the pin paths are not checked by timing analysis.
- **parameter_ranges**: Assumption: the legal ranges in the parameter table are read from the RTL width and compare logic. Only the default values were exercised by the benches.

<!-- prose:gaps -->
<!-- /prose:gaps -->

## Next steps

1. Re-measure with python -m agent resume, so the base build runs on Vivado 2026.1; publish no resource, timing or power number until that run is recorded.
2. Find why the ILA debug build produced an error-stub gates record and no run record, then run the configuration-and-debug stage again.
3. Settle the segment bit order: compare the glyph table with the seg[0] to seg[6] pin mapping in design.xdc, fix whichever is wrong, and check on the board.
4. Reconcile spec.yaml with what was built: clk pin E3, 100000 cycles per digit, 32-bit press counters, and the unsynchronised reset release of the top-level registers. Decide whether to synchronise the design reset, as the spec asks.
5. Take the simulation evidence from V1 to V3: seeded runs, a constrained-random test, bound assertions, coverage and the mutation score. Then add a board test.

Open questions:

- What made the ILA debug build fail to produce a gates record?
- Do the digits display correctly on the board, given the segment order question?

<!-- prose:next -->
<!-- /prose:next -->

## History

| Date | Brief | PR | What |
|---|---|---|---|
| 2026-11-02 | agent run | - | produced by the agent graph; stages that passed: clarify, board-and-device-planning, rtl-design-creation, constraints, synthesis, implementation, timing-closure, power-closure, drc-closure |

<!-- prose:history -->
<!-- /prose:history -->
