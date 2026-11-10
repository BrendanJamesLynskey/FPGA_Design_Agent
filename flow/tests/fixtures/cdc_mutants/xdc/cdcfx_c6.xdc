# the hand-built Gray bus: the bits are launched together and must be captured within one source period
set_max_delay -datapath_only -from [get_cells {g_reg[*]}] -to [get_cells {s1_reg[*]}] 10.000
set_bus_skew -from [get_cells {g_reg[*]}] -to [get_cells {s1_reg[*]}] 7.000
