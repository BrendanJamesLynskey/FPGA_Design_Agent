# build.tcl: non-project Vivado build of the CDC soak rig.
#
#   vivado -mode batch -source hil/cdc_soak/tcl/build.tcl -tclargs <small|full> <out dir> [place directive] [route directive] [build id]
#
# Run it through hil/cdc_soak/run_build.sh (heavy slot, systemd-run MemoryMax, one Vivado at a time). Stages:
# synth, the crossing constraints (tcl/rig_cdc.tcl), opt/place/phys_opt/route, the closure reports the brief asks
# for (report_cdc, report_methodology, report_bus_skew, report_power, utilisation, timing), the bitstream, and the
# per-copy routed delay and skew table (tcl/delay_table.tcl). Nothing here opens the hardware manager.

# Threads: FDA_VIVADO_THREADS (1-8; set by _handoff/take_heavy_slot.sh --env on the shared PC), else 2 as before
# (brief 33 measured 1, 2 and 4 on this build: results/33_vivado_speed).
set nthreads [expr {[info exists ::env(FDA_VIVADO_THREADS)] && $::env(FDA_VIVADO_THREADS) ne "" ? $::env(FDA_VIVADO_THREADS) : 2}]
if {![string is integer -strict $nthreads] || $nthreads < 1 || $nthreads > 8} { error "FDA_VIVADO_THREADS must be 1-8, not '$nthreads'" }
set_param general.maxThreads $nthreads
set_param synth.maxThreads   $nthreads

set here [file dirname [file normalize [info script]]]
set rig  [file dirname $here]
set mode [lindex $argv 0]
set out  [file normalize [lindex $argv 1]]
set pdir [expr {[llength $argv] > 2 ? [lindex $argv 2] : "Default"}]
set rdir [expr {[llength $argv] > 3 ? [lindex $argv 3] : "Default"}]
set bid  [expr {[llength $argv] > 4 ? [lindex $argv 4] : "00000000"}]
set part xc7a100tcsg324-1
file mkdir $out
source $here/rig_map.tcl
set rig_counts [expr {$mode eq "full" ? $rig_counts_full : $rig_counts_small}]

set t0 [clock milliseconds]
set stage_log [open $out/stages.txt w]
proc stage {name} {
    global t0 stage_log
    set s [expr {([clock milliseconds] - $t0) / 1000.0}]
    puts $stage_log [format "%-16s %8.1f" $name $s]
    flush $stage_log
    puts "RIG-STAGE $name at ${s}s"
}

foreach f {rig_pkg cdc_lib rig_check afifo16 rig_copy rig_ctrl rig_core rig_top} {
    read_verilog -sv $rig/rtl/$f.sv
}
read_xdc $rig/constr/rig.xdc
synth_design -top rig_top -part $part -flatten_hierarchy rebuilt {*}[rig_generics $rig_counts] -generic BUILD_ID=32'h$bid
stage synth
source $here/rig_cdc.tcl
stage constraints
report_utilization -file $out/util_synth.rpt
write_checkpoint -force $out/post_synth.dcp

opt_design
stage opt
place_design -directive $pdir
stage place
phys_opt_design
stage phys_opt
route_design -directive $rdir
stage route
write_checkpoint -force $out/post_route.dcp
# brief 33: the placed and routed result as text (flow/result_hash.py), only when FDA_RESULT_HASH=1
if {[info exists ::env(FDA_RESULT_HASH)] && $::env(FDA_RESULT_HASH) eq "1"} {
    source [file join [file dirname $rig] .. flow result_hash.tcl]
    result_dump $out/result_dump.txt
    stage result_dump
}

report_timing_summary -max_paths 20 -file $out/timing_summary.rpt
report_clock_interaction -file $out/clock_interaction.rpt
report_cdc -file $out/cdc_summary.rpt
report_cdc -details -show_waiver -file $out/cdc_details.rpt
report_cdc -no_waiver -file $out/cdc_summary_nowaiver.rpt
report_cdc -details -waived -file $out/cdc_waived.rpt
report_methodology -file $out/methodology.rpt
report_methodology -no_waiver -file $out/methodology_nowaiver.rpt
report_bus_skew -file $out/bus_skew.rpt
report_power -file $out/power.rpt
report_utilization -file $out/util.rpt
report_utilization -hierarchical -hierarchical_depth 3 -file $out/util_hier.rpt
report_drc -file $out/drc.rpt
report_waivers -file $out/waivers.rpt
stage reports

write_bitstream -force $out/rig_$mode.bit
stage bitstream

source $here/delay_table.tcl
rig_delay_table $out $rig_counts
stage delay_table
close $stage_log
