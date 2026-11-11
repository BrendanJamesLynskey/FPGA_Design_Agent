create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# SW: switches set by hand, asynchronous; they enter the two-flop synchroniser sw_a/sw_b (ASYNC_REG): a 0 ns
# placeholder delay and a false path
set_input_delay -clock sys_clk 0.000 [get_ports {SW[*]}]
set_false_path -from [get_ports {SW[*]}]
# LED: read by a person, no timing relationship
set_output_delay -clock sys_clk 0.000 [get_ports {LED[*]}]
set_false_path -to [get_ports {LED[*]}]
