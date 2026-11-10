# Slow FSM: en is 1 on one clock in 8. Setup 8, hold 7.
# fault: all_registers reaches the fast datapath (y, div, en) too
set_multicycle_path 8 -setup -from [all_registers] -to [all_registers]
set_multicycle_path 7 -hold -from [all_registers] -to [all_registers]
