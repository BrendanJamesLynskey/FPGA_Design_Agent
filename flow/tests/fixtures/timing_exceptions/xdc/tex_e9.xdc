# mode is quasi-static (software writes it rarely) and reaches clk_b through the 2-flop ASYNC_REG chain m1 -> m2
set_false_path -from [get_cells mode_reg] -to [get_cells m1_reg]
