## design.xdc: pins and I/O standards from the board's master XDC (kr260-pins.xdc).
## The board clock resource clk_25 is the top port clk_c3.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk_c3 }];  # clk_25
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk_c3 }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# SFP+ MGTREFCLK0, 156.25 MHz (clock B source); GT pins are placed by the GT reference clock site.
create_clock -name gt_refclk -period 6.400 [get_ports { gt_refclk_p }];

# The board clock and the GT reference clock come from separate oscillators: every crossing uses an XPM CDC primitive.
set_clock_groups -asynchronous -group [get_clocks sys_clk_pin] -group [get_clocks gt_refclk]

# LEDs and SFP TX_DISABLE are slow human-facing or static outputs: no external timing relationship, constrain loosely.
set LED_PORTS [get_ports { led[*] sfp_tx_disable }]
set_output_delay -clock [get_clocks sys_clk_pin] -max 0.000 $LED_PORTS
set_output_delay -clock [get_clocks sys_clk_pin] -min 0.000 $LED_PORTS
