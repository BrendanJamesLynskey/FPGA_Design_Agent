# Brief 206: one clock per arm, deliberately tight (2 ns) so the Timing Analyzer reports each arm's Fmax.
foreach c {clk1 clk2 clk3 clk4 clk5 clk6 clk7 clk8 clk9 clk10} { create_clock -name $c -period 2.0 [get_ports $c] }
set_clock_groups -asynchronous -group clk1 -group clk2 -group clk3 -group clk4 -group clk5 -group clk6 -group clk7 -group clk8 -group clk9 -group clk10
