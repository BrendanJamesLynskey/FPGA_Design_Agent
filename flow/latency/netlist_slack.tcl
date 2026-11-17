# netlist_slack.tcl (brief 97): the post-route slack of each latency stage's registers.
#   vivado -mode batch -source flow/latency/netlist_slack.tcl -tclargs <post_route.dcp> <stages.tsv> <out.tsv>
# stages.tsv: one stage per line, "<id>\t<cell name pattern>\t<pattern>...". out.tsv: "<id>\t<cells>\t<clock>\t<setup slack ns>\t<hold slack ns>"
# (slack of the worst path that ENDS at the stage's registers; "-" when the stage has no matching register or no timed path).
set_param general.maxThreads 1
lassign $argv dcp tsv out
open_checkpoint $dcp
set fo [open $out w]
set fi [open $tsv r]
while {[gets $fi line] >= 0} {
    set f [split $line "\t"]
    set id [lindex $f 0]
    set cells {}
    foreach pat [lrange $f 1 end] {
        if {$pat eq ""} continue
        foreach c [get_cells -quiet -hierarchical -filter "IS_SEQUENTIAL && NAME =~ $pat"] { lappend cells $c }
    }
    if {[llength $cells] == 0} { puts $fo "$id\t0\t-\t-\t-"; continue }
    set clk "-"
    set ck [get_clocks -quiet -of_objects [get_pins -quiet -of_objects [lindex $cells 0] -filter {IS_CLOCK}]]
    if {[llength $ck]} { set clk [get_property NAME [lindex $ck 0]] }
    set sp [get_timing_paths -quiet -to $cells -max_paths 1 -setup]
    set hp [get_timing_paths -quiet -to $cells -max_paths 1 -hold]
    set ss "-"; set hs "-"
    if {[llength $sp]} { set ss [get_property SLACK [lindex $sp 0]] }
    if {[llength $hp]} { set hs [get_property SLACK [lindex $hp 0]] }
    puts $fo "$id\t[llength $cells]\t$clk\t$ss\t$hs"
}
close $fi
close $fo
close_design
