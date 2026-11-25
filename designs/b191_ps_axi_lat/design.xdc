# design.xdc (brief 191, build ps_axi_lat): the PS provides pl_clk0 (its clock constraint comes with the PS IP); the one placeholder output port has no timing requirement.
set_false_path -to [get_ports unused_o]
# the PS clock pin (the pin name is the IP wrapper's output port; unverified: the image was not built)
create_clock -name pl_clk0 -period 10.000 [get_pins u_ps/pl_clk0]
