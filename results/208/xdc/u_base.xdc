# Topology U (unrelated): two primary clocks on two ports.
create_clock -name clk0 -period 10.000 [get_ports clk0_p]
create_clock -name clk1 -period 13.333 [get_ports clk1_p]
set_input_delay -clock clk0 1.000 [get_ports sel_in]
set_false_path -to [get_ports {dout0 dout1 doutm}]
