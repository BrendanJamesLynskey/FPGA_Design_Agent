# fault: clk0 and clk1 come from one MMCM (synchronous); a false path between them hides a real path
set_false_path -from [get_clocks -of_objects [get_pins mmcm/CLKOUT0]] -to [get_clocks -of_objects [get_pins mmcm/CLKOUT1]]
