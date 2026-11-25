create_clock -name clk -period 4.000 [get_ports clk]
set_input_delay -clock clk 0.500 [get_ports {en_in din}]
set_false_path -to [get_ports dout]
