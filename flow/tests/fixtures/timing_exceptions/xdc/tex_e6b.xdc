# fault: a and b do not drive en, so these exceptions cover no path at all (and p is left single-cycle)
set_multicycle_path 2 -setup -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells en_reg]
set_multicycle_path 1 -hold -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells en_reg]
