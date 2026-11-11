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

# Threads (brief 33). The pins come from FDA_VIVADO_THREADS (1-8; unset: 1), which
# _handoff/take_heavy_slot.sh --env sets on the shared PC: 4 when this is the only
# Vivado job, 2 when the other heavy slot also runs Vivado. The old pin of 1 dated
# from the 16 GB PC, where builds above 1 thread were OOM-killed at 5-6 GB; on the
# 32 GB PC (2026-11-04) the measured peaks per thread count are in results/33_vivado_speed.
# general.maxThreads does not lower synth.maxThreads (it stays at 7), so both are
# set. chipscope.maxJobs stays at 1 at every thread count: when automatic (0) the
# ILA build synthesises its debug cores in parallel helper Vivado processes, each
# with its own memory (F0A: the 6 GB cap reached 111 times without the pin).
set fda_threads 1
if {[info exists ::env(FDA_VIVADO_THREADS)] && $::env(FDA_VIVADO_THREADS) ne ""} {
    set fda_threads $::env(FDA_VIVADO_THREADS)
    if {![string is integer -strict $fda_threads] || $fda_threads < 1 || $fda_threads > 8} {
        error "build.tcl: FDA_VIVADO_THREADS must be an integer from 1 to 8, not '$fda_threads'"
    }
}
set_param general.maxThreads $fda_threads
set_param synth.maxThreads   $fda_threads
set_param chipscope.maxJobs  1
puts "FLOW-THREADS $fda_threads"

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

# procs of the flow (definitions only)
source $flow_dir/xpm_cdc.tcl
source $flow_dir/cdc_paths.tcl
source $flow_dir/mcp_paths.tcl
source $flow_dir/io_paths.tcl
source $flow_dir/result_hash.tcl
proc exception_reports {out sfx} {
    mcp_dump_paths $out/mcp_paths_$sfx.txt
    report_exceptions           -file $out/exceptions_$sfx.rpt
    report_exceptions -ignored  -file $out/exceptions_ignored_$sfx.rpt
    report_exceptions -coverage -file $out/exceptions_coverage_$sfx.rpt
}
# stage-limited build (FDA_STOP_AFTER via flow/prepare.py): stop here after the post_synth reports
proc stop_here {name} {
    global stop_after stage_log
    if {$stop_after eq $name} {
        close $stage_log
        puts "FLOW-STOPPED after $name"
        exit 0
    }
}

# --- resume (brief 33) --------------------------------------------------------
# flow/run_vivado.sh sets resume_from when an earlier build of the same inputs (the same flow key: sources, XDC,
# generics, build.yaml settings, flow scripts, thread count, Vivado) stopped at an earlier stage. "synth" opens that
# build's post_synth.dcp and "route" its post_route.dcp (resume_dir), and the reports that build wrote for the stages
# skipped here are copied unchanged: they describe the same netlist. Unset or "": the whole flow from the RTL.
if {![info exists resume_from]} { set resume_from "" }
if {![info exists resume_dir]}  { set resume_dir "" }
proc copy_reports {from to patterns} {
    set n 0
    foreach pat $patterns {
        foreach f [glob -nocomplain -directory $from $pat] {
            if {[file isfile $f]} { file copy -force $f $to; incr n }
        }
    }
    return $n
}
# every file the rtl and post_synth stages write (the gates read these)
set synth_files {methodology_rtl.rpt *_synth.rpt *_synth.txt post_synth.dcp}
if {$resume_from ni {"" synth route}} { error "build.tcl: resume_from must be synth or route, not '$resume_from'" }

if {$resume_from eq ""} {
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
    cdc_dump_paths $out/cdc_paths_synth.rpt
    report_drc            -file $out/drc_synth.rpt
    report_qor_assessment -file $out/qor_assessment_synth.rpt
    report_utilization    -file $out/utilization_synth.rpt
    report_clock_networks -file $out/clock_networks_synth.rpt
    report_clock_interaction -delay_type min_max -file $out/clock_interaction_synth.rpt
    report_high_fanout_nets -timing -load_types -max_nets 25 -file $out/high_fanout_synth.rpt
    # brief 20: every timing exception, the ones Vivado drops (overridden or no path) and the endpoints each covers, for
    # flow/exceptions_check.py (gates post_synth_exceptions_clean and exceptions_clean; UG906 ch. 5 "Report Exceptions")
    exception_reports $out synth
    # brief 20 part B: each port's delays, IOB register and synchroniser, the clocks (virtual, generated, input jitter), for
    # flow/io_check.py (gates post_synth_io_constraints_clean and io_timing_clean)
    io_dump_paths $out/io_paths_synth.txt
    stage synth_reports
} elseif {$resume_from eq "synth"} {
    open_checkpoint $resume_dir/post_synth.dcp
    puts "FLOW-RESUMED from $resume_dir/post_synth.dcp ([copy_reports $resume_dir $out $synth_files] files copied)"
    stage resumed_synth
}
if {$ila eq "0"} { stop_here synth }

if {$ila} {
    source $flow_dir/debug.tcl
    insert_ila $probes_tcl $out
    stage ila_inserted
}

if {$resume_from ne "route"} {
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
    # brief 33: incremental implementation (FDA_INCREMENTAL=1 via flow/run_vivado.sh, which keeps the previous build's
    # post_route.dcp as the reference). Vivado reuses the reference's placement and routing for the cells that match and
    # falls back to the default flow when too little matches (report_incremental_reuse says which). Off by default: the
    # gates' reference builds always run the default flow.
    if {[info exists incremental_ref] && $incremental_ref ne ""} {
        read_checkpoint -incremental $incremental_ref
        stage incremental_read
    }
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
    if {[info exists incremental_ref] && $incremental_ref ne ""} {
        report_incremental_reuse -file $out/incremental_reuse.rpt
    }
    # brief 33: the placed and routed result as text, for comparing builds (flow/result_hash.py); off unless FDA_RESULT_HASH=1
    if {[info exists ::env(FDA_RESULT_HASH)] && $::env(FDA_RESULT_HASH) eq "1"} {
        result_dump $out/result_dump.txt
        stage result_dump
    }

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
} else {
    # an earlier build of the same inputs reached the post_route reports: only the bitstream is left
    open_checkpoint $resume_dir/post_route.dcp
    set n [copy_reports $resume_dir $out [list {*}$synth_files *_place*.rpt timing_margin.txt post_route.dcp \
        timing_summary.rpt check_timing.rpt utilization.rpt utilization_hier.rpt methodology.rpt cdc.rpt drc.rpt \
        qor_assessment_route.rpt *_route.rpt *_route.txt timing_worst_*.rpt power.rpt io.rpt xprobe.json \
        result_dump.txt incremental_reuse.rpt]]
    puts "FLOW-RESUMED from $resume_dir/post_route.dcp ($n files copied)"
    stage resumed_route
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
