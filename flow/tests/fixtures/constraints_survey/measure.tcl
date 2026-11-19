# measure.tcl (brief 105): one out-of-context implementation of one fixture variant, then the metrics for its experiment.
#   vivado -mode batch -source measure.tcl -tclargs <flow dir> <fixture dir> <exp m1|m2|m3> <top> <xdc name> <part> <generics, ""|"A=1 B=2"> <out dir>
# Writes <out>/metrics.txt (key value lines), the post-route reports and post_route.dcp. Threads come from FDA_VIVADO_THREADS (default 1).
set nthr 1
if {[info exists ::env(FDA_VIVADO_THREADS)] && $::env(FDA_VIVADO_THREADS) ne ""} { set nthr $::env(FDA_VIVADO_THREADS) }
set_param general.maxThreads $nthr
set_param synth.maxThreads $nthr
lassign $argv flow_dir fx_dir exp top xdcname part generics out
file mkdir $out
set gen {}
foreach g $generics { lappend gen -generic $g }
read_verilog -sv $fx_dir/rtl/[dict get {m1 m1_sync m2 m2_fanout m3 m3_bus} $exp].sv
read_xdc $fx_dir/xdc/$xdcname.xdc
synth_design -top $top -part $part -mode out_of_context {*}$gen
report_methodology -file $out/methodology_synth.rpt
report_cdc -details -file $out/cdc_synth.rpt
source $flow_dir/cdc_paths.tcl
cdc_dump_paths $out/cdc_paths_synth.rpt
opt_design
place_design
phys_opt_design
route_design
write_checkpoint -force $out/post_route.dcp
report_timing_summary -max_paths 5 -file $out/timing_summary.rpt
report_methodology -file $out/methodology.rpt
report_cdc -details -file $out/cdc.rpt
report_utilization -file $out/utilization.rpt
set m [open $out/metrics.txt w]
proc kv {k v} { global m; puts $m "$k $v" }
kv version [version -short]
kv part $part
kv wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
kv whs [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
proc site_xy {cell} {
    set s [get_property SITE $cell]
    if {[regexp {SLICE_X(\d+)Y(\d+)} $s -> x y]} { return [list $x $y $s] }
    return [list -1 -1 $s]
}
if {$exp eq "m1"} {
    set n [llength [get_cells -hierarchical -filter {NAME =~ *a1_reg[*] || NAME =~ *p1_reg[*]}]]
    kv chains $n
    set tot 0.0; set maxd 0; set same 0; set srl 0; set sumdelay 0.0; set maxdelay 0.0; set rows {}
    foreach c1 [get_cells -hierarchical -filter {NAME =~ *a1_reg[*] || NAME =~ *p1_reg[*]}] {
        regsub {1_reg\[(\d+)\]$} [get_property NAME $c1] {2_reg[\1]} n2
        set c2 [get_cells $n2]
        lassign [site_xy $c1] x1 y1 s1
        lassign [site_xy $c2] x2 y2 s2
        set d [expr {abs($x1-$x2) + abs($y1-$y2)}]
        if {$d == 0} { incr same }
        if {$d > $maxd} { set maxd $d }
        set tot [expr {$tot + $d}]
        set p [lindex [get_timing_paths -from $c1 -to $c2 -max_paths 1 -setup] 0]
        set dd [get_property DATAPATH_DELAY $p]
        set sumdelay [expr {$sumdelay + $dd}]
        if {$dd > $maxdelay} { set maxdelay $dd }
        lappend rows "[get_property NAME $c1] $s1 [get_property NAME $c2] $s2 d=$d delay_ns=$dd ref=[get_property REF_NAME $c1]"
    }
    kv mean_slice_distance [format %.2f [expr {$tot / double($n)}]]
    kv max_slice_distance $maxd
    kv chains_in_same_slice $same
    kv mean_s1_to_s2_delay_ns [format %.3f [expr {$sumdelay / $n}]]
    kv max_s1_to_s2_delay_ns [format %.3f $maxdelay]
    kv srl_cells [llength [get_cells -hierarchical -quiet -filter {REF_NAME =~ SRL*}]]
    kv fd_cells [llength [get_cells -hierarchical -quiet -filter {REF_NAME =~ FD*}]]
    kv async_reg_cells [llength [get_cells -hierarchical -quiet -filter {ASYNC_REG == TRUE}]]
    set f [open $out/chains.txt w]; puts $f [join $rows "\n"]; close $f
    # MTBF: UltraScale+ only (the command warns on 7-series)
    if {[catch {report_synchronizer_mtbf -file $out/mtbf.rpt} err]} { kv mtbf_error $err }
}
if {$exp eq "m2"} {
    set go [get_cells -hierarchical -filter {NAME =~ *go_reg*}]
    kv go_register_cells [llength $go]
    set maxf 0
    foreach c $go {
        set q [get_pins -of_objects $c -filter {REF_PIN_NAME == Q}]
        set net [get_nets -of_objects $q]
        set f [llength [get_pins -leaf -of_objects $net -filter {DIRECTION == IN}]]
        if {$f > $maxf} { set maxf $f }
        lappend fl $f
    }
    kv go_fanouts [lsort -integer -decreasing $fl]
    kv max_go_fanout $maxf
    kv ff_count [llength [get_cells -hierarchical -quiet -filter {REF_NAME =~ FD*}]]
    # the worst setup path that starts at a copy of the control register (the design's worst path overall may be an I/O path)
    set gp [lindex [get_timing_paths -from $go -max_paths 1 -setup] 0]
    kv go_path_wns [get_property SLACK $gp]
    kv go_path_delay_ns [get_property DATAPATH_DELAY $gp]
    kv go_path_logic_levels [get_property LOGIC_LEVELS $gp]
    set p [lindex [get_timing_paths -max_paths 1 -setup] 0]
    kv worst_path_start [get_property STARTPOINT_PIN $p]
    kv worst_path_logic_levels [get_property LOGIC_LEVELS $p]
}
if {$exp eq "m3"} {
    set dl {}
    foreach c1 [get_cells q1_reg[*]] {
        regsub {q1_reg\[(\d+)\]$} [get_property NAME $c1] {gray_reg[\1]} n0
        set p [lindex [get_timing_paths -from [get_cells $n0] -to $c1 -max_paths 1 -setup] 0]
        lappend dl [get_property DATAPATH_DELAY $p]
    }
    set mx [lindex [lsort -real -decreasing $dl] 0]
    set mn [lindex [lsort -real $dl] 0]
    kv bit_delays_ns [join [lmap x $dl {format %.3f $x}] ,]
    kv delay_min_ns [format %.3f $mn]
    kv delay_max_ns [format %.3f $mx]
    kv delay_spread_ns [format %.3f [expr {$mx - $mn}]]
    catch {report_bus_skew -file $out/bus_skew.rpt}
    catch {report_exceptions -file $out/exceptions.rpt}
}
close $m
puts "MEASURE-DONE $out"
