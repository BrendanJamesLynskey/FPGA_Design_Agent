# groups on the SOURCE clocks, -asynchronous (the wrong option for a mux)
set_clock_groups -name mux_src -asynchronous -group [get_clocks -of_objects [get_pins -of_objects [get_cells -hier -filter {NAME =~ *u_mux}] -filter {REF_PIN_NAME == I0}]] -group [get_clocks -of_objects [get_pins -of_objects [get_cells -hier -filter {NAME =~ *u_mux}] -filter {REF_PIN_NAME == I1}]]
