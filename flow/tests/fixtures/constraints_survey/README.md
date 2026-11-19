# constraints_survey: small designs for brief 105's measurements

Three out-of-context designs, one Vivado implementation per variant (`run_all.sh`), measured by `measure.tcl`. They back claims in
[docs/constraints_survey.md](../../../../docs/constraints_survey.md); the recorded runs and their summary are in
[results/105_constraints_survey/](../../../../results/105_constraints_survey/README.md).

| Experiment | RTL | Question | Variants |
|---|---|---|---|
| M1 | `rtl/m1_sync.sv` | What does `(* ASYNC_REG *)` change for a two-flop synchroniser (placement, delay, MTBF report, rule rows)? | `AREG=1` or `0`, on xc7a100t and xck26 |
| M2 | `rtl/m2_fanout.sv` | What do `MAX_FANOUT` and `DONT_TOUCH` do to a register driving 3000 clock enables? | `MODE` 0 (none), 1 (`MAX_FANOUT`), 2 (both), 3 (`DONT_TOUCH`) on xc7a100t |
| M3 | `rtl/m3_bus.sv` | What does `set_bus_skew` change for a 16-bit Gray pointer? | `xdc/m3_a` none, `m3_b` datapath-only delay, `m3_c` plus bus skew |

Use: needs Vivado 2026.1 (`flow/version_pin.py --vivado`) and the heavy slot (`_handoff/take_heavy_slot.sh`), `FDA_VIVADO_THREADS=1`.
`bash run_all.sh <out dir> [variant ...]` runs the variants in order (about 2 to 4 minutes each at one thread).
Each writes `<out>/<variant>/metrics.txt` and the reports.

Limits: all runs are out-of-context (no pins, so no I/O delay model), which is why a hold slack of a few picoseconds below 0 can appear on a
register-to-register path with no clock uncertainty; the numbers are comparisons between variants, not closure results.
