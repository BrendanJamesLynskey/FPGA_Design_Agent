# ooc.tcl (brief 101): out-of-context synthesis or EDIF import, placement and routing of one block per job, one Vivado session.
#   vivado -mode batch -source ooc.tcl -tclargs <jobs.tcl>
# <jobs.tcl> sets ooc(part) and ooc(jobs), a list of {name top wd clock_ns kind sources}.
# kind: edif                     read_edif sources (a Yosys netlist), link_design -mode out_of_context
#       rtl:<directive>[:retime] read_verilog -sv sources, synth_design -mode out_of_context -directive <directive> [-retiming]
# Both kinds then run the same opt_design, place_design and route_design with default directives, the same clock
# constraint (period on port clk, read_xdc -mode out_of_context for rtl; the same file after link_design for edif), and
# write utilisation, the timing summary and the single worst setup path (its "Logic Levels" line).
# A failing job writes <wd>/error.txt and the next job runs. Same thread limits as flow/ipchar.tcl.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
source [lindex $argv 0]
foreach job $ooc(jobs) {
    lassign $job name top wd clock_ns kind sources
    file mkdir $wd
    set t0 [clock seconds]
    if {[catch {
        set f [open $wd/clock.xdc w]
        puts $f "create_clock -period $clock_ns -name clk \[get_ports clk\]"
        close $f
        if {$kind eq "edif"} {
            # non-project mode; no -top (link_design -top fails with "Project 1-68" on an EDIF read this way; the EDIF has a single top)
            foreach s $sources { read_edif $s }
            link_design -part $ooc(part) -mode out_of_context
            read_xdc -mode out_of_context $wd/clock.xdc
        } else {
            create_project -in_memory -part $ooc(part)
            lassign [split $kind :] k directive retime
            foreach s $sources { if {[string match *.v $s]} { read_verilog $s } else { read_verilog -sv $s } }
            read_xdc -mode out_of_context $wd/clock.xdc
            set args [list -top $top -part $ooc(part) -mode out_of_context -directive $directive]
            if {$retime eq "retime"} { lappend args -retiming }
            synth_design {*}$args
        }
        opt_design
        place_design
        route_design
        report_utilization -file $wd/utilization.rpt
        report_timing_summary -max_paths 3 -file $wd/timing_summary.rpt
        report_timing -max_paths 1 -setup -file $wd/timing_worst.rpt
        set f [open $wd/done.txt w]; puts $f [expr {[clock seconds] - $t0}]; close $f
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "ooc: $name failed: $err"
    }
    catch {close_project -quiet}
    catch {close_design -quiet}
    puts "ooc: $name finished in [expr {[clock seconds] - $t0}] s"
}
