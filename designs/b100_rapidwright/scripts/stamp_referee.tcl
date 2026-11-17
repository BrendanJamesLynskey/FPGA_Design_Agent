# stamp_referee.tcl: Vivado's verdict on a stamped design that RapidWright routed (brief 100, capability 1): route_design (a check that
# completes anything left; B100_ROUTE=0 skips it), route status, timing, and the block-internal paths of the four copies.
#   B100_IN_DCP, B100_OUT, B100_ROUTE (default 1)
source [file join [file dirname [info script]] ../../../flow/rw/common.tcl]
source [file join [file dirname [info script]] blocks.tcl]
b100_threads
set out $::env(B100_OUT)
set times [dict create]
set t0 [clock milliseconds]
open_checkpoint $::env(B100_IN_DCP)
set_property SEVERITY {Warning} [get_drc_checks {NSTD-1 UCIO-1}]
if {[env_or B100_ROUTE 1] eq "1"} { route_design; lap route }
report_route_status -file ${out}_route_status.rpt
write_run_json ${out}_ref $times [get_property PART [current_design]] [get_property PERIOD [lindex [get_clocks] 0]]
block_paths $out
report_timing -setup -max_paths 3 -file ${out}_timing.rpt
