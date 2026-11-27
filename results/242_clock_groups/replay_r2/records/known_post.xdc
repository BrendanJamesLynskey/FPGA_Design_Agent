# False paths and 0 ns placeholder delays of ports with no timing relation to any clock (board slow_ports, or the spec's async: true).
# flow/known_constraints.py, brief 230. Read after design.xdc; a port the design's XDC already constrains is left alone.
# One command per kind: Vivado reports a false path whose every object carries no path (a constant output) as EXC-IGNORED, so the
# ports are listed together and one live port keeps the command in use.
# led: board.yaml slow_ports: user I/O with no timing relation to any clock
# sfp_tx_disable: board.yaml slow_ports: user I/O with no timing relation to any clock
set_output_delay -clock [get_clocks -of_objects [get_ports {clk_c3}]] 0.000 [get_ports {led[*] sfp_tx_disable}]
set_false_path -to [get_ports {led[*] sfp_tx_disable}]
# Clock groups from the declared clock relations (architecture.yaml clock_relations, or spec.yaml; flow/known_constraints.py, brief 242).
# clk_c3 / gt_refclk: async: a crossing clk_c3 -> gt_refclk through xpm_cdc_async_rst is declared in architecture.yaml (state clock_relations to say otherwise, e.g. related) (bounded, not grouped: a crossing macro carries set_max_delay -datapath_only, which a clock group would override)
set_max_delay -datapath_only -from [get_clocks -of_objects [get_ports {clk_c3}]] -to [get_clocks gt_refclk] [expr {min([get_property PERIOD [get_clocks -of_objects [get_ports {clk_c3}]]], [get_property PERIOD [get_clocks gt_refclk]])}]
set_max_delay -datapath_only -from [get_clocks gt_refclk] -to [get_clocks -of_objects [get_ports {clk_c3}]] [expr {min([get_property PERIOD [get_clocks -of_objects [get_ports {clk_c3}]]], [get_property PERIOD [get_clocks gt_refclk]])}]
