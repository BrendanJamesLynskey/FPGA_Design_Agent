# retime.tcl: re-state the clock period of a placed checkpoint (the placement stays), so one placement can be routed at several periods (brief 100B).
#   B100_IN_DCP, B100_OUT_DCP, B100_PERIOD
source [file join [file dirname [info script]] ../common.tcl]
b100_threads
open_checkpoint $::env(B100_IN_DCP)
create_clock -period $::env(B100_PERIOD) -name clk [get_ports clk]
write_checkpoint -force $::env(B100_OUT_DCP)
