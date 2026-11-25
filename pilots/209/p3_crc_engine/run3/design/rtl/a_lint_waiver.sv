// Lint waiver for the supplied read-only data/jtag_bus.sv (tdo, cmd_s[45] unused by construction).
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*/jtag_bus.sv" -match "*tdo*"
lint_off -rule UNUSEDSIGNAL -file "*/jtag_bus.sv" -match "*cmd_s*"
`verilog
`endif
