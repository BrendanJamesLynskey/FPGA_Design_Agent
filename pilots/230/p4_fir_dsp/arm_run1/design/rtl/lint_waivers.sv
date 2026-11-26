// Lint waivers for the supplied read-only data/jtag_bus.sv.
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*tdo*"
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*cmd_s*"
`verilog
`endif
