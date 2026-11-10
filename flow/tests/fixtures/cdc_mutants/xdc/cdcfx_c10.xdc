# the FIFO's Gray pointers
set_max_delay -datapath_only -from [get_cells {wptr_reg[*]}] -to [get_cells {rq1_reg[*]}] 10.000
set_bus_skew -from [get_cells {wptr_reg[*]}] -to [get_cells {rq1_reg[*]}] 7.000
set_max_delay -datapath_only -from [get_cells {rptr_reg[*]}] -to [get_cells {wq1_reg[*]}] 10.000
set_bus_skew -from [get_cells {rptr_reg[*]}] -to [get_cells {wq1_reg[*]}] 10.000
