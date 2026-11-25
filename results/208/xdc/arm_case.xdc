# set_case_analysis on the select register output: only one mode is timed
set_case_analysis 0 [get_pins -of_objects [get_cells -hier -filter {NAME =~ *sel_r_reg}] -filter {REF_PIN_NAME == Q}]
