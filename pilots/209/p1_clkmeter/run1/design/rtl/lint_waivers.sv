// Lint waivers for the supplied read-only jtag_bus (BSCANE2 TDO unused in sim, cmd bit 45 not decoded).
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*" -match "*'tdo'*"
lint_off -rule UNUSEDSIGNAL -file "*" -match "*'cmd_s'*"
`verilog
`endif
