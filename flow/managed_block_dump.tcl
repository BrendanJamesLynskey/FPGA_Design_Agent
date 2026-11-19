# managed_block_dump.tcl: read a written checkpoint again and dump what a locked placed-and-routed block and the logic around it look like
# (brief 102, stage 2): a check of the saved file, not of Vivado's memory. Lines:
#   BLOCK|cell|site|bel|loc_fixed     ROUTE|net|route_fixed|route string (the nets inside the block that arrive routed)     OTHER|cell|site
# Environment: FDA_PR_DCP, FDA_PR_CELL (the block's instance), FDA_PR_OUT (the text file), FDA_PR_NETS (a file of the net names to dump:
# the <tag>_routes_before.txt of the run, so the same nets are read).
open_checkpoint $::env(FDA_PR_DCP)
set cell $::env(FDA_PR_CELL)
set f [open $::env(FDA_PR_OUT) w]
foreach c [lsort [get_cells -hier -filter "IS_PRIMITIVE && NAME =~ $cell/*"]] {
    puts $f "BLOCK|[get_property NAME $c]|[get_property SITE $c]|[get_property BEL $c]|[get_property IS_LOC_FIXED $c]"
}
set nf [open $::env(FDA_PR_NETS) r]
while {[gets $nf line] >= 0} {
    set name [lindex [split $line |] 0]
    set net [get_nets -quiet $name]
    if {$net eq ""} { puts $f "ROUTE|$name|missing|"; continue }
    puts $f "ROUTE|$name|[get_property IS_ROUTE_FIXED $net]|[get_property ROUTE $net]"
}
close $nf
foreach c [lsort [get_cells -hier -filter "IS_PRIMITIVE && NAME !~ $cell/*"]] {
    set s [get_property SITE $c]
    if {$s ne ""} { puts $f "OTHER|[get_property NAME $c]|$s" }
}
close $f
close_design
