create_clock -period 10.000 -name rx_clk [get_ports rx_clk]
# source-synchronous DDR, centre-aligned: the source's data sheet gives the data valid 2.0 ns before and 2.0 ns after
# each rx_clk edge (dv_bre = dv_are = dv_bfe = dv_afe = 2.0 ns); traces matched. Per edge (AMD's centre-aligned DDR
# template): -max = T/2 - dv_before = 5.0 - 2.0 = 3.0 ns; -min = dv_after = 2.0 ns
set_input_delay -clock rx_clk -max 3.000 [get_ports {rx_d[*]}]
set_input_delay -clock rx_clk -min 2.000 [get_ports {rx_d[*]}]
set_input_delay -clock rx_clk -max 3.000 [get_ports {rx_d[*]}] -clock_fall -add_delay
set_input_delay -clock rx_clk -min 2.000 [get_ports {rx_d[*]}] -clock_fall -add_delay
# LED[0]: read by a person, no timing relationship
set_output_delay -clock rx_clk 0.000 [get_ports {LED[0]}]
set_false_path -to [get_ports {LED[0]}]
