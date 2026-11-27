## design.xdc: pins and I/O standards from the board's master XDC (kr260-pins.xdc); timing lines below.
## The MGTREFCLK0 differential pair (mgtrefclk0_p / mgtrefclk0_n) takes its package pins from the board's gt: section;
## board_constraints was not available to this stage, so its pin lines are to be added from that tool.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk }];  # clk (C3 25 MHz)
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# SFP+ MGTREFCLK0 is 156.25 MHz (clock B of the mux), asynchronous to clk (FDA-CON-5: clock definition)
create_clock -name gt_refclk_pin -period 6.40 -waveform {0 3.2} [get_ports { mgtrefclk0_p }];

# LEDs and sfp_tx_disable are slow indicator outputs observed by eye or tied constant: no capture clock, 0 ns output delay
# against the register clock keeps them constrained (FDA-CON-5)
set_output_delay -clock [get_clocks sys_clk_pin] 0.000 [get_ports { led[*] sfp_tx_disable }];

# The muxed-domain reset enters the xpm_cdc_async_rst synchroniser asynchronously (asserts asynchronously, release is
# synchronised to mux_clk); the register-to-PRE path from the clk domain is not a timed synchronous path (FDA-CON-5).
# No [*] bracket in the glob: brackets are character classes in the filter.
set_false_path -to [get_pins -hierarchical -filter {NAME =~ *u_dom/u_rst/arststages_ff_reg*/PRE}];
