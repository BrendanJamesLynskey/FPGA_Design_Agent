// Lint waiver for the supplied, read-only jtag_bus.sv (its BSCANE2 TDO and command bit 45 are unused in simulation).
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*/data/jtag_bus.sv" -match "*"
lint_off -rule UNUSEDSIGNAL -file "*/data/jtag_bus.sv"
`endif
