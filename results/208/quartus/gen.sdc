create_clock -name clk0 -period 10.000 [get_ports clk0]
create_clock -name clk1 -period 13.333 [get_ports clk1]
derive_clock_uncertainty
set_input_delay -clock clk0 1.000 [get_ports sel_in]
set_false_path -to [get_ports {doutm dout0}]
# generated clocks on the clock control block's output, grouped (the Altera form of UG949's template)
set mo [get_pins -compatibility_mode {*u_clkctrl*|sd*|outclk}]
create_generated_clock -name clk0mux -source [get_ports clk0] -master_clock clk0 $mo
create_generated_clock -name clk1mux -source [get_ports clk1] -master_clock clk1 -add $mo
set_clock_groups -logically_exclusive -group [get_clocks clk0mux] -group [get_clocks clk1mux]
