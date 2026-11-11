create_clock -period 10.000 -name rx_clk [get_ports rx_clk]
create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# rx_clk and sys_clk come from different oscillators (the IDELAY reference only uses sys_clk)
set_clock_groups -asynchronous -group [get_clocks rx_clk] -group [get_clocks -include_generated_clocks sys_clk]
# source-synchronous DDR, edge-aligned: data change with each rx_clk edge, skew 0.5 ns before and after
# (skew_bre = skew_are = skew_bfe = skew_afe = 0.5 ns); per edge: -max = skew_after = 0.5 ns; -min = -skew_before = -0.5 ns
set_input_delay -clock rx_clk -max 0.500 [get_ports {rx_d[*]}]
set_input_delay -clock rx_clk -min -0.500 [get_ports {rx_d[*]}]
set_input_delay -clock rx_clk -max 0.500 [get_ports {rx_d[*]}] -clock_fall -add_delay
set_input_delay -clock rx_clk -min -0.500 [get_ports {rx_d[*]}] -clock_fall -add_delay
# LED[0]: read by a person, no timing relationship
set_output_delay -clock rx_clk 0.000 [get_ports {LED[0]}]
set_false_path -to [get_ports {LED[0]}]
