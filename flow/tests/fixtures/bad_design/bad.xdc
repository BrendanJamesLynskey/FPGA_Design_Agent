## Deliberately incomplete constraints (see bad_top.sv)
create_clock -name clk_a -period 2.000 [get_ports clk_a]
create_clock -name clk_b -period 3.000 [get_ports clk_b]
set_false_path -from [get_ports in_fp]
set_input_delay  -clock clk_a 0.5 [get_ports {x[*] y[*]}]
set_output_delay -clock clk_a 0.5 [get_ports {p[*]}]
