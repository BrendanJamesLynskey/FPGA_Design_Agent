# Brief 174: design package, pilots

Records of the runs behind [docs/design_package.md](../../docs/design_package.md): a package folder (spec, board materials, an optional existing design) is ingested into sourced facts, and the facts are checked against the flow's `boards/<board>/board.yaml`. Dates come from the machine clock (2026-11-22).

## Records

- `check_kr260_before_fix.txt`: `flow.package check packages/kr260` against `boards/kr260/board.yaml` as it was before the fix: one conflict (PHY: 88E1111 in the board file, DP83867 in BOM row 60).
- `check_kr260_after_fix.txt`: the same after the fix: no conflict; two confirmations (SFP+ reference clock 156.25 MHz, PL clock 25 MHz); nothing missing.
- `check_nexys_a7_100t.txt`: the Nexys A7-100T pilot against its board file: no conflict.
- `offchip_hints_kr260.yaml`: `flow.package offchip packages/kr260` (trace length per net, carrier copper only).
- `pilot_b58a/sim_before.txt` and `sim_after.txt`: iverilog 12 on `packages/b58a_change/tests/lat_hist_lost_tb.sv`, the unchanged `lat_hist` (`wrapped`) and the changed one (`saturated`); `pilot_b58a/frozen_check_proposed.txt`: the frozen-file gates on the change (pass). The change is `packages/b58a_change/lat_hist_saturate.patch`.
- `pytest_174.txt`: the unit tests (`flow/tests/test_174_package.py`, `agent/tests/test_174_package_hook.py`).

## Reproduce

Run these from the repository root; the first three need the private AMD files in the KR260 package folder, the rest need nothing private.

```
python3 -m flow.package init packages/kr260        # needs the private AMD files in packages/kr260/board/ (xlrd for the .xls BOM)
python3 -m flow.package ingest packages/kr260
python3 -m flow.package check packages/kr260
python3 -m flow.package existing packages/b58a_change
python3 -m pytest flow/tests/test_174_package.py agent/tests/test_174_package_hook.py
```

## Known gaps and limits

- The KR260 inputs are AMD's files: private and git-ignored, so only the manifest hashes and the derived facts are committed; a clone cannot re-run the KR260 ingest.
- The BOM `.xls` needs `xlrd`, which the flow does not depend on.
- No Vivado synthesis was run for the b58a pilot (both heavy slots were taken); the pilot change is checked in simulation only.
- UG1092, which the knowledge bank cites for the Marvell PHY, was not available to re-read.
