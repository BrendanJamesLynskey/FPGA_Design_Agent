// Lint configuration for the supplied read-only jtag bus file:
// its tdo and cmd_s[45] are unused when BSCANE2 is not modelled in simulation.
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*'tdo'*"
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*'cmd_s'*"
`verilog
`endif
