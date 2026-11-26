## design.xdc: pins from the board's master XDC (kr260-pins.xdc); timing lines appended.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk }];  # clk_25
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# SFP+ MGTREFCLK0 156.25 MHz GT reference (clock B source)
create_clock -name clk_b_ref -period 6.400 [get_ports { gtref_p }]

# clk_mux (BUFGCTRL output) and the GT reference clock are asynchronous to clk: all crossings use xpm_cdc cells
set_clock_groups -asynchronous -group [get_clocks sys_clk_pin] -group [get_clocks clk_b_ref]

# LEDs and sfp_tx_disable are static indicators with no timing relation to the board
set_false_path -to [get_ports { led[*] sfp_tx_disable }]
