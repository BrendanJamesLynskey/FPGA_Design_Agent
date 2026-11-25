# vivado_ooc.tcl (brief 142): out-of-context Vivado runs for the benchmark set, one session, one thread.
#   vivado -mode batch -source vivado_ooc.tcl -tclargs <jobs.tcl>
# <jobs.tcl> (written by vivado_jobs.py) sets ooc(part) and ooc(jobs), a list of
#   {name top wd clock_ns kind stage sources generics ?part?}   (the part defaults to ooc(part))
# kind:  rtl         read_verilog -sv sources, synth_design -mode out_of_context [-generic ...]
#        edif        read_edif sources (a Yosys netlist), link_design -mode out_of_context
# stage: synth       stop after synthesis (RTL kinds) / after link_design (edif kinds): utilisation, worst path, primitive counts
#        impl        then opt_design, place_design, route_design (default directives): utilisation, timing summary, worst path
# A failing job writes <wd>/error.txt and the next job runs.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
source [lindex $argv 0]
foreach job $ooc(jobs) {
    lassign $job name top wd clock_ns kind stage sources generics jpart
    set part $ooc(part); if {$jpart ne ""} { set part $jpart }   ;# optional per-job part (a ninth field)
    file mkdir $wd
    set t0 [clock seconds]
    if {[catch {
        set f [open $wd/clock.xdc w]
        puts $f "create_clock -period $clock_ns -name clk \[get_ports clk\]"
        close $f
        if {$kind eq "edif"} {
            foreach s $sources { read_edif $s }
            link_design -part $part -mode out_of_context
            read_xdc -mode out_of_context $wd/clock.xdc
        } else {
            create_project -in_memory -part $part
            foreach s $sources { read_verilog -sv $s }
            read_xdc -mode out_of_context $wd/clock.xdc
            set args [list -top $top -part $part -mode out_of_context]
            foreach g $generics { lappend args -generic $g }
            synth_design {*}$args
        }
        report_utilization -file $wd/utilization_$stage.rpt
        report_timing -max_paths 1 -setup -file $wd/timing_worst_$stage.rpt
        if {$stage eq "impl"} {
            opt_design
            place_design
            route_design
            report_utilization -file $wd/utilization.rpt
            report_timing_summary -max_paths 3 -file $wd/timing_summary.rpt
            report_timing -max_paths 1 -setup -file $wd/timing_worst.rpt
        }
        set f [open $wd/done.txt w]; puts $f [expr {[clock seconds] - $t0}]; close $f
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "ooc: $name failed: $err"
    }
    catch {close_project -quiet}
    catch {close_design -quiet}
    puts "ooc: $name finished in [expr {[clock seconds] - $t0}] s"
}
