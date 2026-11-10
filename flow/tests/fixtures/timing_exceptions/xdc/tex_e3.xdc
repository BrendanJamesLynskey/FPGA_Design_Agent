# fault: the registers load on every clock (no enable), so this multicycle is false
set_multicycle_path 2 -setup -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {p_reg[*]}]
set_multicycle_path 1 -hold -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {p_reg[*]}]
