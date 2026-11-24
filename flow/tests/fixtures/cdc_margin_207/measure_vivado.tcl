# measure_vivado.tcl: brief 207, one out-of-context synthesis of cdc207_top, then one place-and-route per constraint variant.
#
#   vivado -mode batch -source measure_vivado.tcl -tclargs <rtl dir> <part> <BAD> <clk_b period> <out dir> <variant> ...
#
# Variants (results/207_cdc_margin/README.md section 3):
#   N           set_clock_groups -asynchronous only
#   U           N plus user clock uncertainty of 12.5 % of the destination period (setup and hold, both clocks and between them)
#   D_<dir>     per-crossing set_max_delay -datapath_only at the latency bound L, set_bus_skew at the skew bound S; no clock group
#   DU          D plus U's uncertainty
#   M_<dir>     the draft method: D with L and S each reduced by U_pair, the tool's own clock uncertainty for the pair,
#               read from the header of D's report_bus_skew (run D first in the same call)
#   B3N B3U B3D B3M   as N/U/D/M with the first stages of the Gray write pointer pulled apart: bits 0-3 at the lowest slices,
#               bits 4-7 at the highest (LOC), to make the routed skew large
# <dir> is the place_design directive (Default, Explore, ExtraNetDelay_high), standing in for a seed.
# After routing, every variant gets the SAME post-route bus-skew assertions (set_bus_skew is an assertion, UG903 p. 143, and only
# route_design optimises it, so adding it after routing measures the routed skew without changing it), so skew is comparable across
# variants; the variants that carry the constraint during routing are D, DU, M.

set rtl   [lindex $argv 0]
set part  [lindex $argv 1]
set bad   [lindex $argv 2]
set pb    [lindex $argv 3]
set out   [lindex $argv 4]
set variants [lrange $argv 5 end]
set pa 10.000
set thr 1
if {[info exists ::env(FDA_VIVADO_THREADS)]} { set thr $::env(FDA_VIVADO_THREADS) }
set_param general.maxThreads $thr
catch { set_param synth.maxThreads $thr }
file mkdir $out

if {[info exists ::env(FDA_FLOW)]} { source $::env(FDA_FLOW)/cdc_paths.tcl }
read_verilog $rtl/cdc207_top.v
synth_design -top cdc207_top -part $part -mode out_of_context -generic BAD=$bad -flatten_hierarchy rebuilt
write_checkpoint -force $out/synth.dcp

# ---------- the crossings: name -> {from cells, to cells, source clock, latency bound kind, skew bound kind} ----------
# L kinds: src = source period; dst = one destination period; dstN<k> = k destination periods (handshake/CE capture)
proc cr_list {} {
    return {
        lvl   {lvl_a_reg}          {lvl_s1_reg}        a dst   -
        tgl   {tg_a_reg}           {tg_s1_reg}         a dst   -
        wptr  {wgray_a_reg[*] wbin_a_reg[*]} {wq1_b_reg[*]} a src   min
        rptr  {rgray_b_reg[*] rbin_b_reg[*]} {rq1_a_reg[*]} b src   min
        ram   {mem_reg*}           {dout_b_reg[*]}     a src   -
        hsreq {req_a_reg}          {rq1_b_reg}         a dst   -
        hsack {ack_b_reg}          {aq1_a_reg}         b dst   -
        hsdat {hs_hold_a_reg[*]}   {hs_data_b_reg[*]}  a dstN3 dstN3
        cfgt  {ctg_a_reg}          {ct1_b_reg}         a dst   -
        cfgd  {cfg_hold_a_reg[*]}  {cfg_b_reg[*]}      a dstN2 dstN2
    }
}
proc cells_of {pats} {
    set r {}
    foreach p $pats { set r [concat $r [get_cells -quiet -hierarchical -filter "IS_SEQUENTIAL && NAME =~ $p"]] }
    return [lsort -unique $r]
}
proc period_of {d} { return [get_property PERIOD [get_clocks clk_$d]] }
proc other {d} { return [expr {$d eq "a" ? "b" : "a"}] }
proc bound {kind src} {
    set ps [period_of $src]; set pd [period_of [other $src]]
    switch -glob -- $kind {
        src   { return $ps }
        dst   { return $pd }
        min   { return [expr {min($ps, $pd)}] }
        dstN* { return [expr {[string range $kind 4 end] * $pd}] }
        default { return "" }
    }
}

proc clocks {pb} {
    create_clock -name clk_a -period 10.000 [get_ports clk_a]
    create_clock -name clk_b -period $pb    [get_ports clk_b]
}
proc add_uncertainty {} {
    set ua [expr {0.125 * [period_of a]}]; set ub [expr {0.125 * [period_of b]}]
    set_clock_uncertainty $ua [get_clocks clk_a]
    set_clock_uncertainty $ub [get_clocks clk_b]
    set_clock_uncertainty -from [get_clocks clk_a] -to [get_clocks clk_b] $ub
    set_clock_uncertainty -from [get_clocks clk_b] -to [get_clocks clk_a] $ua
}
# per-crossing bounds; margin m (ns) is taken off every bound (the method's M variant)
proc add_bounds {m fh} {
    foreach {n f t s lk sk} [cr_list] {
        set fc [cells_of $f]; set tc [cells_of $t]
        if {[llength $fc] == 0 || [llength $tc] == 0} { puts $fh "BOUND|$n|missing cells"; continue }
        set L [expr {[bound $lk $s] - $m}]
        set_max_delay -datapath_only -from $fc -to $tc $L
        set S ""
        if {$sk ne "-"} { set S [expr {[bound $sk $s] - $m}]; set_bus_skew -from $fc -to $tc $S }
        puts $fh "BOUND|$n|L=$L|S=$S|m=$m"
    }
}
proc add_skew_assertions {} {
    # post-route measurement assertions on every multi-bit crossing (same in every variant); a huge value never fails
    foreach {n f t s lk sk} [cr_list] {
        if {$sk eq "-"} { continue }
        set fc [cells_of $f]; set tc [cells_of $t]
        if {[llength $fc] > 1 && [llength $tc] > 1} { set_bus_skew -from $fc -to $tc 1000.0 }
    }
}
# B3: pull the Gray write-pointer first stages apart (bits 0-3 lowest slices, 4-7 highest), sources left to the placer
proc pull_apart {fh} {
    set sl [get_sites -filter {SITE_TYPE == SLICEL}]
    set scored {}
    foreach s $sl { lappend scored [list [expr {[get_property RPM_X $s] + [get_property RPM_Y $s]}] $s] }
    set scored [lsort -integer -index 0 $scored]
    set lo [lrange $scored 0 3]; set hi [lrange $scored end-3 end]
    for {set i 0} {$i < 8} {incr i} {
        set c [get_cells -quiet "wq1_b_reg\[$i\]"]
        if {$c eq ""} { continue }
        set site [lindex [expr {$i < 4 ? [lindex $lo $i] : [lindex $hi [expr {$i - 4}]]}] 1]
        set_property LOC $site $c
        puts $fh "LOC|wq1_b_reg\[$i\]|$site"
    }
}

# max datapath delay and spread per crossing (setup paths, including ignored ones under clock groups)
proc measure {fh} {
    foreach {n f t s lk sk} [cr_list] {
        set fc [cells_of $f]; set tc [cells_of $t]
        if {[llength $fc] == 0 || [llength $tc] == 0} { continue }
        set ps [get_timing_paths -quiet -from $fc -to $tc -max_paths 200 -nworst 1 -setup]
        set ign 0
        if {[llength $ps] == 0} { set ps [get_timing_paths -quiet -from $fc -to $tc -max_paths 200 -nworst 1 -setup -user_ignored]; set ign 1 }
        set ds {}
        foreach p $ps { lappend ds [get_property DATAPATH_DELAY $p] }
        if {[llength $ds] == 0} { puts $fh "CROSS|$n|npaths=0"; continue }
        set ds [lsort -real $ds]
        set slack [get_property SLACK [lindex $ps 0]]
        # the clock uncertainty and requirement of the worst path, read from report_timing (ignored paths included)
        set unc ""; set req ""
        set rt [report_timing -of_objects [lindex $ps 0] -return_string]
        regexp {Clock Uncertainty:\s+(-?[0-9.]+)ns} $rt -> unc
        regexp {Requirement:\s+(-?[0-9.]+)ns} $rt -> req
        if {$unc ne "" && $unc > $::upair_seen} { set ::upair_seen $unc }
        puts $fh [format "CROSS|%s|npaths=%d|ignored=%d|dmax=%.3f|dmin=%.3f|spread=%.3f|slack=%s|unc=%s|req=%s" $n [llength $ds] $ign \
            [lindex $ds end] [lindex $ds 0] [expr {[lindex $ds end] - [lindex $ds 0]}] $slack $unc $req]
    }
    foreach c {a b} {
        set p [get_timing_paths -quiet -from [get_clocks clk_$c] -to [get_clocks clk_$c] -setup]
        set h [get_timing_paths -quiet -from [get_clocks clk_$c] -to [get_clocks clk_$c] -hold]
        puts $fh "FILL|$c|wns=[get_property SLACK $p]|whs=[get_property SLACK $h]"
    }
    foreach {x y} {a b b a} {
        set p [get_timing_paths -quiet -from [get_clocks clk_$x] -to [get_clocks clk_$y] -setup]
        if {$p ne ""} { puts $fh "INTER|$x->$y|wns=[get_property SLACK $p]|from=[get_property STARTPOINT_PIN $p]|to=[get_property ENDPOINT_PIN $p]" } \
        else { puts $fh "INTER|$x->$y|none" }
    }
}

set upair 0.0
set ::upair_seen 0.0
foreach v $variants {
    set d $out/$v
    file mkdir $d
    open_checkpoint $out/synth.dcp
    set fh [open $d/metrics.txt w]
    puts $fh "# measure_vivado v1 part=$part bad=$bad pb=$pb variant=$v vivado=[version -short]"
    clocks $pb
    set dir Default
    if {[regexp {_(\w+)$} $v -> dd]} { set dir $dd }
    set base [regsub {_\w+$} $v {}]
    set b3 0
    if {[string match B3* $base]} { set b3 1; set base [string range $base 2 end] }
    switch -- $base {
        N  { set_clock_groups -asynchronous -group clk_a -group clk_b }
        U  { set_clock_groups -asynchronous -group clk_a -group clk_b; add_uncertainty }
        D  { add_bounds 0.0 $fh }
        DU { add_bounds 0.0 $fh; add_uncertainty }
        M  { puts $fh "UPAIR|$upair"; add_bounds $upair $fh }
        default { error "unknown variant $v" }
    }
    if {$b3} { pull_apart $fh }
    opt_design
    place_design -directive $dir
    route_design
    report_bus_skew -max_paths 20 -nworst 1 -file $d/bus_skew_constraint.rpt
    add_skew_assertions
    report_bus_skew -max_paths 20 -nworst 1 -file $d/bus_skew.rpt
    report_timing_summary -max_paths 20 -file $d/timing_summary.rpt
    report_exceptions -file $d/exceptions.rpt
    report_methodology -file $d/methodology.rpt
    report_cdc -details -file $d/cdc.rpt
    if {[string match xck26* $part] || [string match xczu* $part]} {
        if {[catch { report_synchronizer_mtbf -file $d/mtbf.rpt } e]} { puts $fh "MTBF|error|$e" }
    }
    report_utilization -file $d/utilization.rpt
    if {[llength [info procs cdc_dump_paths]]} { cdc_dump_paths $d/cdc_paths.rpt }
    set ::upair_seen 0.0
    measure $fh
    # U_pair for M: the largest tool-computed clock uncertainty on a crossing path, taken from the first variant run (N: no user
    # uncertainty, so this is Vivado's own jitter and phase error for the pair)
    if {$upair == 0.0 && ($base eq "N")} { set upair $::upair_seen; puts $fh "UPAIR_MEASURED|$upair" }
    close $fh
    close_design
}
puts "measure_vivado: done $variants"
