# ooc.tcl: out-of-context synthesis, placement and routing of each brief 93 subject, one Vivado batch session.
#   vivado -mode batch -source ooc.tcl -tclargs <jobs.tcl>
# The brief 87 script (designs/b87_ml_trading/ooc/ooc.tcl) plus, per job, an optional Tcl snippet run after routing
# (the 6th job element, with $wd set): the partial-evaluation blocks use it to report the worst early and late path.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
source [lindex $argv 0]
foreach job $ooc(jobs) {
    lassign $job name top wd clock_ns sources extra
    file mkdir $wd
    set t0 [clock seconds]
    if {[catch {
        create_project -in_memory -part $ooc(part)
        foreach s $sources { if {[string match *.v $s]} { read_verilog $s } else { read_verilog -sv $s } }
        set f [open $wd/clock.xdc w]
        puts $f "create_clock -period $clock_ns -name clk \[get_ports clk\]"
        close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        synth_design -top $top -part $ooc(part) -mode out_of_context
        opt_design
        place_design
        route_design
        report_utilization -file $wd/utilization.rpt
        report_timing_summary -max_paths 3 -file $wd/timing_summary.rpt
        if {$extra ne ""} { eval $extra }
        set f [open $wd/done.txt w]; puts $f [expr {[clock seconds] - $t0}]; close $f
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "ooc: $name failed: $err"
    }
    close_project -quiet
    puts "ooc: $name finished in [expr {[clock seconds] - $t0}] s"
}
