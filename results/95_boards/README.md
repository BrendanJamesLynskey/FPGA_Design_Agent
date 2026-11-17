# results/95_boards: board smoke builds and the licence probe

Records from brief 95 (the board catalogue): one generated smoke design per free-tier catalogue board, built with Vivado 2026.1 through post-route and the bitstream with the board's own constraints, and a probe of which parts the installed licence can implement. Nothing here was run on a board.

## Records

| File | What | Made by |
|---|---|---|
| `licence_probe.json` | for each part in the catalogue, whether a one-flop design goes through synthesis, placement and routing on the installed Basic-tier licence | `tools/board_licence_probe.tcl` |
| `<board>/smoke.json` | the smoke build's gate results, the hashes of the committed smoke XDC and top, and the build's figures | `python3 tools/board_smoke.py record <board>` |
| `<board>/gates.json`, `run.json`, `*.rpt` | the build's own records | `flow/run_vivado.sh boards/<board>/smoke base` |

Status at the time of writing: the builds are queued behind other sessions' heavy jobs; boards without a `smoke.json` here are labelled `documented` in [docs/board_catalogue.md](../../docs/board_catalogue.md).

## Reproduce

- `python3 tools/board_smoke.py gen <board>`, then `flow/run_vivado.sh boards/<board>/smoke base` under a heavy slot (each build is small), then `python3 tools/board_smoke.py record <board>`.
- The probe: `vivado -mode batch -source tools/board_licence_probe.tcl -tclargs <out.json> <part> ...` under a heavy slot.

## Known gaps and limits

- A smoke build proves the board file's pins and standards pass the tool's checks. It does not show the board works: nothing was loaded onto any board, LED and button polarity are unconfirmed, and the Zynq builds are PL-only (no PS).
