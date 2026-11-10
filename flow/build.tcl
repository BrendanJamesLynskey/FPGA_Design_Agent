# build.tcl: the non-project Vivado flow, RTL + XDC to a bitstream and reports.
#
#   vivado -mode batch -source flow/build.tcl -tclargs <build dir>/inputs.tcl
#
# Run it through flow/run_vivado.sh, which writes inputs.tcl (flow/prepare.py),
# applies the memory guard and records time and memory. Every report the
# gates read (flow/gates.py) lands in the build directory, one group per
# UltraFast stage (docs/methodology.md): rtl, post_synth, post_place,
# post_route, bitstream. AMD UG949 v2025.2 places report_methodology at three
# stages (elaborated RTL, after synthesis, after implementation; ch. 1 "Using
# the UltraFast Design Methodology DRCs"), check_timing and the timing summary
# after synthesis and after each implementation step (ch. 6 "Evaluating Design
# WNS After Each Step"), report_qor_assessment after synthesis (ch. 5
# "Assessing Post-Synthesis Quality of Results") and report_drc/report_cdc/
# report_power at closure (ch. 6).

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
set gen_args {}
foreach g $generics { lappend gen_args -generic $g }

# --- stage rtl: elaborate and run the RTL methodology DRCs ------------------
# UG949 ch. 3 "Running RTL DRCs": report_methodology on the elaborated design.
# synth_design -rtl elaborates without synthesising; the real synth_design below
# re-elaborates from the sources (non-project mode), so nothing is reused.
synth_design -rtl -rtl_skip_ip -top $top -part $part {*}$gen_args
stage elaborate
report_methodology -file $out/methodology_rtl.rpt
stage rtl_reports

# --- stage post_synth ----------------------------------------------------------
synth_design -top $top -part $part {*}$gen_args
stage synth
# AMD's scoped XPM constraints are not applied in this non-project flow (QR1, docs/methodology.md): apply them by cell name
source $flow_dir/xpm_cdc.tcl
apply_xpm_cdc_constraints
write_checkpoint -force $out/post_synth.dcp
# UG949 ch. 5 "Moving Past Synthesis": DRCs, methodology, timing constraints,
# QoR assessment, utilisation, clock trees; ch. 6 "Baselining and Timing
# Constraints Validation Procedure" steps 2-5 and 10 (timing summary, check_timing,
# clock networks, clock interaction, high-fanout nets).
report_timing_summary -max_paths 10 -report_unconstrained -file $out/timing_summary_synth.rpt
check_timing -verbose -file $out/check_timing_synth.rpt
report_methodology    -file $out/methodology_synth.rpt
# design standard STD-CDC-02 (docs/design_standards.md, brief 05d): report_cdc on the synthesised netlist
report_cdc -details   -file $out/cdc_synth.rpt
# brief 16: every asynchronous register-to-register path of the netlist, for flow/cdc_structure.py (gate post_synth_cdc_structure_clean)
source $flow_dir/cdc_paths.tcl
cdc_dump_paths $out/cdc_paths_synth.rpt
report_drc            -file $out/drc_synth.rpt
report_qor_assessment -file $out/qor_assessment_synth.rpt
report_utilization    -file $out/utilization_synth.rpt
report_clock_networks -file $out/clock_networks_synth.rpt
report_clock_interaction -delay_type min_max -file $out/clock_interaction_synth.rpt
report_high_fanout_nets -timing -load_types -max_nets 25 -file $out/high_fanout_synth.rpt
# brief 20: every timing exception, the ones Vivado drops (overridden or no path) and the endpoints each covers, for
# flow/exceptions_check.py (gates post_synth_exceptions_clean and exceptions_clean; UG906 ch. 5 "Report Exceptions")
source $flow_dir/mcp_paths.tcl
proc exception_reports {out sfx} {
    mcp_dump_paths $out/mcp_paths_$sfx.txt
    report_exceptions           -file $out/exceptions_$sfx.rpt
    report_exceptions -ignored  -file $out/exceptions_ignored_$sfx.rpt
    report_exceptions -coverage -file $out/exceptions_coverage_$sfx.rpt
}
exception_reports $out synth
# brief 20 part B: each port's delays, IOB register and synchroniser, the clocks (virtual, generated, input jitter), for
# flow/io_check.py (gates post_synth_io_constraints_clean and io_timing_clean)
source $flow_dir/io_paths.tcl
io_dump_paths $out/io_paths_synth.txt
stage synth_reports
# stage-limited build (FDA_STOP_AFTER via flow/prepare.py): stop here after the post_synth reports
proc stop_here {name} {
    global stop_after stage_log
    if {$stop_after eq $name} {
        close $stage_log
        puts "FLOW-STOPPED after $name"
        exit 0
    }
}
if {$ila eq "0"} { stop_here synth }

if {$ila} {
    source $flow_dir/debug.tcl
    insert_ila $probes_tcl $out
    stage ila_inserted
}

# --- implementation ----------------------------------------------------------
# brief 20 part B: build.yaml timing_margin_ns, an implementation-only setup margin on every design clock (UG949 v2025.2
# ch. 6 "Overconstraining the Design": -setup only, reset to 0 before the router), taken off before routing
set margin_clocks {}
if {[info exists timing_margin_ns] && $timing_margin_ns > 0} {
    foreach c [get_clocks -quiet] { if {[get_property -quiet SOURCE_PINS $c] ne ""} { lappend margin_clocks $c } }
    if {[llength $margin_clocks]} { set_clock_uncertainty -setup $timing_margin_ns $margin_clocks }
    set mf [open $out/timing_margin.txt w]
    puts $mf "margin_ns $timing_margin_ns"
    puts $mf "clocks [join $margin_clocks { }]"
    close $mf
}
opt_design
stage opt
place_design
stage place
phys_opt_design
stage phys_opt
# stage post_place: UG949 ch. 6 "Pre- and Post-Placement" (large hold violations
# must be fixed before routing) and figure 113 "Baselining the Design"
report_timing_summary -max_paths 10 -file $out/timing_summary_place.rpt
if {[llength $margin_clocks]} {
    set_clock_uncertainty -setup 0 $margin_clocks
    report_timing_summary -max_paths 3 -file $out/timing_summary_place_nomargin.rpt
}
stage place_reports
if {$ila eq "0"} { stop_here place }
route_design
stage route
write_checkpoint -force $out/post_route.dcp

# --- stage post_route: reports (the gates read these) ------------------------
report_timing_summary -max_paths 10 -report_unconstrained -file $out/timing_summary.rpt
check_timing -verbose -file $out/check_timing.rpt
report_utilization    -file $out/utilization.rpt
report_utilization    -hierarchical -file $out/utilization_hier.rpt
report_methodology    -file $out/methodology.rpt
report_cdc -details   -file $out/cdc.rpt
report_drc            -file $out/drc.rpt
report_qor_assessment -file $out/qor_assessment_route.rpt
exception_reports $out route
io_dump_paths $out/io_paths_route.txt
report_timing -delay_type max -max_paths 1 -file $out/timing_worst_setup.rpt
report_timing -delay_type min -max_paths 1 -file $out/timing_worst_hold.rpt
# the board's thermal environment (boards/<board>/board.yaml, via prepare.py) so that the
# junction temperature is the board's, not Vivado's default heat sink and 250 LFM airflow
if {[info exists power_env] && $power_env ne ""} { set_operating_conditions {*}$power_env }
report_power          -file $out/power.rpt
report_io             -file $out/io.rpt
stage reports
# brief 18: machine-readable cross-probing (RTL file/line, clock region, routed tiles of the worst paths) as evidence;
# off unless FDA_XPROBE=1, and it changes no report and no gate
if {[info exists ::env(FDA_XPROBE)] && $::env(FDA_XPROBE) eq "1"} {
    source $flow_dir/xprobe.tcl
    xprobe_dump $out/xprobe.json
    stage xprobe
}
if {$ila eq "0"} { stop_here route }

# --- stage bitstream -----------------------------------------------------------
write_bitstream -force $out/$top.bit
if {$ila} {
    write_debug_probes -force $out/$top.ltx
}
stage bitstream
close $stage_log
puts "FLOW-DONE $out/$top.bit"
