# 105A: three constraint rules (owner decisions 6 to 8, 2026-11-19)

Code: `flow/constraint_gates.py`; tests: `flow/tests/test_105a_constraint_gates.py`; standard: FDA-HDL v1.5 ([docs/hdl_coding_standard.md](../../docs/hdl_coding_standard.md)); survey: [docs/constraints_survey.md](../../docs/constraints_survey.md).

| Rule | What it does | Blocks? |
|---|---|---|
| CFGBVS / CONFIG_VOLTAGE (HDL-DRC-01) | DRC CFGBVS-1/2 fail the gate `config_voltage_declared` when `boards/<board>/board.yaml` `config` cites a source and has no `status` (Basys 3, Arty S7-50, Nexys Video); the flow writes `board_config.xdc` for those boards | only for a confirmed board |
| Blanket `set_clock_groups -asynchronous` (HDL-XDC-02) | warning `async_clock_groups_review` / check `constraint_scope`: a group over a clock pair with endpoints between the clocks (`XDC-ASYNC-PATHS`) or over every clock (`XDC-ASYNC-ALL`) | never |
| XPM `SIM_ASSERT_CHK` (HDL-CDC-02) | 86 live instances set to 1 (72 changed from 0, 14 added); advisory source check `xpm_sim` (`XPM-SIM-01`) | never |

## Real Vivado 2026.1 probe (Nexys Video smoke design, XDC without the two lines, one thread)

- `probe_a` (board `nexys_video`): the flow wrote `board_config.xdc`; report_drc has no row; gates pass except none (`reports/probe_a/`).
- `probe_b` (board with no file): report_drc shows CFGBVS-1 as a Warning, `drc_clean` is true; only `power_junction_ok` fails, because no board thermal environment is set for an unlisted board (`reports/probe_b/`). The rule applied to that real report fails a confirmed board and passes an unconfirmed one.

## Stamps

The SIM_ASSERT_CHK edits change `sources_sha256` and the build stamp of every KR260 design that builds the edited RTL (b56a, b58a, b96 and variants); see the report.
