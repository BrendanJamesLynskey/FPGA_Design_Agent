# the Gray pointer: bound the crossing to one clk_b period
set_max_delay -datapath_only -from [get_cells {gray_reg[*]}] -to [get_cells {s1_reg[*]}] 7.000
# fault: clock groups beat every max delay, so the bound above is dropped
set_clock_groups -asynchronous -group [get_clocks clk_a] -group [get_clocks clk_b]
