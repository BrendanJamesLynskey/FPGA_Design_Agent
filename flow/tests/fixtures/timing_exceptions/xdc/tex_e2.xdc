# a, b and p load only when en is 1, on every second clock (fault: no -hold 1 to bring the hold check back)
set_multicycle_path 2 -setup -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {p_reg[*]}]
