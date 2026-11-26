# ooc_compare.tcl (brief 171): out-of-context Vivado builds of hand-written SV vs Hardcaml-generated Verilog at the same parameter points.
#   vivado -mode batch -source tools/hardcaml/ooc_compare.tcl -tclargs <jobs.tcl>
# <jobs.tcl> sets jobs: a list of {name part top clock_ns generics sources workdir}. One project per job; clock on port aclk;
# synth (out of context), opt, place, route; utilisation, timing and hierarchical utilisation reports into the workdir.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
source [lindex $argv 0]
foreach job $jobs {
    lassign $job name part top clock_ns generics srcs wd
    file mkdir $wd
    set t0 [clock seconds]
    if {[catch {
        create_project -in_memory -part $part
        read_verilog -sv $srcs
        set f [open $wd/clock.xdc w]
        puts $f "create_clock -period $clock_ns -name aclk \[get_ports aclk\]"
        close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        set g {}
        foreach {k v} $generics { lappend g "$k=$v" }
        synth_design -top $top -part $part -mode out_of_context -generic $g
        report_utilization -file $wd/utilization_synth.rpt
        opt_design
        place_design
        route_design
        report_utilization -file $wd/utilization.rpt
        report_utilization -hierarchical -file $wd/utilization_hier.rpt
        report_timing_summary -max_paths 3 -file $wd/timing_summary.rpt
        report_timing -delay_type max -max_paths 1 -file $wd/timing_worst_setup.rpt
        set f [open $wd/done.txt w]; puts $f [expr {[clock seconds] - $t0}]; close $f
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "ooc_compare: $name failed: $err"
    }
    catch {close_project -quiet}
    puts "ooc_compare: $name finished in [expr {[clock seconds] - $t0}] s"
}
