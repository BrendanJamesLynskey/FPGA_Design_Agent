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

Compared with the earlier release's record (`results/24_fsm`): all 37 synthesis results are identical (counts, encodings and
slacks); 9 of the 12 routed variants are identical and 3 moved, by placement alone: `sep_base` (setup slack on the controller's own
paths -1.286 to -0.660 ns, register-to-output -1.544 to -1.859 ns), `sep_in1` and `sep_out1` (a few tens of picoseconds). One
routed run each; such moves are run-to-run placement differences, not a trend. Of the summary numbers only the decoded-output slack
changed (-1.544 to -1.859 ns). Coverage (simulation) and formal results are tool-independent and are read from `results/24_fsm`.
The I/O study, the family runs, the drills and the simulator survey of brief 24 were not re-run.
