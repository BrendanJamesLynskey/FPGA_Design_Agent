# results/16_cdc_gate

This folder holds the mutant table for the 22 CDC fixtures of brief 16 (the stronger CDC gate): for each fixture, what `report_cdc` alone flags, what the structure check flags, what the injected simulation flags, and the new gate's verdict. It is superseded by the 2026.1 twin and kept only as the record the earlier site text cited.

Measured on 2025.2, superseded by `results/16_cdc_gate_2026_1`.

## Records

| File | What |
|---|---|
| `mutant_table.md`, `mutant_table.json` | the table of 22 fixtures (12 correct, 10 mutant), as markdown and as data |

## Reproduce

Not regenerated here: the Vivado columns came from the earlier release's reports, which are no longer committed. Use
`results/16_cdc_gate_2026_1`, whose command is `python3 flow/tests/fixtures/cdc_mutants/make_table.py --golden results/16_cdc_gate_2026_1/golden --vivado 2026.1 --out results/16_cdc_gate_2026_1`.

## Known gaps and limits

- Superseded by `results/16_cdc_gate_2026_1`; do not cite the Vivado columns from this folder.
- Fixtures are small hand-written designs; the simulation columns are cycle-level injection with no timing window.
