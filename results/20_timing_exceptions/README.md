# results/20_timing_exceptions

This folder holds the original records of brief 20: the timing-exception fixtures, the I/O-delay and virtual-clock fixtures and the clock-uncertainty runs on a small Artix-7 design, plus the agent drill runs graded by code. Only `drills/` is still current; the Vivado tables are superseded by the 2026.1 twin.

Measured on 2025.2, superseded by `results/20_timing_exceptions_2026_1`.
Still current: `drills/` (agent runs graded by code; not a measurement of a Vivado release).

## Records

| Path | What |
|---|---|
| `exceptions_table.md`, `.json` | the one-fault timing-exception fixtures: Vivado rule, status and slack per fixture, and the flow's verdict |
| `io_table.md`, `.json` | the I/O-delay and virtual-clock fixtures |
| `uncertainty.md`, `.json` | the clock-uncertainty runs and the Clocking Wizard read-back |
| `drills/` | the two timing-exception drills (`d20_adc_capture`, `d20_slow_fsm_ramp`) run on the agent: constraints, hidden-bench results and XDC history per run, and the Icarus results |

## Reproduce

The tables are not regenerated here (superseded): use the commands in `results/20_timing_exceptions_2026_1/README.md`
(Vivado, heavy slot). The drill records come from paid agent runs (`benchmark/drills`) and cannot be regenerated without
repeating them.

## Known gaps and limits

- Superseded by `results/20_timing_exceptions_2026_1` for every Vivado table; do not cite its numbers from this folder.
- The drills are agent outcomes graded by code, not a Vivado measurement, and are few: they say the drills are gradeable, not a rate.
- The drill runs use the 100 MHz board clock, so no MMCM is needed in simulation; the gate is measured on Artix-7 only.
- Fixtures are out of context (no board clock tree), so synthesis hold estimates on clock crossings are not real; only routed numbers are used for hold.
