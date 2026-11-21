# results/b131: build dbg_xvc (an ILA reached over Ethernet), implementation against its parent; nothing ran on a board

Brief 131. Build `dbg_xvc` of `designs/b96_kr260_10g` (the eyescan build plus a PS-AXI Debug Bridge and one ILA) and its parent `eyescan`, both implemented on Vivado 2026.1 with the same flow commit, 2 threads, MemoryMax 12G. Design notes: `designs/b96_kr260_10g/dbg_xvc/docs/dbg_xvc.md`.

## Records
- `builds/eyescan/`, `builds/dbg_xvc/`: `digest.json` (timing, utilisation, power, gates), `gates.json` (stages trimmed), `run.json` (wall time, memory, stamp), `stages.txt`.
- `compare/summary.json`: the two builds' cells under `u_core`, worst slack per clock and through the receive and transmit paths, the tapped nets' fanout and the utilisation difference (made by `dbg_xvc/scripts/compare_builds.py` from `dump/`).
- `dump/{parent,dbg}/`: the raw dumps of `dbg_xvc/scripts/dump_netlist_timing.tcl` on each routed checkpoint.

## Measured
- Both builds meet timing with positive slack on every clock: WNS 0.314 ns (parent) and 0.323 ns (dbg_xvc), WHS 0.011 ns in both.
- dbg_xvc adds 1821 LUT, 2865 FF and 1.5 BRAM tiles (the ILA's capture memory); peak anonymous memory 9647 MiB against 8111 MiB.
- Cells under `u_core` with RTL-given names: 14311 in both, 0 removed, 0 added, 0 changed. LUT-type cells (tool-named): 25 more in total, none in the receive path.
- Receive-path worst setup slack 0.444 ns (parent) and 0.333 ns (dbg_xvc); transmit path 0.314 and 0.323. Run-to-run variation was not measured.
- Flow gates: the parent passes all; dbg_xvc passes every post-route timing gate but fails `post_synth_no_unconstrained_endpoints`, `post_synth_methodology_no_critical`, `post_synth_cdc_structure_clean`, `post_synth_exceptions_clean`, `post_place_hold` and `exceptions_clean` (debug-IP clock and exception handling; table with causes and what is unconfirmed in the design note).
- Earlier attempts: three runs at the 6 GiB cap were OOM-killed (two ILA sizes, 1 and 2 threads); the first 12G run's gate record (receive clock named `dbg_rxclk`) was replaced by the second after the rename.

## Reproduce
Take a heavy slot (the dbg_xvc and eyescan builds peak at about 9.7 and 8.1 GiB, so they need MemoryMax above the usual 6G, which needs the owner's permission and no other large Vivado job), then build `designs/b96_kr260_10g/dbg_xvc` and `designs/b96_kr260_10g/eyescan` with `flow/run_vivado.sh <design> base`. Run `dbg_xvc/scripts/dump_netlist_timing.tcl` in Vivado batch mode on each build's `post_route.dcp`, then `dbg_xvc/scripts/compare_builds.py` on the two dump folders and the two `gates.json` files.

## Known gaps and limits
- No board run: the board test is pre-registered (`designs/b96_kr260_10g/dbg_xvc/docs/xvc_board_test.md`) and not run; the ILA, bridge and Linux XVC server have never been loaded or connected.
- Six flow gates fail for dbg_xvc (listed above); the causes of the CDC structure and exception failures are not found.
- One run of each build: the 0.111 ns drop of the receive path's setup slack is not separated from run-to-run variation.
- The LUT-type cell count changes (25 more under `u_core`) are not explained.
