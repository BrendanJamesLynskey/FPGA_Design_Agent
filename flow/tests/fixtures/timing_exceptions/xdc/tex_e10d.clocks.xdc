create_clock -period 8.000 -name clk [get_ports clk]
create_generated_clock -name clk_slow -source [get_ports clk] -divide_by 8 [get_pins {div_reg[2]/Q}]
