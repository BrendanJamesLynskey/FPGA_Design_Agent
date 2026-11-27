## design.xdc: pins and I/O standards from the board's master XDC (kr260-pins.xdc); timing lines appended below.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk_c3 }];  # clk_c3
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk_c3 }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# SFP+ MGTREFCLK0 156.25 MHz differential reference (dedicated GT clock pins; the IBUFDS_GTE4 site follows the pair).
create_clock -name mgtrefclk0 -period 6.40 -waveform {0 3.2} [get_ports { mgtrefclk0_p }]

# The three clock groups are mutually asynchronous: clk_c3 (also clock A of the mux), the GT reference (clock B)
# and the muxed clock. Every crossing goes through an XPM CDC primitive.
set_clock_groups -asynchronous -group [get_clocks sys_clk_pin] -group [get_clocks mgtrefclk0]

# led[1:0] show ACTIVE_SEL and SWITCHING, sfp_tx_disable is a constant: slow outputs read by eye or by the SFP+ cage,
# so they are timed against clk_c3 with a loose output delay.
set_output_delay -clock [get_clocks sys_clk_pin] -max 5.0 [get_ports { led[*] sfp_tx_disable }]
set_output_delay -clock [get_clocks sys_clk_pin] -min 0.0 [get_ports { led[*] sfp_tx_disable }]
