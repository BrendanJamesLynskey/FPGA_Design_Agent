# results/b96c: frequency offset and rate matching on the 10G link (brief 96C)

This folder holds the simulation records, the report_cdc and TXPI probes, and the four Vivado builds of brief 96C, which adds a rate-matching elastic buffer (`designs/b96_kr260_10g/rtl/rate_match.sv`) and TX phase-interpolator ppm controls to the KR260 10GBASE-R design and to its latency variant `lat_all3`. No board result yet: the board session is pending.

## Records
- `ppm_sim_baseline.json`, `ppm_sim_baseline_stress.json`: the pre-96C design (main 6909e43f) against a simulated partner at +-ppm (the stress run is `B96_PPM_GAPS=12,14,16`). No failure found: the old design crosses events, not a stream.
- `ppm_sim_ratematch.json`: the rate-matched design, 0, +-100, +-300 ppm, 400 frames each (separate tests per point): every frame received, every order fired, counters clean.
- `core_sim.json`: the core bench (15 tests) on the rate-matched design, including the tick-to-trade table (12 to 13 clocks in simulation, in-phase clocks).
- `cdc_probe.*`, `cdcexp/`: the report_cdc experiments on the first (block memory) design: CDC-1 Critical (38) with or without `set_max_delay`, which led to the `xpm_fifo_async` redesign. `tim7.*`, `tim7_probe.tcl`: the TIMING-7 finding through the FIFO memory that `flow/xpm_cdc.tcl` now handles.
- `txpi_probe.*`: TXPI_PPM is settable on the synthesised GTHE4_CHANNEL cell (default 1'b0 from the Wizard).
- `builds/<name>/`: `digest.json` (timing, utilisation, power, gates), `run.json` (memory and wall time), `wall.txt` for control, all3, ppm_ctl and ppm_all3; `builds/gates.md` is the table generated from them by `gen_gates.py`. Bitstreams and the full Vivado logs are local and git-ignored (`designs/b96_kr260_10g/build/base`, `*/build/base`). `builds_pre_tcl/` holds the records of the earlier attempt before the FIFO-memory exception.
- `queue.sh`, `build_one.sh`, `queue.log`: the heavy-slot Vivado queue and its log.

## Measured
All four builds (git f47986f4, Vivado 2026.1, 6 GiB scope, 1 thread) pass all 29 gates with methodology critical warnings 0. Setup slack in ns: control 0.293, all3 0.004, ppm_ctl 0.135, ppm_all3 0.033; hold slack 0.010 to 0.011. Power: 0.928, 0.947, 1.102 and 0.930 W; junction 46.9 to 48.2 C. The all3 builds hit the scope's memory cap about 1000 times and used about 700 MiB of swap.

## Reproduce
`python3 -m pytest designs/b96_kr260_10g/tests` (simulation, Icarus and cocotb); `bash results/b96c/queue.sh` re-runs the four builds through the heavy-slot script (about 25 minutes each, `take_heavy_slot.sh` first); `python3 results/b96c/gen_gates.py` regenerates `builds/gates.md`.

## Known gaps and limits
No board result: whether TXPIPPM gives a relative offset at all (TXUSRCLK2 may follow the shifted rate), the achieved ppm, the echo and loop numbers with rate matching and the latency at the extremes are pending. The simulated latency is for in-phase clocks; the buffer adds up to about 5 more clocks at a positive ppm. The all3 setup slack of 0.004 ns is thin. The Icarus stand-in for `xpm_fifo_async` was not checked against the real macro.
