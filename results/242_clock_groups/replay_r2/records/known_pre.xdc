# Clock inputs the board file defines (flow/known_constraints.py, brief 230): the board clock, and the transceiver reference clock's pins and frequency.
# gt_refclk_p/gt_refclk_n: the transceiver reference clock pair of the board lane (board.yaml gt refclk p/n): placement
set_property PACKAGE_PIN Y6 [get_ports {gt_refclk_p}]
set_property PACKAGE_PIN Y5 [get_ports {gt_refclk_n}]
# gt_refclk_p: reference clock 156.25 MHz (board.yaml gt refclk mhz)
create_clock -name gt_refclk -period 6.400 [get_ports {gt_refclk_p}]
# Clocks of the primitives in this design that Vivado cannot derive (flow/known_constraints.py, brief 230).
# Read before design.xdc: a create_clock of your own on the same pin replaces these.
# BSCANE2 u_jtag_bus/u_bscan: a create_clock on the TCK output (INTERNAL_TCK pin), at most 30 MHz on the JTAG cable; its crossings go through xpm_cdc macros, which carry their own constraints
create_clock -name jtag_tck -period 33.333 [get_pins u_jtag_bus/u_bscan/INTERNAL_TCK]
# USR_ACCESSE2 u_core/u_usr: a clock on the CCLK pin (the primitive is a clocked cell with an internal clock); the DATA word is constant after configuration, but whether paths from the clock need a cut depends on where DATA goes (an xpm_cdc macro already cuts them: a second false path is reported EXC-IGNORED, measured), so the crossing is the design's
create_clock -name usr_cclk -period 10.000 [get_pins u_core/u_usr/CCLK]
