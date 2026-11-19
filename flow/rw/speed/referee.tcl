# referee.tcl: Vivado's timing and route status of a finished checkpoint, no routing (brief 100B). B100_IN_DCP, B100_OUT, B100_PERIOD (for the record).
source [file join [file dirname [info script]] ../common.tcl]
b100_threads
set out $::env(B100_OUT)
open_checkpoint $::env(B100_IN_DCP)
set times [dict create]
set rs [report_route_status -return_string]
set f [open ${out}_route_status.txt w]; puts $f $rs; close $f
report_timing -setup -max_paths 3 -file ${out}_timing.rpt
write_run_json $out $times [get_property PART [current_design]] [env_or B100_PERIOD 0]
