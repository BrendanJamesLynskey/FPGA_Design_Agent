# ooc.tcl: out-of-context synthesis, placement and routing of tcp_fast, one Vivado batch session (brief 119).
#   vivado -mode batch -source ooc.tcl -tclargs <jobs.tcl>
# <jobs.tcl> (written by ooc.py) sets ooc(part), ooc(top) and ooc(jobs), a list of {name workdir clock_ns sources parameters}.
# Each job: ooc_wrap (input registers, as the producer would have) around tcp_fast, a clock on port clk, synth_design -mode out_of_context,
# opt, place, route, then utilisation (flat and by hierarchy) and timing reports. A failing job writes <workdir>/error.txt and the next job runs.
# Same settings as flow/ipchar.tcl and the 87 builds: one thread.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
source [lindex $argv 0]
foreach job $ooc(jobs) {
    lassign $job name wd clock_ns sources generics
    file mkdir $wd
    set t0 [clock seconds]
    if {[catch {
        create_project -in_memory -part $ooc(part)
        foreach s $sources { read_verilog -sv $s }
        set f [open $wd/clock.xdc w]
        puts $f "create_clock -period $clock_ns -name clk \[get_ports clk\]"
        close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        set gl {}
        foreach {k v} $generics { lappend gl -generic $k=$v }
        synth_design -top $ooc(top) -part $ooc(part) -mode out_of_context {*}$gl
        opt_design
        place_design
        route_design
        report_utilization -file $wd/utilization.rpt
        report_utilization -hierarchical -hierarchical_depth 3 -file $wd/utilization_hier.rpt
        report_timing_summary -max_paths 5 -file $wd/timing_summary.rpt
        report_timing -max_paths 3 -nworst 1 -path_type full -file $wd/worst_paths.rpt
        report_clock_utilization -file $wd/clock_utilization.rpt
        set f [open $wd/done.txt w]; puts $f [expr {[clock seconds] - $t0}]; close $f
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "ooc: $name failed: $err"
    }
    close_project -quiet
    puts "ooc: $name finished in [expr {[clock seconds] - $t0}] s"
}
