# results/24_fsm_2026_1: the FSM reference controller on Vivado 2026.1 (brief 49)

Brief 24's controller variants (`flow/tests/fixtures/fsm_discipline`) re-run on **Vivado 2026.1** (Basic licence tier),
xc7a100tcsg324-1, 2.5 ns clock, out of context, on 2026-11-11, each Vivado in its own 6 GB scope under a heavy slot:

    flow/tests/fixtures/fsm_discipline/run_all.sh <dir> 0                 # synthesis, every variant (synth/*.kv)
    flow/tests/fixtures/fsm_discipline/run_all.sh <dir> 1 <12 variants>   # opt, place and route (impl/*.kv)
    python3 results/24_fsm_2026_1/make_tables.py                          # the tables and summary.json

| File | What |
|---|---|
| `synth/*.kv`, `synth_table.json` | 37 variants, synthesis only |
| `impl/*.kv`, `impl_table.json`, `impl_table.md` | 12 main variants, routed |
| `summary.json` | the numbers the site's FSM drawer quotes |
| `vivado_stamps.txt` | the version line of the Vivado log behind every `.kv` (all v2026.1; a `.kv` carries no version) |
| `simprobe/` | the simulator survey re-run: Icarus and Verilator as before; xsim 2026.1 compiles the covergroup, and its report tool `xcrg` stops for want of a simulator licence on the Basic tier |

Compared with the earlier release's record (`results/24_fsm`): all 37 synthesis results are identical (counts, encodings and
slacks); 9 of the 12 routed variants are identical and 3 moved, by placement alone: `sep_base` (setup slack on the controller's own
paths -1.286 to -0.660 ns, register-to-output -1.544 to -1.859 ns), `sep_in1` and `sep_out1` (up to about 0.1 ns). One
routed run each; such moves are run-to-run placement differences, not a trend. Of the summary numbers only the decoded-output slack
changed (-1.544 to -1.859 ns). Coverage (simulation) and formal results are tool-independent and are read from `results/24_fsm`.
The I/O study, the family runs and the drills of brief 24 were not re-run.

## Records

The table above lists each file. `synth/*.kv` and `impl/*.kv` are the raw per-variant results; `make_tables.py` builds the tables.

## Reproduce

The three commands above (Vivado 2026.1, a heavy slot, one Vivado per variant). The simulator survey in `simprobe/` is
re-run by the survey script in the earlier folder's `simprobe/`. No board or paid agent run.

## Known gaps and limits

- One routed run per variant: the three moved variants are placement differences, not a trend.
- Out of context (no I/O, no board); synthesis-only numbers carry unplaced wire delay.
- Coverage and formal results are not re-run here; the I/O study, family runs and drills were not repeated.
- The xsim report tool `xcrg` stops for want of a simulator licence on the Basic tier, so xsim coverage reports are not available.
- Supersedes `results/24_fsm` for the Vivado tables.
