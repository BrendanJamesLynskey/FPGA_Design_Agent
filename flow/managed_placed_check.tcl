# managed_placed_check.tcl: the facts the import check of a placed-and-routed component needs (brief 102, stage 2), read from the supplier's
# checkpoint: ports, how much of it is locked (placement and routing), routing status, and the sites it occupies. One line per fact:
#   PORT|name|dir|width   CELLS|leaf|loc_fixed|bel_fixed|unplaced   NETS|signal|routed|route_fixed|unrouted   SITE|type|count   RECT|x0|y0|x1|y1
# Environment: FDA_PR_DCP (the checkpoint), FDA_PR_OUT (the text file written), FDA_PR_FUNCSIM (optional: write the funcsim netlist there).
open_checkpoint $::env(FDA_PR_DCP)
set f [open $::env(FDA_PR_OUT) w]
puts $f "VIVADO|[version -short]"
puts $f "PART|[get_property PART [current_design]]"
puts $f "TOP|[get_property TOP [current_design]]"
set seen [dict create]
foreach p [get_ports] {
    set n [regsub {\[\d+\]$} [get_property NAME $p] {}]
    dict lappend seen $n [get_property DIRECTION $p]
}
dict for {n dirs} $seen { puts $f "PORT|$n|[string tolower [lindex $dirs 0]]|[llength $dirs]" }
# GND and VCC are constant sources with no site: not placeable, so not counted
set leaf [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME != GND && REF_NAME != VCC}]
puts $f "CELLS|[llength $leaf]|[llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME != GND && REF_NAME != VCC && IS_LOC_FIXED}]]|[llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME != GND && REF_NAME != VCC && IS_BEL_FIXED}]]|[llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME != GND && REF_NAME != VCC && STATUS == UNPLACED}]]"
set nets [get_nets -hier -filter {TYPE == SIGNAL}]
set routed 0; set fixed 0; set unrouted 0
foreach n $nets {
    set st [get_property ROUTE_STATUS $n]
    if {$st eq "ROUTED"} { incr routed } elseif {$st eq "UNROUTED"} { incr unrouted }
    if {[get_property IS_ROUTE_FIXED $n]} { incr fixed }
}
puts $f "NETS|[llength $nets]|$routed|$fixed|$unrouted"
set types [dict create]
set xs {}; set ys {}
foreach c $leaf {
    set s [get_sites -quiet [get_property SITE $c]]
    if {$s eq ""} { continue }
    dict incr types [get_property SITE_TYPE $s]
    if {[regexp {^SLICE_X(\d+)Y(\d+)$} [get_property NAME $s] -> x y]} { lappend xs $x; lappend ys $y }
}
dict for {t n} $types { puts $f "SITE|$t|$n" }
if {[llength $xs]} { puts $f "RECT|[tcl::mathfunc::min {*}$xs]|[tcl::mathfunc::min {*}$ys]|[tcl::mathfunc::max {*}$xs]|[tcl::mathfunc::max {*}$ys]" }
close $f
if {[info exists ::env(FDA_PR_FUNCSIM)] && $::env(FDA_PR_FUNCSIM) ne ""} { write_verilog -force -mode funcsim $::env(FDA_PR_FUNCSIM) }
close_design
