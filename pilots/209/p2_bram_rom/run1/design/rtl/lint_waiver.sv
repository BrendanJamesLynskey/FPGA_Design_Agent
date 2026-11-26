// Lint waiver for the supplied, read-only data/jtag_bus.sv: its tdo (used only by BSCANE2 in synthesis)
// and cmd_s[45] (the read flag, not needed on the core side) are unused in lint.
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*tdo*"
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*cmd_s*"
`verilog
`endif
