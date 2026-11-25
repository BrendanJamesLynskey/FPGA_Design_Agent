## design.xdc: pins from the board's master XDC (kr260-pins.xdc); timing lines appended.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk_c3 }];  # clk_25
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk_c3 }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# 156.25 MHz SFP+ GT reference clock (pins are assigned by the GT site of the differential pair)
set_property PACKAGE_PIN Y6 [get_ports { mgtrefclk0_p }]
set_property PACKAGE_PIN Y5 [get_ports { mgtrefclk0_n }]
create_clock -name clk_ref_pin -period 6.40 [get_ports { mgtrefclk0_p }]

# JTAG TCK from the BSCANE2 in jtag_bus (data/jtag_bus.sv): up to 50 MHz, a primary clock on the primitive output.
create_clock -name jtag_tck -period 20.00 [get_pins u_jtag/u_bscan/INTERNAL_TCK]

# The three clocks are unrelated; every crossing goes through an XPM CDC primitive. Each crossing is bounded
# with a datapath-only max delay (one source period) instead of an unbounded clock group.
set C3_CLK  [get_clocks sys_clk_pin]
set REF_CLK [get_clocks clk_ref_pin]
set TCK_CLK [get_clocks jtag_tck]
set_max_delay -datapath_only -from $C3_CLK  -to $REF_CLK 6.40
set_max_delay -datapath_only -from $REF_CLK -to $C3_CLK  6.40
# The jtag_tck crossings are bounded by the scoped constraints of the xpm_cdc cells in jtag_bus.

# TDO of the BSCANE2 is clocked inside the configuration logic on the falling TCK edge; the tool cannot time that
# half-cycle path against the BUFG-delayed TCK, and it is static in practice at the JTAG rate.
set_false_path -to [get_pins u_jtag/u_bscan/TDO]

# USR_ACCESSE2 only reads a configuration register (static after load); its CFGCLK pin is unused.
create_clock -name usr_cfgclk -period 10.00 [get_pins u_core/u_usr/CCLK]
set_clock_groups -asynchronous -group [get_clocks usr_cfgclk] -group [get_clocks {sys_clk_pin clk_ref_pin jtag_tck}]

# Outputs: LEDs and the constant sfp_tx_disable are slow, human-visible or static; no timing relationship to a board
# device, so a zero output delay against the C3 clock only lets the checker see them as constrained.
set LED_PORTS [get_ports { led[*] sfp_tx_disable }]
set_output_delay -clock $C3_CLK 0.000 $LED_PORTS
