// Lint waivers for the supplied read-only jtag_bus: unused tdo and cmd_s[45] in simulation.
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*/data/jtag_bus.sv"
lint_off -rule UNUSEDSIGNAL -file "*/jtag_bus.sv" -match "*"
`endif
