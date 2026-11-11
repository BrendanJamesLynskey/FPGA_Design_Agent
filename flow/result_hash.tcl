# result_hash.tcl: dump the placed and routed result of the open design, for comparing two builds (brief 33).
#
#   source flow/result_hash.tcl; result_dump <file>
#
# One line per placed primitive cell ("C <cell> <LOC> <BEL>") and one per routed net ("N <net> <ROUTE>"). Only the
# top segment of each hierarchical net is written (its PARENT is itself): every other segment carries the same ROUTE, and on
# the 36k-LUT CDC rig writing all of them made a 10 GB file. Properties are read in chunks so that no Tcl list holds
# every route at once. flow/result_hash.py hashes the cell lines (placement) and the net lines (routing) separately
# and independently of their order. Used by flow/build.tcl when FDA_RESULT_HASH=1 and by
# results/33_vivado_speed/hash_dcp.tcl on saved checkpoints; it reads properties only and changes nothing.

proc result_dump {file} {
    set fh [open $file w]
    set cells [get_cells -hierarchical -quiet -filter {IS_PRIMITIVE && STATUS != UNPLACED}]
    for {set i 0} {$i < [llength $cells]} {incr i 5000} {
        set chunk [lrange $cells $i [expr {$i + 4999}]]
        foreach c $chunk loc [get_property LOC $chunk] bel [get_property BEL $chunk] {
            puts $fh "C $c $loc $bel"
        }
    }
    set nets [get_nets -hierarchical -quiet -filter {ROUTE_STATUS != NOLOADS}]
    for {set i 0} {$i < [llength $nets]} {incr i 2000} {
        set top {}
        foreach n [lrange $nets $i [expr {$i + 1999}]] p [get_property PARENT [lrange $nets $i [expr {$i + 1999}]]] {
            if {$n eq $p} { lappend top $n }
        }
        if {[llength $top]} {
            foreach n $top r [get_property ROUTE $top] { puts $fh "N $n $r" }
        }
    }
    close $fh
}
