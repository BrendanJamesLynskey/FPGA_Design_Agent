## design.xdc: pins and I/O standards from the board's master XDC (kr260-pins.xdc); port clk is the 25 MHz clock.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk }];  # clk
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# JTAG TCK is generated inside the BSCANE2 primitive of jtag_bus, so the tool cannot derive it; define it on the primitive's internal clock pin (100 ns, a slow JTAG cable).
create_clock -name jtag_tck -period 100.00 -waveform {0 50} [get_pins {u_bus/u_bscan/INTERNAL_TCK}];
# The USR_ACCESSE2 configuration clock pin has no clock; define it at a conservative 10 ns (the read value is static after configuration).
create_clock -name cfg_clk -period 10.00 -waveform {0 5} [get_pins {u_core/u_usr/CCLK}];
# The config clock and clk are unrelated and the USR_ACCESS value is static: asynchronous groups. TCK/clk crossings are covered by the xpm_cdc macros' own constraints, so no group for them.
set_clock_groups -asynchronous -group [get_clocks sys_clk_pin] -group [get_clocks cfg_clk];

# LEDs and sfp_tx_disable are slow status outputs with no timing relation to any external device: loose output delay.
set_output_delay -clock sys_clk_pin -max 5.0 [get_ports { led[*] sfp_tx_disable }]
set_output_delay -clock sys_clk_pin -min 0.0 [get_ports { led[*] sfp_tx_disable }]
