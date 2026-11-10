# Slow FSM (st, gain, k) and its consumer gain_q load only when en is 1; en is 1 on one clock in 8 (div counts 0..7).
# Paths between two of them have 8 clocks: setup 8, hold 7. Consumer: gain_q samples gain only on en (qualified).
set slow [get_cells -hier -filter {fda_slow_en == true}]
set_multicycle_path 8 -setup -from $slow -to $slow
set_multicycle_path 7 -hold -from $slow -to $slow
