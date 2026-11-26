// Waiver for the supplied read-only data/jtag_bus.sv: its tdo wire and cmd_s[45] (the read flag) are unused in simulation.
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*" -match "*'tdo'*"
lint_off -rule UNUSEDSIGNAL -file "*" -match "*'cmd_s'*"
`endif
