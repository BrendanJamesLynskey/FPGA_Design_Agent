## design.xdc: pins from the board's master XDC (kr260-pins.xdc); port clk25 is the spec's name.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk25 }];  # clk25
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk25 }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# The JTAG TCK from BSCANE2 clocks the TCK side of jtag_bus; it has no timing arc from an input, so it is a
# primary clock (hw_server's default JTAG clock is 15 MHz; 66.667 ns is used because the TDO path is a half-period path
# and the BUFG insertion delay on TCK, about 11 ns, would fail it at 20 ns).
create_clock -name jtag_tck -period 66.667 [get_pins u_jtag/u_bscan/INTERNAL_TCK]

# The USR_ACCESSE2 configuration clock is unused (only DATA is read, a static value after configuration);
# it is declared at its 100 MHz maximum so its pin is not an unclocked endpoint.
create_clock -name usr_cclk -period 10.000 [get_pins u_core/u_usr/CCLK]

# usr_cclk is unused; USR_ACCESSE2 DATA is a static value after configuration read through no timed logic.
set_clock_groups -asynchronous -group [get_clocks usr_cclk] -group [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]]

# No clock group for TCK: TCK and clk cross only through xpm_cdc synchronisers, which carry their own
# set_max_delay -datapath_only; a clock group would override and mask those.

# led and sfp_tx_disable are static indicators to the board with no timing relation to a capture clock;
# the outputs are constrained loosely against the 100 MHz clk so they are not unconstrained endpoints.
set_output_delay -clock [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] 0.0 [get_ports {led[0] led[1] sfp_tx_disable}]
