# results/b96c (brief 96C, WIP)

- `ppm_sim_baseline*.json`: the pre-96C design (main 6909e43f) against a simulated partner at +-ppm (first run used one test for several points; the stress run is `B96_PPM_GAPS=12,14,16`). No failure found.
- `ppm_sim_ratematch.json`: the rate-matched design, 0, +-100, +-300 ppm, 400 frames each (separate tests per point): every frame received, every order fired, counters clean.
- `core_sim.json`: core bench (15 tests) on the rate-matched design, incl. the tick-to-trade table (13 to 14 clocks).
- `cdc_probe.*`, `cdcexp/`: report_cdc experiments. A LUTRAM or xpm_memory_sdpram block memory read across clocks gives CDC-1 Critical (38) with or without set_max_delay: the flow gate post_synth_cdc_no_critical fails. See the report.
- `txpi_probe.*`: TXPI_PPM is settable on the synthesised GTHE4_CHANNEL cell (default 1'b0 from the Wizard).
- `queue.sh`, `build_one.sh`: the four builds (not completed; see report).
