# Slow FSM (st, gain, k) and gain_q tagged fda_slow_en; en is 1 on one clock in 8. Setup 8, hold 7.
# fault: gain_q copies gain on every clock, so the path gain -> gain_q is not an 8-clock path
set slow [get_cells -hier -filter {fda_slow_en == true}]
set_multicycle_path 8 -setup -from $slow -to $slow
set_multicycle_path 7 -hold -from $slow -to $slow
