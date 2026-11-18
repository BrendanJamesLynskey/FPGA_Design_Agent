# report_cdc on a routed variant, plus the path report of the crossing's order data bus and pulse (brief 97).
#   vivado -mode batch -source cdc_report.tcl -tclargs <post_route.dcp> <out prefix>
lassign $argv dcp pre
set_param general.maxThreads 1
open_checkpoint $dcp
report_cdc -details -file ${pre}_cdc.rpt
report_cdc -summary -file ${pre}_cdc_summary.rpt
report_clock_interaction -file ${pre}_clock_interaction.rpt
# the receive-to-transmit go pulse and the order bus: timing of paths into the first synchroniser flop of each, and from the decision logic into the pulse's source flop
foreach {tag pat} {pulse_sync *u_p_go/* bus_sync *u_bus/*} {
    set cells [get_cells -quiet -hierarchical -filter "IS_SEQUENTIAL && NAME =~ $pat"]
    set fo [open ${pre}_$tag.txt w]
    puts $fo "cells: [llength $cells]"
    foreach c $cells { puts $fo "$c [get_property REF_NAME $c] [get_property ASYNC_REG $c]" }
    close $fo
}
set src [get_cells -quiet -hierarchical -filter {IS_SEQUENTIAL && NAME =~ *u_p_go/src_*}]
if {[llength $src]} { report_timing -to $src -max_paths 1 -setup -file ${pre}_into_pulse_src.rpt }
close_design
