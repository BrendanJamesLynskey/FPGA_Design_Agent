create_clock -period 10.000 -name clk_a [get_ports clk_a]
create_clock -period 3.000  -name clk_b [get_ports clk_b]
# the crossing is declared as XPM does: no timing relationship to the first stage (a false path to its D pin), nothing else
set_false_path -to [get_cells -hierarchical -filter {NAME =~ *a1_reg[*] || NAME =~ *p1_reg[*]}]
