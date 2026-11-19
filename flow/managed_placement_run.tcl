# managed_placement_run.tcl: one placement of a placed-and-routed component in its project (brief 102, stage 2). The project's own top is
# synthesised with the component's slot as a black box, the supplier's locked checkpoint fills the slot (read_checkpoint -cell), Vivado places
# and routes everything else around it, and the facts that say whether the block was left alone and how it times are written:
#   <out>_run.json     whole-design WNS/WHS, route status, the block's cell->site map before and after, route-signature files
#   <out>_block.csv    the block-internal setup paths: endpoint, data-path delay, slack, logic levels (Vivado's report_timing)
#   <out>_routes_before.txt / _routes_after.txt   one line per net inside the block: name|ROUTE (before opt_design, after route_design)
#   BUDGET|name|delay|slack lines in the log: the contract's boundary budgets, when FDA_PR_BUDGET_TCL names the Tcl (managed_import.py budget-tcl)
# Environment: FDA_PR_PART FDA_PR_TOP FDA_PR_SRC (space-separated) FDA_PR_XDC FDA_PR_CELL FDA_PR_DCP FDA_PR_OUT [FDA_PR_DIRECTIVE FDA_PR_BUDGET_TCL FDA_PR_THREADS FDA_PR_EXTRA_XDC]
proc env_or {k d} { if {[info exists ::env($k)] && $::env($k) ne ""} { return $::env($k) } else { return $d } }
set n [env_or FDA_PR_THREADS 1]
set_param general.maxThreads $n
set_param synth.maxThreads $n
set_param chipscope.maxJobs 1
set_param tcl.collectionResultDisplayLimit 0       ;# the block has more than 500 cells and nets
set out $::env(FDA_PR_OUT); set cell $::env(FDA_PR_CELL)
set t0 [clock milliseconds]; set times [dict create]
proc lap {name} { upvar t0 t0 times times; set now [clock milliseconds]; dict set times $name [expr {($now - $t0) / 1000.0}]; set t0 $now }
foreach f $::env(FDA_PR_SRC) { if {[string match *.sv $f]} { read_verilog -sv $f } else { read_verilog $f } }
synth_design -top $::env(FDA_PR_TOP) -part $::env(FDA_PR_PART) -flatten_hierarchy rebuilt
lap synth
read_xdc $::env(FDA_PR_XDC)
if {[env_or FDA_PR_EXTRA_XDC ""] ne ""} { read_xdc $::env(FDA_PR_EXTRA_XDC) }   ;# the agent's own constraints around the block, for one arm
read_checkpoint -cell $cell $::env(FDA_PR_DCP)
lap read_block
proc block_cells {cell} { return [get_cells -hier -filter "IS_PRIMITIVE && NAME =~ $cell/*"] }
proc cell_sites {cell file} {
    set f [open $file w]
    foreach c [lsort [block_cells $cell]] { puts $f "[get_property NAME $c]|[get_property SITE $c]|[get_property BEL $c]|[get_property IS_LOC_FIXED $c]" }
    close $f
}
proc route_sig {names file} {
    set f [open $file w]
    foreach name [lsort $names] {
        set net [get_nets -quiet $name]
        if {$net eq ""} { puts $f "$name|missing|"; continue }
        puts $f "$name|[get_property IS_ROUTE_FIXED $net]|[get_property ROUTE $net]"
    }
    close $f
}
# the block's own routing: the nets inside it that arrive routed (nets with a pin outside are routed later by the project's router).
# Names, not objects: Tcl variables holding design objects go stale after read_checkpoint and opt_design.
set block_nets {}
foreach net [get_nets -hier -quiet -filter "TYPE == SIGNAL && NAME =~ $cell/* && ROUTE_STATUS == ROUTED"] { lappend block_nets [get_property NAME $net] }
cell_sites $cell ${out}_sites_before.txt
route_sig  $block_nets ${out}_routes_before.txt
opt_design
place_design -directive [env_or FDA_PR_DIRECTIVE Default]
lap place
route_design
lap route
cell_sites $cell ${out}_sites_after.txt
route_sig  $block_nets ${out}_routes_after.txt
write_checkpoint -force ${out}_routed.dcp
set wns [get_property SLACK [lindex [get_timing_paths -setup -max_paths 1] 0]]
set whs [get_property SLACK [lindex [get_timing_paths -hold -max_paths 1] 0]]
set rs [report_route_status -return_string]
regexp {of nets with routing errors\.*\s*:\s*(\d+)} $rs -> errs
if {![info exists errs]} { set errs -1 }
set bc [block_cells $cell]
set f [open ${out}_block.csv w]
puts $f "endpoint,data_path_delay_ns,slack_ns,logic_levels"
foreach p [get_timing_paths -setup -from $bc -to $bc -max_paths 5000 -nworst 1 -unique_pins] {
    puts $f "[string map [list ${cell}/ {}] [get_property ENDPOINT_PIN $p]],[get_property DATAPATH_DELAY $p],[get_property SLACK $p],[get_property LOGIC_LEVELS $p]"
}
close $f
if {[info exists ::env(FDA_PR_BUDGET_TCL)] && $::env(FDA_PR_BUDGET_TCL) ne ""} { source $::env(FDA_PR_BUDGET_TCL) }   ;# BUDGET|name|delay|slack lines go to the log
set tj [join [lmap {k v} $times {format {"%s": %s} $k $v}] {, }]
set jf [open ${out}_run.json w]
puts $jf "{\"vivado\": \"[version -short]\", \"part\": \"[get_property PART [current_design]]\", \"period_ns\": [get_property PERIOD [lindex [get_clocks] 0]], \"directive\": \"[env_or FDA_PR_DIRECTIVE Default]\", \"wns_ns\": $wns, \"whs_ns\": $whs, \"routing_errors\": $errs, \"block_cells\": [llength $bc], \"times_s\": {$tj}}"
close $jf
