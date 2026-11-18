# phase2_probe.tcl (brief 97, phase 2 plan): which controls Vivado 2026.1 itself documents for manual placement, manual routing and
# per-block synthesis, read from the tool's own help and property tables (no design needed for the help; the properties are read from the
# 96 post-route checkpoint). Run: vivado -mode batch -source phase2_probe.tcl -tclargs <post_route.dcp> <out.txt>
lassign $argv dcp out
set fo [open $out w]
proc sect {t} { global fo; puts $fo "\n##### $t" }
foreach c {synth_design opt_design place_design phys_opt_design route_design} {
    sect "help $c"
    catch {puts $fo [help $c]} e
}
open_checkpoint $dcp
sect "version"
puts $fo [version -short]
foreach {cls pat} {cell {LOC BEL RLOC U_SET HU_SET H_SET KEEP DONT_TOUCH KEEP_HIERARCHY IS_BEL_FIXED IS_LOC_FIXED PBLOCK DIRECT_ENABLE}
                   net {FIXED_ROUTE ROUTE IS_ROUTE_FIXED IS_ROUTE_FIXED MARK_DEBUG DONT_TOUCH USER_CLOCK_ROOT CLOCK_DEDICATED_ROUTE}} {
    sect "properties of a $cls matching these names"
    set obj [expr {$cls eq "cell" ? [lindex [get_cells -hier -filter {IS_SEQUENTIAL}] 0] : [lindex [get_nets -hier -filter {TYPE==SIGNAL}] 0]}]
    set have [list_property $obj]
    foreach p $pat { puts $fo "$cls $p : [expr {[lsearch -exact $have $p] >= 0 ? {present} : {ABSENT}}]" }
}
sect "report_property of one routed net"
set n [get_nets -quiet -hier -filter {TYPE==SIGNAL && ROUTE_STATUS==ROUTED}]
catch {puts $fo [join [lrange [report_property -return_string [lindex $n 0]] 0 60] "\n"]} e
sect "clock regions and the GTH quad"
catch {puts $fo [get_property CLOCK_REGION [get_cells -hier -filter {REF_NAME==GTHE4_CHANNEL}]]} e
sect "directives"
catch {puts $fo "place_design -directive: [get_property ENUM_VALUES [get_param place.directive]]"} e
close_design
close $fo
