// Waiver for unused signals in the supplied read-only jtag bus file.
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*" -match "*'tdo'*"
lint_off -rule UNUSEDSIGNAL -file "*" -match "*'cmd_s'*"
`verilog
`endif
