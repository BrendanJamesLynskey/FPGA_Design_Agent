# referee.tcl: Vivado's verdict on a checkpoint (brief 100). Vivado's timing analysis is the referee; nothing else is used to claim closure.
#   B100_IN_DCP, B100_OUT (prefix), B100_ROUTE (1: run route_design first, which completes or repairs the routing and checks it),
#   B100_PERIOD (only for a design with no clock), B100_BITSTREAM (1: write_bitstream to <out>.bit)
source [file join [file dirname [info script]] common.tcl]
b100_threads
set out [env_or B100_OUT referee]
set times [dict create]
set t0 [clock milliseconds]
open_checkpoint $::env(B100_IN_DCP)
set_property SEVERITY {Warning} [get_drc_checks {NSTD-1 UCIO-1}]
if {[env_or B100_ROUTE 0] eq "1"} {
    route_design
    lap route
}
report_route_status -file ${out}_route_status.rpt
report_timing -setup -max_paths 10 -nworst 1 -file ${out}_timing.rpt
report_timing -hold -max_paths 3 -file ${out}_hold.rpt
report_drc -file ${out}_drc.rpt
report_utilization -file ${out}_util.rpt
write_run_json $out $times [get_property PART [current_design]] [get_property PERIOD [lindex [get_clocks] 0]]
if {[llength [get_cells -quiet u_gt]]} { chain_metrics $out }
if {[env_or B100_BITSTREAM 0] eq "1"} {
    write_bitstream -force ${out}.bit
    lap bitstream
    set f [open ${out}_bitstream.txt w]; puts $f "bitstream [file size ${out}.bit] bytes"; close $f
}
