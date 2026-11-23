# design.xdc: b196_top on the Kria KR260 (xck26-sfvc784-2LV-c). Pins from boards/kr260/kr260-pins.xdc (AMD board files, see boards/kr260/board.yaml):
# the 25 MHz clock on HPA_CLK0P (frequency unconfirmed on the board) and the two user LEDs, all LVCMOS18.
set_property -dict {PACKAGE_PIN C3 IOSTANDARD LVCMOS18} [get_ports clk_25]
create_clock -name clk_25 -period 40.000 [get_ports clk_25]
set_property -dict {PACKAGE_PIN F8 IOSTANDARD LVCMOS18} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E8 IOSTANDARD LVCMOS18} [get_ports {led[1]}]
# the LEDs are slow outputs: no timing relation to the clock is meant
set_false_path -to [get_ports {led[*]}]
