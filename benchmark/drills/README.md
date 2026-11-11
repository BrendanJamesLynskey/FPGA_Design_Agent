# Constraint drills (brief 20)

Development drills for the timing-constraint work of brief 20. They sit **outside** the benchmark splits: they are not in
`split.yaml`, the course split or the v2 ledger, were never submitted for a draw, and are never held out. The agent may run on
them freely; nothing here is a score of the benchmark.

Each drill has the usual task layout (`spec.md` for the agent; `hidden/` for the oracle, the acceptance bench, the model and the
mutants; `ref/` for a reference design) plus `hidden/constraints.yaml`, what the constraint grader requires.

| Drill | What it asks | Graded by |
|---|---|---|
| [d20_slow_fsm_ramp](d20_slow_fsm_ramp/spec.md) | A slow control FSM on the board's single 100 MHz clock, advanced by a 1-in-8 tick, sequencing a fast unit that must take the FSM's level only on the tick; the 8-clock paths constrained as such (setup 8, hold 7) on exactly the tick-enabled registers | acceptance bench (`benchmark/tools/run_task.py`) + [lib/grade_constraints.py](lib/grade_constraints.py) |
| [d20_adc_capture](d20_adc_capture/spec.md) | A system-synchronous ADC on the board clock, constrained from a data-sheet excerpt (tCO 1.0/5.0 ns, trace 0.5 ns) for setup and hold in IOB flip-flops; the oscillator's jitter given to the timer; a 0.3 ns implementation-only setup margin kept out of sign-off; the button, LEDs and UART left without invented delays (brief 20 part B) | acceptance bench + [lib/grade_io.py](lib/grade_io.py) |
| [d24_registered_outputs](d24_registered_outputs/spec.md) | A bus-burst sequencer on Pmods JA/JB whose output pins must come straight from flip-flops (the partner has no slack for logic); all outputs may trail the state table by the same one clock (brief 24) | acceptance bench (cycle-exact against a model, plus the counters) + [lib/grade_fsm.py](lib/grade_fsm.py) (pin drivers from the routed checkpoint; records registered, lookahead or combinational) |
| [d24_no_extra_latency](d24_no_extra_latency/spec.md) | The same sequencer where no output may be later than the state table and `cmd_ack` answers in the clock of the command (Mealy): registering the outputs fails, lookahead or combinational decode passes (brief 24) | acceptance bench + `lib/grade_fsm.py` (records the choice) |

`lib/grade_constraints.py <task> <design>` grades the agent's routed build: only the allowed clocks; FDA-CON-5/-10 clean;
the flow's exception check after routing clean; every relaxed path's requirement is N periods and its registers share a real clock
enable (from `flow/mcp_paths.tcl` on `post_route.dcp`, run by `lib/mcp_paths.tcl`); no broad waivers. It records the choice the
agent made (multicycle, or a pipeline with no exception). The reference and the constraint mutants (E10b: the copy taken on every
clock; E10c: the multicycle on `all_registers`) were built through `flow/run_vivado.sh` and graded; the results are in
[results/20_timing_exceptions/drills](../../results/20_timing_exceptions/drills).

`lib/grade_io.py <task> <design>` (part B) grades the agent's routed build: the interface's `-max`/`-min` equal the data-sheet
formula, relative to the board clock, IOB-packed, with setup and hold met (`flow/io_check.py` with the task's interfaces);
FDA-CON-11/-12/-13 clean; the board clock's `set_input_jitter`; and the margin as build.yaml `timing_margin_ns`, applied by the
flow, with no setup `set_clock_uncertainty` in design.xdc. The reference and four constraint mutants (margin in design.xdc,
invented slow-port delays, `-min`/`-max` swapped, no input jitter) were built through `flow/run_vivado.sh` and graded
(`flow/tests/test_20b_drill_grader.py`).

## FSM drills (brief 24)

Both drills share the controller of `flow/tests/fixtures/fsm_discipline` (11 states, a 4-beat burst, an 8-clock acknowledge window, a retry, a timeout,
a 3-clock cool-down) with five input pins and eight output pins, and differ in the output rule. The hidden bench drives random inputs that do
not depend on the outputs and compares every output pin, every clock, with `hidden/model.py` allowing the lag the task allows; it also reads the
counters over the shell. Ten functional mutants each (timeout, burst length, nack, cool-down, counters, CLEAR, ack priority, last beat, plus the output-style
ones), all killed (`flow/tests/test_24_drills_rtl.py`); on the reference the bench itself reaches every state and legal transition
(`flow/fsm_cov_cocotb.py`). `lib/grade_fsm.py <task> <design>` runs the bench on the design's `rtl/`, reads the lag the pins follow, reads the driver of each
output pin from `build/base/post_route.dcp` (`lib/driver_cells.tcl`), and records the choice: flip-flop-driven with lag 1 is a registered decode of the state,
flip-flop-driven with lag 0 is a lookahead decode, LUT-driven with lag 0 is combinational. A seed passes the first drill when the bench passes and every output
pin is flop-driven.
