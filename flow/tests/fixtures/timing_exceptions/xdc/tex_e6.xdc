# a, b and p load only when en is 1, on every second clock (fault: p_rgx is a typo for p_reg)
set_multicycle_path 2 -setup -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {p_rgx[*]}]
set_multicycle_path 1 -hold -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {p_rgx[*]}]
