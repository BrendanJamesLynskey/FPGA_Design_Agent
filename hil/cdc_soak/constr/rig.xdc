# rig.xdc: pins and primary clocks of the CDC soak rig on the Nexys A7-100T.
# Pins from boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc (Digilent, MIT).
# The crossing exceptions, pblocks and waivers are per copy and live in tcl/rig_cdc.tcl (sourced after synthesis).

set_property -dict { PACKAGE_PIN E3  IOSTANDARD LVCMOS33 } [get_ports CLK100MHZ]
set_property -dict { PACKAGE_PIN D4  IOSTANDARD LVCMOS33 } [get_ports UART_RXD_OUT]
set_property -dict { PACKAGE_PIN H17 IOSTANDARD LVCMOS33 } [get_ports {LED[0]}]
set_property -dict { PACKAGE_PIN K15 IOSTANDARD LVCMOS33 } [get_ports {LED[1]}]
set_property -dict { PACKAGE_PIN J13 IOSTANDARD LVCMOS33 } [get_ports {LED[2]}]
set_property -dict { PACKAGE_PIN N14 IOSTANDARD LVCMOS33 } [get_ports {LED[3]}]

# clk_a: the board oscillator. clk_c (CLKOUT0) and clk_f (CLKOUT1) are derived from the MMCM automatically.
create_clock -name clk_a -period 10.000 [get_ports CLK100MHZ]
# clk_b: CFGMCLK, typical 65 MHz, tolerance +-50 % (DS181): constrained at the fastest case, 97.5 MHz.
create_clock -name clk_b -period 10.260 [get_pins u_startup/CFGMCLK]

# The UART and LEDs are static or slow; no I/O timing is needed.
set_false_path -to [get_ports UART_RXD_OUT]
set_false_path -to [get_ports {LED[*]}]

set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
