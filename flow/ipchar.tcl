# ipchar.tcl: out-of-context characterisation of ip_lib variants (brief 63A). Batch, no GUI, no project on disk.
#   vivado -mode batch -source flow/ipchar.tcl -tclargs <jobs.tcl>
# <jobs.tcl> (written by flow/ipchar.py) sets ipchar(part), ipchar(sources) and ipchar(jobs): a list of
#   {name top workdir clock_ns generics}
# where generics is a flat name/value list. For each job: synth_design -mode out_of_context, clock on port clk, then
# opt, place and route, and the utilisation, timing and vectorless power reports into the job's workdir. A failing job
# writes <workdir>/error.txt and the next job runs.
set_param general.maxThreads 1
set_param synth.maxThreads 1
source [lindex $argv 0]

foreach job $ipchar(jobs) {
    lassign $job name top wd clock_ns generics
    file mkdir $wd
    set t0 [clock seconds]
    if {[catch {
        create_project -in_memory -part $ipchar(part)
        read_verilog -sv $ipchar(sources)
        set f [open $wd/clock.xdc w]
        puts $f "create_clock -period $clock_ns -name clk \[get_ports clk\]"
        close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        set g {}
        foreach {k v} $generics { lappend g "$k=$v" }
        synth_design -top $top -part $ipchar(part) -mode out_of_context -generic $g
        report_utilization -file $wd/utilization_synth.rpt
        opt_design
        place_design
        route_design
        report_utilization -file $wd/utilization.rpt
        report_timing_summary -delay_type max -max_paths 3 -file $wd/timing_summary.rpt
        report_power -file $wd/power.rpt
        set f [open $wd/done.txt w]; puts $f [expr {[clock seconds] - $t0}]; close $f
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "ipchar: $name failed: $err"
    }
    close_project -quiet
    puts "ipchar: $name finished in [expr {[clock seconds] - $t0}] s"
}
