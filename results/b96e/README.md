# results/b96e: a lower-latency elastic buffer for the 10G link (brief 96E)

This folder holds the simulation records and the Vivado build of brief 96E, which added `rtl/rate_match_gp.sv` (our own gray-pointer elastic buffer, `RM_OWN = 1`) beside brief 96C's buffer on `xpm_fifo_async`, and the accounting of the board's +11 clocks. No board was used for the brief itself; the board run of 2026-11-19 is recorded below.

## Records
- `core_lat_sim.sh`, `core_lat.py`, `core_lat_sim.json`: the whole core in xsim 2026.1 with AMD's real XPM macros (`sim/tb_lat_core.sv`, `sim/gth_wiz_model96e.sv`), three receive paths, four phases between the clocks, 8 orders per point: tick-to-trade, the receive-start stamp path (what E and L are made of on the board) and D.
- `rm_latency_sim.sh`, `rm_latency_sim.json`: the buffer alone (`sim/tb_rm_latency.sv`), by implementation and fill target.
- `builds/rm_gp/`, `builds/rm_gp_direct/`: `cdc_summary.txt`, `digest.json` (timing, utilisation, power, gates), `run.json` (memory, wall time, stamp), `commit.txt`, `dirty.txt`, `wall.txt`, `run_vivado.log`; `build_one.sh` is the slot-taking build script.

## Measured
**Whole core, mean over four phases (clocks of 6.2058 ns):** tick-to-trade 10.6 (97C path), 15.9 (96C buffer on xpm_fifo_async), 12.9 (own buffer, ENT_SYNC 1, build rm_gp): +2.3 against 97C; 11.8 (direct-read variant, build rm_gp_direct): +1.2. Receive-start path 5.6, 10.1, 7.0, 6.0; D 10.4, 11.1, 11.3, 11.2.
**Build `rm_gp`:** every gate true, WNS +0.164 ns, WHS +0.010 ns, 6,730 LUT, 18,938 FF, 1.105 W (vectorless), Tj 48.2 C, 1,422 s, resident peak 4,398 MiB; report_cdc: no CDC-1 row, none critical; stamp b72d3f46.
**Build `rm_gp_direct`:** two gates fail (`post_synth_cdc_no_critical`, `cdc_no_critical`): report_cdc lists 38 CDC-1 Critical rows (`cdc_summary.txt`); WNS +0.079 ns.
**Equivalence of the default path (records in `eqy/`):** `results/b96c/eqy_default` re-run on this branch: default 219 partitions proved, all3 218 proved, planted change fails in `c_err`.
**Rejected first version:** `builds_v1_per_entry_sync/` and `v1_per_entry_sync/` (per-entry synchronisers with a 2-flop pointer: WNS +0.105 ns, stamp 1a2fa1a8; margin 0 to 1 clock).

## Board run, 2026-11-19 (KR260, fibre loopback, build rm_gp)

`hw/20261119_231251/rm_gp/stage3.json` (with `session.json`, `program.json`, `git_heads.txt`): build stamp 98577dbc read back over JTAG and matching; 100 link restarts, 0 failed to lock (lock 68 to 277 clocks, median 176); 5 orders per restart, 500 sent and 500 fired; every safety counter (poisoned, dropped, underrun, late, stale, bad, err, toolong, order_bad, blocked) 0; inside the recommended operating conditions at start and end (26.9 to 27.9 C).

| measure (clocks of 6.2061 ns) | min | median | max |
|---|---|---|---|
| E, minimum per link | 21 | 21.0 | 22 |
| L, minimum per link | 53 | 54.0 | 55 |
| L, maximum per link | 54 | 55.0 | 55 |
| D from the medians of the minima | | 12.0 | |

Predicted before the run: L of about 54 to 55 clocks, including the 1.25 clocks of D that simulation does not reproduce. Measured: 54.0. A fibre loopback has no frequency offset between the two ends, so this run does not exercise the buffer's slip path; that waits for the real-offset test (`docs/real_offset_plan.md`, needs a 10G NIC). Run with `BOARD_LINUX_DOWN_OK=1` (the board's Linux stops after a JTAG load) and `FDA_VIVADO_MAX=2` under a heavy slot.

## Reproduce
`bash results/b96e/core_lat_sim.sh 0:0 1:0 1:1` then `python3 results/b96e/core_lat.py build/core_lat96e results/b96e/core_lat_sim.json` (xsim, about 15 minutes); `bash results/b96e/rm_latency_sim.sh 0:4 0:1 1:1`; `python3 -m pytest designs/b96_kr260_10g/tests`; the build: `results/b96e/build_one.sh rm_gp`.

## Known gaps and limits
Apart from the board run above, nothing here ran on a board. The transceiver is a stand-in in xsim (the real model is refused), so the GT's own delays and the phase it gives are absent; 1.25 clocks of the board's +11 are not reproduced by simulation (design.md section 11). The simulated copies of the RTL replace `always_ff` by `always` and `INIT_SYNC_FF` 0 by 1 (simulation initial values only). The real offset test is a plan (`docs/real_offset_plan.md`), not a result.
