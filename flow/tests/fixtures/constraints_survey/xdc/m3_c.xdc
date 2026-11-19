create_clock -period 10.000 -name clk_a [get_ports clk_a]
create_clock -period 6.000  -name clk_b [get_ports clk_b]
# bounded datapath plus a bus-skew limit, as xpm_cdc_gray's own constraints do (min of the two periods)
set_max_delay -datapath_only -from [get_cells gray_reg[*]] -to [get_cells q1_reg[*]] 10.000
set_bus_skew -from [get_cells gray_reg[*]] -to [get_cells q1_reg[*]] 6.000
