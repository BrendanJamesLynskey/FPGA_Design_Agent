# Topology R (related): one 100 MHz reference into an MMCM; clk0 (CLKOUT0, 100 MHz) and clk1 (CLKOUT1, 150 MHz) are auto-derived.
create_clock -name clkref -period 10.000 [get_ports clk0_p]
set_input_delay -clock clkref 1.000 [get_ports {sel_in clk1_p}]
set_false_path -to [get_ports {dout0 dout1 doutm}]
# rename the auto-derived MMCM output clocks (UG903 "Renaming Auto-Derived Clocks"), so arms can name them
create_generated_clock -name clk0 [get_pins -hier -filter {NAME =~ *u_mmcm/CLKOUT0}]
create_generated_clock -name clk1 [get_pins -hier -filter {NAME =~ *u_mmcm/CLKOUT1}]
