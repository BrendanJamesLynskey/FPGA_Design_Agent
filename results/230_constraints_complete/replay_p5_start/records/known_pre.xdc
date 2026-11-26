# Clock inputs the board file defines (flow/known_constraints.py, brief 230): the board clock, and the transceiver reference clock's pins and frequency.
# gt_refclk0_p/gt_refclk0_n: the transceiver reference clock pair of the board lane (board.yaml gt refclk p/n): placement
set_property PACKAGE_PIN Y6 [get_ports {gt_refclk0_p}]
set_property PACKAGE_PIN Y5 [get_ports {gt_refclk0_n}]
# Clocks of the primitives in this design that Vivado cannot derive (flow/known_constraints.py, brief 230).
# Read before design.xdc: a create_clock of your own on the same pin replaces these.
# BSCANE2 u_jtag/u_bscan: a create_clock on the TCK output (INTERNAL_TCK pin), at most 30 MHz on the JTAG cable; its crossings go through xpm_cdc macros, which carry their own constraints
create_clock -name jtag_tck -period 33.333 [get_pins u_jtag/u_bscan/INTERNAL_TCK]
# USR_ACCESSE2 u_usr: a clock on the CCLK pin (the primitive is a clocked cell with an internal clock); the DATA word is constant after configuration, so paths from it are cut with a reason
create_clock -name usr_cclk -period 10.000 [get_pins u_usr/CCLK]
# USR_ACCESS data is written at configuration and constant afterwards: paths from the configuration clock are not timed
set_false_path -from [get_clocks usr_cclk]
