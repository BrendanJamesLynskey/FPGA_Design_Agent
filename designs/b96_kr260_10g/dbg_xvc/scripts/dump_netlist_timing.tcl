# dump_netlist_timing.tcl (brief 131): what the debug logic changes, measured from a routed checkpoint. Run once on the parent build's post_route.dcp (eyescan) and once on dbg_xvc's:
#   vivado -mode batch -source dump_netlist_timing.tcl -tclargs <post_route.dcp> <out dir>
# Writes cells.txt (every leaf cell under u_core with its library cell), per_clock.txt (worst setup and hold slack per clock), paths.txt (worst setup and hold slack of paths that start or end inside
# the trading path's hierarchies u_rx and u_tx), hier_util.txt (primitive counts per u_core child), tap_fanout.txt (dbg_xvc only: the load pins on the three tapped nets).
set dcp [lindex $argv 0]
set out [lindex $argv 1]
file mkdir $out
open_checkpoint $dcp
set f [open $out/cells.txt w]
foreach c [lsort [get_cells -hier -filter {IS_PRIMITIVE && NAME =~ u_core/*}]] { puts $f "$c|[get_property REF_NAME $c]" }
close $f
set f [open $out/per_clock.txt w]
foreach c [lsort [get_clocks]] {
    set s [get_timing_paths -max_paths 1 -setup -to [get_clocks $c]]
    set h [get_timing_paths -max_paths 1 -hold -to [get_clocks $c]]
    puts $f "$c|setup|[expr {[llength $s] ? [get_property SLACK $s] : {na}}]|hold|[expr {[llength $h] ? [get_property SLACK $h] : {na}}]"
}
close $f
set f [open $out/paths.txt w]
foreach {label pat} {u_rx {u_core/g_old.u_rx/*} u_tx {u_core/g_old.u_tx/*}} {
    set cells [get_cells -hier -filter "IS_PRIMITIVE && NAME =~ $pat"]
    foreach {dir opt} {from -from to -to} {
        set p [get_timing_paths -max_paths 1 -setup $opt $cells]
        puts $f "$label|$dir|setup|[expr {[llength $p] ? [get_property SLACK $p] : {na}}]"
        set p [get_timing_paths -max_paths 1 -hold $opt $cells]
        puts $f "$label|$dir|hold|[expr {[llength $p] ? [get_property SLACK $p] : {na}}]"
    }
}
close $f
set f [open $out/hier_util.txt w]
set cnt [dict create]
foreach c [get_cells -hier -filter {IS_PRIMITIVE && NAME =~ u_core/*}] {
    set parts [split $c /]
    set k [lindex $parts 1]
    dict incr cnt $k
}
foreach k [lsort [dict keys $cnt]] { puts $f "$k|[dict get $cnt $k]" }
close $f
set f [open $out/tap_fanout.txt w]
# the three nets the debug taps read (dbg_xvc only; the parent has no such cells): the load pins on each, the design's own load plus the tap's first flop
foreach p [get_pins -quiet -hier -filter {NAME =~ u_dbg/g_p[*].u_x/src_pulse}] {
    set n [get_nets -of_objects $p]
    puts $f "$n|[llength [get_pins -of_objects $n -filter {DIRECTION == IN}]]"
}
close $f
close_design
