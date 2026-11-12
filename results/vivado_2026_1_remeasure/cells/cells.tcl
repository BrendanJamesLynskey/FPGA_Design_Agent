open_checkpoint [lindex $argv 0]
array set n {}
foreach c [get_cells -hierarchical *] {
    set t [get_property REF_NAME $c]
    if {![info exists n($t)]} { set n($t) 0 }
    incr n($t)
}
foreach t [lsort [array names n]] { puts [format "CELLS %-12s %6d" $t $n($t)] }
