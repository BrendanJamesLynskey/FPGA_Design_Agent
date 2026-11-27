## design.xdc: pins and I/O standards from the board's master XDC (kr260-pins.xdc); timing lines appended below.
## gt_refclk, jtag_tck clocks and the asynchronous clock groups are written by the flow.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk_25mhz }];  # clk_25
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk_25mhz }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# LEDs and sfp_tx_disable are static outputs with no timing relationship to the clock: zero output delay plus a false path.
set_output_delay -clock sys_clk_pin 0.0 [get_ports { led[*] sfp_tx_disable }]
set_false_path -to [get_ports { led[*] sfp_tx_disable }]

# usr_cclk is the configuration clock of USR_ACCESSE2; the BUILD word it launches is static after configuration and is
# sampled in the 25 MHz bus domain: asynchronous, one direction only (no path exists the other way).
set_false_path -from [get_clocks usr_cclk] -to [get_clocks sys_clk_pin]
