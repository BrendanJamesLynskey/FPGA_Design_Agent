# results/20_timing_exceptions_2026_1: brief 20's timing-exception and I/O-timing fixtures on Vivado 2026.1 (brief 49)

Re-run on **Vivado 2026.1** (Basic licence tier), xc7a100tcsg324-1, on 2026-11-11, under heavy slots (each Vivado in its own
6 GB scope). Reports are trimmed and stripped of dates, hosts and command lines, as the fixture goldens are.

    FDA_TEX_IMPL="tex_e1 tex_e3 tex_e8 tex_e8b tex_e10 tex_e10b tex_e10d" flow/tests/fixtures/timing_exceptions/run_all.sh <out>
    vivado -mode batch -source flow/tests/fixtures/timing_exceptions/followup.tcl -tclargs <out> benchmark/drills/lib
    flow/tests/fixtures/timing_exceptions/make_table.py --collect <out> --golden results/20_timing_exceptions_2026_1/golden --vivado 2026.1 --out results/20_timing_exceptions_2026_1
    flow/tests/fixtures/io_timing/run_all.sh <out_io>
    FDA_IO_GOLDEN=results/20_timing_exceptions_2026_1/golden_io flow/tests/fixtures/io_timing/collect_golden.py <out_io>
    FDA_IO_GOLDEN=... FDA_IO_OUT=results/20_timing_exceptions_2026_1 FDA_IO_VIVADO=2026.1 flow/tests/fixtures/io_timing/make_table.py

| File | What |
|---|---|
| `exceptions_table.md`, `.json`, `golden/` | the 15 one-fault exception fixtures (7 placed and routed) |
| `io_table.md`, `.json`, `golden_io/` | the I/O-delay and virtual-clock fixtures, routed |
| `vivado_stamps.txt` | the Tool Version line (Vivado v.2026.1, build 6511674) of the raw report each excerpt was cut from: the trimmed excerpts drop that header, and many are byte-identical to the 2025.2 goldens because the results are |
| `raw_u/` | the untrimmed clock-uncertainty reports of the 2026.1 run (dates, hosts and paths removed), which carry the version header |
| `uncertainty.md`, `.json`, `golden_u/` | the clock-uncertainty runs U1-U8 (`measure_u.tcl` on `io_u`) and the Clocking Wizard read-back (`flow/clkwiz_probe.tcl u:100:MMCM:200,100`) |

    FDA_IO_GOLDEN_U=results/20_timing_exceptions_2026_1/golden_u FDA_IO_OUT=... FDA_IO_VIVADO=2026.1 flow/tests/fixtures/io_timing/make_uncertainty.py --collect <measure_u out> <clkwiz.jsonl>

**Result: all three tables are identical to the earlier release's** (`results/20_timing_exceptions`): every Vivado rule, ignored
status, coverage count, slack before and after routing, and every flow verdict. 2026.1 also raised no TIMING-46 for a multicycle on
registers with a tied clock enable, after synthesis or after placement (followup.tcl, E3, E10B, E10C). The agent drill runs (agent
outcomes, not Vivado measurements) were not re-run.

## Records

The files and directories are listed in the table above: the exception table and `golden/` (7 placed and routed, 15 in all),
the I/O table and `golden_io/`, the uncertainty table, `golden_u/` and `raw_u/`, and `vivado_stamps.txt`.

## Reproduce

The commands above (Vivado 2026.1, a heavy slot, one Vivado per fixture in its own memory scope). No board or paid agent run.
`<out>` and `<out_io>` are scratch directories. The drill runs are not regenerated here.

## Known gaps and limits

- Fixtures are out of context (no board clock tree): only routed numbers support claims about hold, not the synthesis estimates on clock crossings.
- Basic licence tier; one run per fixture, so small placement-dependent moves would not show as a trend.
- The agent drill runs were not re-run on 2026.1; their records are in `results/20_timing_exceptions/drills`.
- The multicycle-with-tied-enable check is structural: an enable in the data cone is accepted without proving the register holds.
- Measured on Artix-7 (xc7a100t) only.
