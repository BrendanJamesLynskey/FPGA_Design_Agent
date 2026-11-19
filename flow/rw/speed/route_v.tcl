# route_v.tcl: Vivado's router on a placed checkpoint, the rival of RWRoute (brief 100B). B100_IN_DCP, B100_OUT (prefix), B100_PERIOD (record only).
# The whole job's wall time is measured by meas.sh (it includes opening the checkpoint); the router's own lap is in <out>_run.json.
source [file join [file dirname [info script]] ../common.tcl]
b100_threads
set out $::env(B100_OUT)
set times [dict create]
set t0 [clock milliseconds]
open_checkpoint $::env(B100_IN_DCP)
lap open
route_design
lap route
write_checkpoint -force ${out}_routed.dcp
lap write
set rs [report_route_status -return_string]
set f [open ${out}_route_status.txt w]; puts $f $rs; close $f
report_timing -setup -max_paths 3 -file ${out}_timing.rpt
write_run_json $out $times [get_property PART [current_design]] [env_or B100_PERIOD 0]
