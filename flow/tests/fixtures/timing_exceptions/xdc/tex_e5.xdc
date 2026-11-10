# fault: an 8-bit binary counter crosses bit by bit; a false path removes the only bound on the bus
set_false_path -from [get_clocks clk_a] -to [get_clocks clk_b]
