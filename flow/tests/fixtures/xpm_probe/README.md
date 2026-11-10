# xpm_probe

Two clocks, one `xpm_cdc_single`, one `xpm_cdc_gray`. QR1 (2026-11-10) built it through `flow/run_vivado.sh` (stopped
after route, Vivado 2025.2, xc7a100tcsg324-1) to check whether AMD's scoped XPM constraints are applied in the
non-project flow. Before `flow/xpm_cdc.tcl`: `report_cdc` Exception None on both rows, clk_a -> clk_b setup WNS -1.364 ns
(5 failing endpoints). To repeat: copy `xpm_probe_top.sv` and `design.xdc` into `designs/qr_xpm_probe/{rtl,}`, add a
`build.yaml` (top xpm_probe_top, part xc7a100tcsg324-1, sources rtl/*.sv, constraints design.xdc) and run
`FDA_STOP_AFTER=route flow/run_vivado.sh designs/qr_xpm_probe base`. Not run by pytest (needs Vivado).
