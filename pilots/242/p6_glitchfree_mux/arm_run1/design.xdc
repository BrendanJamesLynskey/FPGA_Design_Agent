## design.xdc: pins and I/O standards are the board's (kr260-pins.xdc); timing lines are appended below.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk }];  # clk (C3 25 MHz)
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

## SFP+ MGTREFCLK0 156.25 MHz reference (6.4 ns); the MGT reference pins are dedicated and are taken from the board file when it provides them.
create_clock -add -name gt_refclk -period 6.40 -waveform {0 3.2} [get_ports { gt_refclk_p }];

## The LEDs and sfp_tx_disable are slow status outputs read by eye or held static: loose output delay against clk.
set STATUS_OUT [get_ports { led[*] sfp_tx_disable }]
set_output_delay -clock [get_clocks sys_clk_pin] -max 5.0 $STATUS_OUT
set_output_delay -clock [get_clocks sys_clk_pin] -min 0.0 $STATUS_OUT

## Muxed-domain reset: the clk register arst asserts the xpm_cdc_async_rst chain asynchronously (PRE pins) and the
## release is synchronised in clk_mux by the chain itself, so the assertion path from clk has no timing relation.
## clk and clk_mux are one clock to the timer (clk_mux is clk through the BUFGCTRL), which gives this path a 0 ns requirement.
set RSTMUX_PRE [get_pins -hierarchical -filter {NAME =~ *u_chk/u_rst/arststages_ff_reg*/PRE}]
set_false_path -to $RSTMUX_PRE
