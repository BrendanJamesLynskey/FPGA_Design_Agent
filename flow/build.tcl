# build.tcl: the non-project Vivado flow, RTL + XDC to a bitstream and reports.
#
#   vivado -mode batch -source flow/build.tcl -tclargs <build dir>/inputs.tcl
#
# Run it through flow/run_vivado.sh, which writes inputs.tcl (flow/prepare.py),
# applies the memory guard and records time and memory. Every report the
# gates read (flow/gates.py) lands in the build directory.

# Memory on the 16 GB build PC. Above 1 thread Vivado is OOM-killed at 5-6 GB.
# general.maxThreads does not lower synth.maxThreads (it stays at 7), and
# chipscope.maxJobs (0 = automatic) lets the ILA build synthesise its debug
# cores in parallel helper Vivado processes, so all three are pinned to 1.
set_param general.maxThreads 1
set_param synth.maxThreads   1
set_param chipscope.maxJobs  1

source [lindex $argv 0]
set flow_dir [file dirname [file normalize [info script]]]
file mkdir $out
set t0 [clock milliseconds]
set stage_log [open $out/stages.txt w]
proc stage {name} {
    global t0 stage_log
    set s [expr {([clock milliseconds] - $t0) / 1000.0}]
    puts $stage_log [format "%-16s %8.1f" $name $s]
    flush $stage_log
    puts "FLOW-STAGE $name at ${s}s"
}

# --- read --------------------------------------------------------------------
foreach f $sources     { read_verilog -sv $f }
foreach x $constraints { read_xdc $x }
stage read

# --- synthesis ---------------------------------------------------------------
set gen_args {}
foreach g $generics { lappend gen_args -generic $g }
synth_design -top $top -part $part {*}$gen_args
stage synth
write_checkpoint -force $out/post_synth.dcp
report_utilization -file $out/utilization_synth.rpt

if {$ila} {
    source $flow_dir/debug.tcl
    insert_ila $probes_tcl $out
    stage ila_inserted
}

# --- implementation ----------------------------------------------------------
opt_design
stage opt
place_design
stage place
phys_opt_design
stage phys_opt
route_design
stage route
write_checkpoint -force $out/post_route.dcp

# --- reports (the gates read these) ------------------------------------------
report_timing_summary -max_paths 10 -report_unconstrained -file $out/timing_summary.rpt
check_timing -verbose -file $out/check_timing.rpt
report_utilization    -file $out/utilization.rpt
report_utilization    -hierarchical -file $out/utilization_hier.rpt
report_methodology    -file $out/methodology.rpt
report_cdc -details   -file $out/cdc.rpt
report_drc            -file $out/drc.rpt
# the board's thermal environment (boards/<board>/board.yaml, via prepare.py) so that the
# junction temperature is the board's, not Vivado's default heat sink and 250 LFM airflow
if {[info exists power_env] && $power_env ne ""} { set_operating_conditions {*}$power_env }
report_power          -file $out/power.rpt
report_io             -file $out/io.rpt
stage reports

# --- bitstream ---------------------------------------------------------------
write_bitstream -force $out/$top.bit
if {$ila} {
    write_debug_probes -force $out/$top.ltx
}
stage bitstream
close $stage_log
puts "FLOW-DONE $out/$top.bit"
