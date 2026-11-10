# the 4-phase handshake holds data stable while req/ack cross
set_max_delay -datapath_only -from [get_cells {data_reg[*]}] -to [get_cells {dout_reg[*]}] 10.000
