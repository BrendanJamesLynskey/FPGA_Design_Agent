# Gates test data

Snippets of real Vivado 2025.2 reports, cut by `flow/tests/cut_snippets.py` (header kept without the date, host and
command lines; long detail sections shortened):

- `good_*.rpt`: the T1 base build (`designs/t1_dimmer_counter`, F0A), where every gate passes.
- `bad_*.rpt`: `flow/tests/fixtures/bad_design`, a deliberately broken design built once so that the gates fail on
  real reports: negative setup and pulse-width slack, an unsynchronised clock crossing (CDC-1), inputs and an output
  without delays, no pin locations or I/O standards (NSTD-1, UCIO-1). Vivado then refuses `write_bitstream`, so
  there is no bitstream.
