// Lint waivers for the supplied, read-only data/jtag_bus.sv: tdo is the BSCANE2 output kept for the
// primitive; cmd_s[45] is the read flag the core does not need (a command that is not a write is a read).
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*"
`verilog
`endif
