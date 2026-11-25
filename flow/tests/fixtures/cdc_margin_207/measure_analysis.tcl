# measure_analysis.tcl: brief 207 E1-E3 as analysis-only effects. One place-and-route of cdc207_top with the D constraints (per-crossing
# datapath-only bounds and bus skew), then the SAME routed design reported twice: before and after adding the U uncertainty (12.5 % of the
# destination period, setup and hold, both clocks and between them). Routing is not repeated, so any difference is the analysis alone.
#   vivado -mode batch -source measure_analysis.tcl -tclargs <variant dir with synth.dcp's parent> <part> <out dir>
set src  [lindex $argv 0]
set part [lindex $argv 1]
set out  [lindex $argv 2]
set thr 1
if {[info exists ::env(FDA_VIVADO_THREADS)]} { set thr $::env(FDA_VIVADO_THREADS) }
set_param general.maxThreads $thr
file mkdir $out
open_checkpoint $src/synth.dcp
create_clock -name clk_a -period 10.000 [get_ports clk_a]
create_clock -name clk_b -period 6.400  [get_ports clk_b]
proc cells {pats} { set r {}; foreach p $pats { set r [concat $r [get_cells -quiet -hierarchical -filter "IS_SEQUENTIAL && NAME =~ $p"]] }; return [lsort -unique $r] }
set cr {
    lvl   {lvl_a_reg}          {lvl_s1_reg}        6.4   -
    wptr  {wgray_a_reg[*]}     {wq1_b_reg[*]}      10.0  6.4
    rptr  {rgray_b_reg[*]}     {rq1_a_reg[*]}      6.4   6.4
    hsdat {hs_hold_a_reg[*]}   {hs_data_b_reg[*]}  19.2  19.2
    cfgd  {cfg_hold_a_reg[*]}  {cfg_b_reg[*]}      12.8  12.8
    tgl   {tg_a_reg}           {tg_s1_reg}         6.4   -
    hsreq {req_a_reg}          {rq1_b_reg}         6.4   -
    hsack {ack_b_reg}          {aq1_a_reg}         10.0  -
    cfgt  {ctg_a_reg}          {ct1_b_reg}         6.4   -
}
foreach {n f t l s} $cr {
    set fc [cells $f]; set tc [cells $t]
    if {[llength $fc] && [llength $tc]} {
        set_max_delay -datapath_only -from $fc -to $tc $l
        if {$s ne "-"} { set_bus_skew -from $fc -to $tc $s }
    }
}
opt_design; place_design; route_design
set fh [open $out/metrics.txt w]
puts $fh "# measure_analysis v1 part=$part vivado=[version -short]"
proc snap {tag fh out cr} {
    report_bus_skew -max_paths 20 -nworst 1 -file $out/bus_skew_$tag.rpt
    report_timing_summary -max_paths 10 -file $out/timing_summary_$tag.rpt
    foreach {n f t l s} $cr {
        set fc [cells $f]; set tc [cells $t]
        if {![llength $fc] || ![llength $tc]} { continue }
        set p [get_timing_paths -quiet -from $fc -to $tc -setup -max_paths 1]
        if {$p eq ""} { continue }
        set rt [report_timing -of_objects $p -return_string]
        set unc "none"; regexp {Clock Uncertainty:\s+(-?[0-9.]+)ns} $rt -> unc
        puts $fh "$tag|CROSS|$n|slack=[get_property SLACK $p]|dmax=[get_property DATAPATH_DELAY $p]|unc=$unc"
    }
    foreach c {a b} {
        set p [get_timing_paths -quiet -from [get_clocks clk_$c] -to [get_clocks clk_$c] -setup]
        set h [get_timing_paths -quiet -from [get_clocks clk_$c] -to [get_clocks clk_$c] -hold]
        puts $fh "$tag|FILL|$c|wns=[get_property SLACK $p]|whs=[get_property SLACK $h]"
    }
    if {[regexp {^xck} [get_property PART [current_design]]]} {
        if {[catch { report_synchronizer_mtbf -file $out/mtbf_$tag.rpt } e]} { puts $fh "$tag|MTBF|error|$e" }
    }
}
snap before $fh $out $cr
set_clock_uncertainty 1.250 [get_clocks clk_a]
set_clock_uncertainty 0.800 [get_clocks clk_b]
set_clock_uncertainty -from [get_clocks clk_a] -to [get_clocks clk_b] 0.800
set_clock_uncertainty -from [get_clocks clk_b] -to [get_clocks clk_a] 1.250
snap after_u $fh $out $cr
close $fh
puts "measure_analysis: done"
