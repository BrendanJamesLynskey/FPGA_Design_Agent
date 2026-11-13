# results/14_flow_notes

This folder holds the facts behind the "Beyond the flow" site page (brief 14) that no machine-written result file contains, for the XPM CDC constraints card: the before and after of the `flow/tests/fixtures/xpm_probe` design, and the two soak-rig mutants that `report_cdc` alone accepts. Each entry in `inputs.json` names the run or report it was read from.

Measured on 2025.2, superseded by `results/vivado_2026_1_remeasure/xpm_probe.json`.

## Records

| File | What |
|---|---|
| `inputs.json` | the xpm_probe before/after entries (timing result, failing endpoints and `report_cdc` exception for the two macros) and the `report_cdc` flag for mutants M9 and M11 of the rig build; its figures are not restated here |

## Reproduce

The earlier-release probe numbers cannot be regenerated, and are replaced by `results/vivado_2026_1_remeasure/xpm_probe.json`.
That record is made by building the probe fixture as `designs/qr_xpm_probe` through `flow/run_vivado.sh`, once with
`FDA_XPM_CDC=0` and once without, both with `FDA_STOP_AFTER=route` (a Vivado run, so a heavy slot is needed).
The M9 and M11 entries are transcribed from a rig build report and have no command.

## Known gaps and limits

- Superseded: made on the earlier Vivado release, and the site should read the 2026.1 record instead.
- The M9 and M11 `report_cdc` flags were taken from the text of a report that is not in the repository, and were not re-run on 2026.1.
- One probe design with two crossings; it shows the effect of the constraint script on that design only.
