# false paths between the two SOURCE clocks (instead of clock groups): the review's case, to read how
# report_clock_interaction names it
set_false_path -from [get_clocks clk0] -to [get_clocks clk1]
set_false_path -from [get_clocks clk1] -to [get_clocks clk0]
