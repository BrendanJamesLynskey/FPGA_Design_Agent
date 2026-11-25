`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*tdo*"
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*cmd_s*"
`endif
