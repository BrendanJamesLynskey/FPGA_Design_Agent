create_clock -period 10.000 -name clk_a [get_ports clk_a]
create_clock -period 6.000  -name clk_b [get_ports clk_b]
# a bounded datapath only: no skew limit
set_max_delay -datapath_only -from [get_cells gray_reg[*]] -to [get_cells q1_reg[*]] 10.000
