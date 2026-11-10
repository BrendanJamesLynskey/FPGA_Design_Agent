# clk0 (100 MHz) -> clk1 (200 MHz) from one MMCM; acc loads only on every second clk1 edge (ph): setup 2 -end, hold 1 -end
set_multicycle_path 2 -setup -end -from [get_cells {s_reg[*]}] -to [get_cells {acc_reg[*]}]
set_multicycle_path 1 -hold -end -from [get_cells {s_reg[*]}] -to [get_cells {acc_reg[*]}]
