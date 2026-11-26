# one Vivado session: for each checkpoint, write the report kinds brief 204a parses (fixtures + corpus hit counts)
set_param general.maxThreads 1
proc rep {out name cmd} {
    set t0 [clock milliseconds]
    if {[catch {uplevel #0 $cmd} err]} {
        set f [open $out/$name.not_run.txt w]; puts $f "$name not run: $err"; close $f
    }
    puts "FDA204A $name [expr {[clock milliseconds] - $t0}] ms"
}
foreach {tag dcp stage} $argv {
    set out /home/brendan/Claude_sandbox/_worktrees/204a-report-gates/build/fixture_run/$tag
    file mkdir $out
    open_checkpoint $dcp
    rep $out logic_levels   "report_design_analysis -logic_level_distribution -logic_level_dist_paths 5000 -file $out/logic_levels.rpt"
    rep $out clock_util     "report_clock_utilization -file $out/clock_utilization.rpt"
    rep $out clock_networks "report_clock_networks -file $out/clock_networks.rpt"
    rep $out control_sets   "report_control_sets -verbose -file $out/control_sets.rpt"
    rep $out ip_status      "report_ip_status -file $out/ip_status.rpt"
    rep $out timing_nonet   "report_timing -max_paths 3 -file $out/timing_paths.rpt"
    if {$stage eq "route"} {
        rep $out congestion "report_design_analysis -congestion -file $out/congestion.rpt"
        rep $out complexity "report_design_analysis -complexity -file $out/complexity.rpt"
    }
    rep $out utilization    "report_utilization -file $out/utilization.rpt"
    close_design
}
puts "FDA204A-DONE"
