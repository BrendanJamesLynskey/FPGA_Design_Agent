# False paths and 0 ns placeholder delays of ports with no timing relation to any clock (board slow_ports, or the spec's async: true).
# flow/known_constraints.py, brief 230. Read after design.xdc; a port the design's XDC already constrains is left alone.
# One command per kind: Vivado reports a false path whose every object carries no path (a constant output) as EXC-IGNORED, so the
# ports are listed together and one live port keeps the command in use.
# sfp_tx_disable: board.yaml slow_ports: user I/O with no timing relation to any clock
# led: board.yaml slow_ports: user I/O with no timing relation to any clock
set_output_delay -clock [get_clocks -of_objects [get_ports {clk_c3}]] 0.000 [get_ports {sfp_tx_disable led[*]}]
