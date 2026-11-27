# False paths and 0 ns placeholder delays of ports with no timing relation to any clock (board slow_ports, or the spec's async: true).
# flow/known_constraints.py, brief 230. Read after design.xdc; a port the design's XDC already constrains is left alone.
# One command per kind: Vivado reports a false path whose every object carries no path (a constant output) as EXC-IGNORED, so the
# ports are listed together and one live port keeps the command in use.
# sfp_tx_disable: board.yaml slow_ports: user I/O with no timing relation to any clock
# led: board.yaml slow_ports: user I/O with no timing relation to any clock
set_output_delay -clock [get_clocks -of_objects [get_ports {clk_c3}]] 0.000 [get_ports {sfp_tx_disable led[*]}]
# Clock groups from the declared clock relations (architecture.yaml clock_relations, or spec.yaml; flow/known_constraints.py, brief 242).
# clk_wr / clk_rd: async: 25 MHz board clock and the 156.25 MHz transceiver reference clock have no common source (spec: 'asynchronous: clk_c3 and gt_refclk0') (bounded, not grouped: a crossing macro carries set_max_delay -datapath_only, which a clock group would override)
set_max_delay -datapath_only -from [get_clocks -of_objects [get_ports {clk_c3}]] -to [get_clocks -of_objects [get_ports {gt_refclk0_p}]] [expr {min([get_property PERIOD [get_clocks -of_objects [get_ports {clk_c3}]]], [get_property PERIOD [get_clocks -of_objects [get_ports {gt_refclk0_p}]]])}]
# clk_wr / jtag: async: JTAG TCK has no common source with the board clock; every crossing is an xpm_cdc macro in jtag_bus
set_clock_groups -asynchronous -name fda_async_clk_wr_jtag -group [get_clocks -of_objects [get_ports {clk_c3}]] -group [get_clocks jtag_tck]
# clk_wr / cfg: async: the configuration clock (USR_ACCESSE2 CCLK) has no common source with the board clock; crossed by xpm_cdc
set_clock_groups -asynchronous -name fda_async_clk_wr_cfg -group [get_clocks -of_objects [get_ports {clk_c3}]] -group [get_clocks usr_cclk]
