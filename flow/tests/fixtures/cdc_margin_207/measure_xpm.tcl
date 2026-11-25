# measure_xpm.tcl: brief 207 finding 5. Synthesise x_xpm_hs out of context, apply the flow's flow/xpm_cdc.tcl exactly as
# flow/build.tcl does, and record the exceptions and bus skew that result, beside the values AMD's shipped template
# (data/ip/xpm/xpm_cdc/tcl/xpm_cdc_handshake.tcl, xpm_cdc_gray.tcl) would give for the same clocks.
#   vivado -mode batch -source measure_xpm.tcl -tclargs <flow dir> <rtl dir> <part> <out dir>
set flow [lindex $argv 0]; set rtl [lindex $argv 1]; set part [lindex $argv 2]; set out [lindex $argv 3]
set thr 1; if {[info exists ::env(FDA_VIVADO_THREADS)]} { set thr $::env(FDA_VIVADO_THREADS) }
set_param general.maxThreads $thr
file mkdir $out
source $flow/xpm_cdc.tcl
read_verilog $rtl/x_xpm_hs.v
synth_design -top x_xpm_hs -part $part -mode out_of_context
create_clock -name clk_a -period 10.000 [get_ports clk_a]
create_clock -name clk_b -period 6.400 [get_ports clk_b]
set fh [open $out/metrics.txt w]
puts $fh "# measure_xpm v1 part=$part vivado=[version -short]"
report_exceptions -file $out/exceptions_before_flow_rule.rpt
apply_xpm_cdc_constraints
report_exceptions -file $out/exceptions.rpt
opt_design; place_design; route_design
report_bus_skew -max_paths 20 -file $out/bus_skew.rpt
report_cdc -details -file $out/cdc.rpt
report_methodology -file $out/methodology.rpt
set hs_n [llength [get_cells -hierarchical -filter {NAME =~ *u_hs/xpm_cdc_single_src2dest_inst/syncstages_ff_reg*}]]
puts $fh "AMD_TEMPLATE|handshake|width=16|n_s2d=$hs_n|max_delay=[expr {6.4 * $hs_n}]|bus_skew=[expr {6.4 * $hs_n}]"
puts $fh "AMD_TEMPLATE|gray|max_delay=10.0|bus_skew=6.4"
foreach {n f t} {hs *u_hs/src_hsdata_ff_reg* *u_hs/dest_hsdata_ff_reg* gray *u_gray/src_gray_ff_reg* *u_gray/dest_graysync_ff_reg[0]*} {
    set fc [get_cells -hierarchical -filter "NAME =~ $f"]; set tc [get_cells -hierarchical -filter "NAME =~ $t"]
    set p [get_timing_paths -quiet -from $fc -to $tc -max_paths 100 -nworst 1]
    set ds {}; foreach q $p { lappend ds [get_property DATAPATH_DELAY $q] }
    set ds [lsort -real $ds]
    puts $fh "ROUTED|$n|npaths=[llength $ds]|dmax=[lindex $ds end]|req=[get_property REQUIREMENT [lindex $p 0]]|exc=[get_property EXCEPTION [lindex $p 0]]"
}
close $fh
