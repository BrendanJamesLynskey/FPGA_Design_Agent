# results/95_boards: board smoke builds and the licence probe

Records from brief 95 (the board catalogue): one generated smoke design per catalogue board that has a PL clock and a pin list, built with Vivado 2026.1 through synthesis, placement, routing and the bitstream with the board's own constraints, and a probe of which parts the installed Basic-tier licence takes through the flow. Nothing here was run on a board.

## Records

| File | What | Made by |
|---|---|---|
| `licence_probe.json` | for each of the 14 parts in the catalogue, whether a one-flop out-of-context design goes through synthesis, placement and routing on the installed licence (every part did) | `tools/board_licence_probe.tcl` |
| `<board>/smoke.json` | the smoke build's gate results, the hashes of the committed smoke XDC and top, and the build's figures; `passed` is true only when every gate passed | `python3 tools/board_smoke.py record <board>` |
| `<board>/gates.json`, `run.json`, `run_vivado.log`, `*.rpt` | the build's own records (gates, run time and memory, console log, DRC, methodology, timing, utilisation, power) | `flow/run_vivado.sh boards/<board>/smoke base` |

Results, in words: 13 boards have a passing smoke build (basys3, arty_a7_35t, arty_a7_100t, arty_s7_50, cmod_a7_35t, nexys_video, genesys2, zybo_z7_10, zybo_z7_20, cora_z7_07s, cora_z7_10, pynq_z2, zedboard). aup_zu3 reached the bitstream with timing, DRC and methodology clean but failed the exceptions gate on a Vivado 12-1411 critical warning at its differential clock input (its routed I/O report shows the clock on the documented pins), so it is not labelled built. The probe and the two builds on parts expected to need a paid licence (Artix-7 200T, Kintex-7 325T) show that the installed 2026.1 Basic licence takes them through the bitstream; the earlier guess that they needed a paid licence was wrong.

Two board-file defects were found by building, not by reading: the Arty S7's bank 34 holds SSTL135 ports, so its smoke XDC needs `INTERNAL_VREF` for that bank (recorded in its board file as derived, not read from a document); and the AUP-ZU3 clock warning above.

## Reproduce

- `python3 tools/board_smoke.py gen <board>`, then `flow/run_vivado.sh boards/<board>/smoke base` under a heavy slot (a build takes about two to three minutes, at two threads), then `python3 tools/board_smoke.py record <board>`.
- The probe: `vivado -mode batch -source tools/board_licence_probe.tcl -tclargs <out.json> <part> ...` under a heavy slot. The committed `licence_probe.json` wraps its output with the method.
- Two builds shared no slot: each took one slot in turn. `run.json` records each build's peak memory (`vivado_peak_rss_mib`; the largest is 3902 MiB, aup_zu3), so by the admission rule's 6 GB limit two smoke builds could share two slots, but nothing was run in parallel.

## Known gaps and limits

- A smoke build proves the board file's pins and standards pass the tool's checks. It does not show the board works: nothing was loaded onto any board, LED and button polarity are unconfirmed, and the Zynq builds are PL-only (no PS).
- The licence probe uses an out-of-context design, so it cannot write a bitstream; only the boards with a smoke build show the bitstream step. The ZCU104 (Zynq UltraScale+ EV) has no smoke map, so its bitstream step is unverified.
- The AUP-ZU3 critical warning was not resolved: moving the LOC to the P port only, and ordering the pair, did not remove it.
