# The clock of the out-of-context cost runs (brief 194). flow/assurance_ooc.tcl creates the same clock itself, with the period it is given
# (default 5.0 ns); this file states the default so the handover can cite it. No pins: the design is only built out of context.
create_clock -period 5.000 -name aclk [get_ports aclk]
