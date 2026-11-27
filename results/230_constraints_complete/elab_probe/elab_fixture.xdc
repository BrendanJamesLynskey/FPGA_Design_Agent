create_clock -name clk_in -period 10.000 [get_ports clk_in]
set_input_delay -clock [get_clocks clk_in] 1.000 [get_ports din_ok]
set_output_delay -clock [get_clocks clk_in] 1.000 [get_ports dout_ok]
set_false_path -to [get_ports dout_fp]
