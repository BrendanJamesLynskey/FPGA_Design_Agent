# results/16_cdc_gate_2026_1: brief 16's CDC fixtures on Vivado 2026.1 (brief 49)

The 22 CDC fixtures (`flow/tests/fixtures/cdc_mutants`) synthesised on **Vivado 2026.1** (Basic licence tier),
xc7a100tcsg324-1, on 2026-11-11 under a heavy slot (`run_all.sh`, one Vivado per fixture, 6 GB scope); the reports
(`golden/<fixture>/cdc_synth.rpt`, `cdc_paths_synth.rpt`, dates, hosts and command lines removed) feed the same table:

    python3 flow/tests/fixtures/cdc_mutants/make_table.py --golden results/16_cdc_gate_2026_1/golden --vivado 2026.1 --out results/16_cdc_gate_2026_1

The simulation columns are re-run by the same command (cocotb on Icarus, seeds 1-3; no Vivado). **Result: the table is
identical to the earlier release's** (`results/16_cdc_gate`): every report_cdc verdict, structure finding and gate verdict.
The soak rig's own report_cdc results (mutants M9 and M11, rig build) were not re-run on 2026.1 and are withdrawn from the site.

## Records

| Path | What |
|---|---|
| `mutant_table.md`, `mutant_table.json` | the 22-fixture table: `report_cdc` alone, structure check, injected simulation (seeds 1-3) and the new gate's verdict |
| `golden/<fixture>/` | the stamped `cdc_synth.rpt` and `cdc_paths_synth.rpt` of each fixture on Vivado 2026.1 (dates, hosts and command lines removed) |

## Reproduce

The table: the `make_table.py` command above (the simulation columns need Icarus and cocotb, no Vivado). The golden
reports: `flow/tests/fixtures/cdc_mutants/run_all.sh` (synthesis-only Vivado 2026.1, one run per fixture; heavy slot).

## Known gaps and limits

- Synthesis-only reports: no place and route, no board. The simulation injection is cycle-level (an extra destination cycle with probability 1/2), with no timing window.
- Fixtures are small hand-written designs, not a sample of real designs; a design with no crossing passes the gate at once.
- The soak rig's `report_cdc` results (mutants M9 and M11) were not re-run on 2026.1 and are withdrawn from the site.
- Supersedes `results/16_cdc_gate`.
