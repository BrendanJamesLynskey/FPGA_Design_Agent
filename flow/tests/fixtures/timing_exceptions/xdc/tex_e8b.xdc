# clk0 (100 MHz) -> clk1 (200 MHz) from one MMCM; acc loads only on every second clk1 edge (ph)
# fault: -start counts in launch-clock (clk0, 10 ns) periods, so this relaxes the path by a whole slow cycle
set_multicycle_path 2 -setup -start -from [get_cells {s_reg[*]}] -to [get_cells {acc_reg[*]}]
set_multicycle_path 1 -hold -start -from [get_cells {s_reg[*]}] -to [get_cells {acc_reg[*]}]
