create_clock -period 2.700 -name clk [get_ports clk]
set_input_delay  -clock clk 0.5 [get_ports {go_in d_in[*]}]
set_output_delay -clock clk 0.5 [get_ports {q_out[*]}]
