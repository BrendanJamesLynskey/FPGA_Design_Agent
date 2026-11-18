# design.xdc: fcs_top on the Kria KR260 (xck26-sfvc784-2LV-c). Pins from designs/b96_kr260_10g/design.xdc (AMD board files).
# The oscillator is 25 MHz; the clock is constrained at 6.206 ns (161.13 MHz, the 10G datapath's rate) so that timing closure asks the
# real question of the CRC block. It is a timing study: the design is not run on a board at that rate (no board is used).
set_property -dict {PACKAGE_PIN C3 IOSTANDARD LVCMOS18} [get_ports clk_25]
create_clock -name clk_25 -period 6.206 [get_ports clk_25]
set_property -dict {PACKAGE_PIN F8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[1]}]
# the LEDs are slow indicators with no timing relationship (the same pattern as designs/b96_kr260_10g/design.xdc)
set_output_delay -clock clk_25 0.000 [get_ports {led[*]}]
set_false_path -to [get_ports {led[*]}]
