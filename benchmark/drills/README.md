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
