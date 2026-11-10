# a, b and p load only when en is 1, and en is 1 on every second clock: the multiply has two clocks (setup 2, hold 1)
set_multicycle_path 2 -setup -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {p_reg[*]}]
set_multicycle_path 1 -hold -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {p_reg[*]}]
