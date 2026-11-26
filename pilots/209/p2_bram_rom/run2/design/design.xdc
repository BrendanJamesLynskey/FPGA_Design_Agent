## design.xdc: pins from the board's master XDC; timing lines appended below.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk }];  # clk
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# JTAG TCK from the BSCANE2 primitive in jtag_bus: no port, so define it on the primitive output (10 MHz max).
create_clock -name jtag_tck -period 100.00 [get_pins u_bus/u_bscan/INTERNAL_TCK]

# USR_ACCESSE2 configuration clock pin (no port, slow, static USR_ACCESS value); BUILD is read quasi-statically.
create_clock -name cfg_cclk -period 100.00 [get_pins u_core/u_usr/CCLK]

# TCK, CCLK and the board clock are unrelated; the TCK crossings are covered by the xpm_cdc primitives' own
# false-path constraints, the static USR_ACCESS value is read by the host long after configuration.
set_false_path -from [get_clocks cfg_cclk]

# LEDs and the constant SFP disable are static, human-visible outputs: zero output delay, no timing to check.
set slow_out [get_ports {led[*] sfp_tx_disable}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
