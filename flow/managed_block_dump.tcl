# managed_block_dump.tcl: read a written checkpoint again and dump what a locked placed-and-routed block and the logic around it look like
# (brief 102, stage 2): a check of the saved file, not of Vivado's memory. Lines:
#   NL|cell|ref|config properties|pin=net,...   (the block's logical netlist, no placement: its fingerprint must not change when the block moves)
#   NETD|net_to_pin|slow_max_ps|fast_max_ps|estimated   (get_net_delays: the interconnect delay to every pin of a block net; clock-independent)
#   BLOCK|cell|site|bel|loc_fixed     ROUTE|net|route_fixed|route string (the nets inside the block that arrive routed)     OTHER|cell|site
# Environment: FDA_PR_DCP, FDA_PR_CELL (the block's instance), FDA_PR_OUT (the text file), FDA_PR_NETS (a file of the net names to dump:
# the <tag>_routes_before.txt of the run, so the same nets are read).
set_param tcl.collectionResultDisplayLimit 0
open_checkpoint $::env(FDA_PR_DCP)
set cell $::env(FDA_PR_CELL)
set f [open $::env(FDA_PR_OUT) w]
foreach c [lsort [get_cells -hier -filter "IS_PRIMITIVE && NAME =~ $cell/*"]] {
    puts $f "BLOCK|[get_property NAME $c]|[get_property SITE $c]|[get_property BEL $c]|[get_property IS_LOC_FIXED $c]"
}
set cfg_re {^(INIT.*|IS_[A-Z0-9_]*_INVERTED|SRVAL.*|CARRY_TYPE|CE_TYPE|SR_TYPE|CLOCK_DOMAINS|DATA_WIDTH.*)$}
foreach c [lsort [get_cells -hier -filter "IS_PRIMITIVE && NAME =~ $cell/*"]] {
    set props {}
    foreach pr [lsort [list_property $c]] { if {[regexp $cfg_re $pr]} { lappend props "$pr=[get_property $pr $c]" } }
    set pins {}
    foreach pn [lsort [get_pins -quiet -of_objects $c]] {
        set net [get_nets -quiet -of_objects $pn]
        lappend pins "[get_property REF_PIN_NAME $pn]=[expr {$net eq "" ? "-" : [get_property NAME $net]}]"
    }
    puts $f "NL|[get_property NAME $c]|[get_property REF_NAME $c]|[join $props ,]|[join $pins ,]"
}
set nf [open $::env(FDA_PR_NETS) r]
while {[gets $nf line] >= 0} {
    set name [lindex [split $line |] 0]
    set net [get_nets -quiet $name]
    if {$net eq ""} { puts $f "ROUTE|$name|missing|"; continue }
    foreach d [get_net_delays -quiet -of_objects $net] { puts $f "NETD|[get_property NAME $d]|[get_property SLOW_MAX $d]|[get_property FAST_MAX $d]|[get_property ESTIMATED $d]" }
    puts $f "ROUTE|$name|[get_property IS_ROUTE_FIXED $net]|[get_property ROUTE $net]"
}
close $nf
foreach c [lsort [get_cells -hier -filter "IS_PRIMITIVE && NAME !~ $cell/*"]] {
    set s [get_property SITE $c]
    if {$s ne ""} { puts $f "OTHER|[get_property NAME $c]|$s" }
}
close $f
close_design
