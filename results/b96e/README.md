# results/b96e: a lower-latency elastic buffer for the 10G link (brief 96E)

This folder holds the simulation records and the Vivado build of brief 96E, which added `rtl/rate_match_gp.sv` (our own gray-pointer elastic buffer, `RM_OWN = 1`) beside brief 96C's buffer on `xpm_fifo_async`, and the accounting of the board's +11 clocks. No board was used for this brief.

## Records
- `core_lat_sim.sh`, `core_lat.py`, `core_lat_sim.json`: the whole core in xsim 2026.1 with AMD's real XPM macros (`sim/tb_lat_core.sv`, `sim/gth_wiz_model96e.sv`), three receive paths, four phases between the clocks, 8 orders per point: tick-to-trade, the receive-start stamp path (what E and L are made of on the board) and D.
- `rm_latency_sim.sh`, `rm_latency_sim.json`: the buffer alone (`sim/tb_rm_latency.sv`), by implementation and fill target.
- `builds/rm_gp/`: `digest.json` (timing, utilisation, power, gates), `run.json` (memory, wall time, stamp), `commit.txt`, `dirty.txt`, `wall.txt`, `run_vivado.log`; `build_one.sh` is the slot-taking build script.

## Measured
**Whole core, mean over four phases (clocks of 6.2058 ns):** tick-to-trade 10.6 (97C path), 15.9 (96C buffer on xpm_fifo_async), 11.8 (own buffer): +1.2 against 97C. Receive-start path 5.6, 10.1, 6.0; D 10.4, 11.1, 11.2.
**Build `rm_gp`:** every gate true, WNS +0.105 ns, WHS +0.011 ns, 6,836 LUT, 18,935 FF, 1.118 W (vectorless), Tj 48.3 C, 1,465 s, resident peak 4,412 MiB, no scope cap hits; stamp 1a2fa1a8.
**Equivalence of the default path (records in `eqy/`):** `results/b96c/eqy_default` re-run on this branch: default 219 partitions proved, all3 218 proved, planted change fails in `c_err`.

## Reproduce
`bash results/b96e/core_lat_sim.sh 0:0 1:0 1:1` then `python3 results/b96e/core_lat.py build/core_lat96e results/b96e/core_lat_sim.json` (xsim, about 15 minutes); `bash results/b96e/rm_latency_sim.sh 0:4 0:1 1:1`; `python3 -m pytest designs/b96_kr260_10g/tests`; the build: `results/b96e/build_one.sh rm_gp`.

## Known gaps and limits
Nothing here ran on a board. The transceiver is a stand-in in xsim (the real model is refused), so the GT's own delays and the phase it gives are absent; 1.25 clocks of the board's +11 are not reproduced by simulation (design.md section 11). The simulated copies of the RTL replace `always_ff` by `always` and `INIT_SYNC_FF` 0 by 1 (simulation initial values only). The real offset test is a plan (`docs/real_offset_plan.md`), not a result.
