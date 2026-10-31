# Gates test data

Snippets of real Vivado 2025.2 reports, cut by `flow/tests/cut_snippets.py` (header kept without the date, host and
command lines; long detail sections shortened):

- `good_*.rpt`: the first T1 base build (`designs/t1_dimmer_counter`, F0A, build stamp `7ff3ef48`; a later comment
  change gives the committed results a different stamp and slightly different numbers), where every gate passes.
- `bad_*.rpt`: `flow/tests/fixtures/bad_design`, a deliberately broken design built once so that the gates fail on
  real reports: negative setup and pulse-width slack, an unsynchronised clock crossing (CDC-1), inputs and an output
  without delays, no pin locations or I/O standards (NSTD-1, UCIO-1). Vivado then refuses `write_bitstream`, so
  there is no bitstream.
- `good_methodology_rtl.rpt`, `good_*_synth.rpt`, `good_timing_summary_place.rpt`, `good_qor_assessment_route.rpt`,
  `good_power_board_env.rpt` (04e): the per-stage reports of the 04e rebuild of the same T1 sources (build stamp
  `dfd4624e`, `results/ultrafast/`), where every UltraFast stage passes; `good_power_board_env.rpt` is that build's
  `report_power` for the board's thermal environment (still air, no heat sink, 40 C ambient), which the
  `power_junction_ok` gate needs. Cut with `cut_snippets.py <build dir> good <names...>`.
- `still_air_power.rpt`: a `b2_tmp_adt7420` power report for the same environment (04c; `test_hw_flow.py`).
