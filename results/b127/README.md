# results/b127: the standard-protocol trading path inside the KR260 10G design (brief 127)

Records of build `designs/b96_kr260_10g/rm_gp_itch`: simulation (xsim with AMD's real XPM macros and the GT stand-in; Icarus with the real MACs) and the Vivado 2026.1 build. **No board was used.** Datasheet and method:
[designs/b96_kr260_10g/rm_gp_itch/docs/itch_integration.md](../../designs/b96_kr260_10g/rm_gp_itch/docs/itch_integration.md); the pre-registered board test: [preregistration.md](preregistration.md), [board_test_plan.md](../../designs/b96_kr260_10g/rm_gp_itch/docs/board_test_plan.md).

## Records
- `core_sim.json`, `core_lat_sim.json`, `xsim_ph*.log`: the whole core in xsim, four phases between the receive and transmit clocks, 8 single-candidate packets (one for each alignment of the message end in its 64-bit word) in each of two modes per phase.
  `core_sim.json` is the aggregate the stage file reads (tick-to-trade GT port to GT port, MAC word to the order's start strobe, PCS word to MAC word, `go` to the start strobe); `core_lat_sim.json` has every order's times; the logs are the testbench's monitor and register lines (the simulator's own
  noise filtered out). Made by `python3 -m designs.b96_kr260_10g.rm_gp_itch.tests.measure_xsim build/measure 0 1550 3100 4650`.
- `latency_sim.json`, `latency_unit_sim.json`: the new blocks with the real MACs (Icarus), the clocks from the MAC word with the message's last byte to the adapter's output word, to `go`, and to the order's start strobe, for all 8 byte positions, both modes.
- `verdict_lag_unit_sim.json`: the clocks from a frame's last word (and from the adapter's last payload word) to the late verdict strobe.
- `fcs_window_unit_sim.json`, `fcs_window_share.json`: how many bytes may follow a candidate message in a bad packet before its order escapes the late frame check, and the share of the synthetic generator's candidates beyond that.
- `back_to_back_unit_sim.json`: the spacing of the start strobes of two to four orders in a row.
- `builds/rm_gp_itch/`: the Vivado build (digest, run record, report_cdc summary, in-context timing of brief 110's critical paths).
- `preregistration.md`: the board test's arms, runs, criteria and stopping rules, written before any board time.

## Reproduce
`python3 -m pytest -q designs/b96_kr260_10g/rm_gp_itch/tests` (Icarus: the unit bench, about 2 minutes; xsim: the whole-core session and the stage dry runs, 10 to 40 minutes each, skipped without Vivado); the build: `results/b127/build_one.sh`.

## Known gaps and limits
Nothing here ran on a board: the test is pre-registered and the script written, not run. The transceiver is a stand-in in xsim, so no GT or optics are in any latency figure, and the clock phases are four fixed offsets, not a real frequency offset. The order frame is a stand-in with TCP checksum 0 until brief 119's `tcp_fast` lands (the hook is simulated). Every message and price is synthetic. The in-context timing selection for the price-ladder RAMs matched no cells in the first pass (`ctx_timing.txt`); `ctx_only.sh` re-runs it under a heavy slot. Full list: `designs/b96_kr260_10g/rm_gp_itch/docs/itch_integration.md`.
