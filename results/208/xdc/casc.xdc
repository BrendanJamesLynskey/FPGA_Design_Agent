create_clock -name clkref -period 10.000 [get_ports clk_in]
set_false_path -from [get_ports sel*]
set_false_path -to [get_ports dout]
