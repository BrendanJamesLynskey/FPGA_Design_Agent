// Lint waivers for the supplied read-only jtag bus: unused JTAG TDO and a spare command bit.
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*/jtag_bus.sv" -match "*tdo*"
lint_off -rule UNUSEDSIGNAL -file "*/jtag_bus.sv" -match "*cmd_s*"
`verilog
`endif
