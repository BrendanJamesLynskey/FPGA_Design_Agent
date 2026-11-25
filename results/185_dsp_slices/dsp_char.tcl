# dsp_char.tcl (brief 185): out-of-context synthesis, placement and routing of DSP-slice experiments, one thread, no I/O constraints.
#   vivado -mode batch -source dsp_char.tcl -tclargs <jobs.tcl>
# <jobs.tcl> (written by run_dsp.py) sets dsc(part), dsc(sources) and dsc(jobs): a list of {name top workdir clock_ns generics}.
# Per job it writes into the workdir: utilization (synth and routed), timing (summary, worst setup, worst hold), the DSP cells' register
# properties after routing (dsp_cells.txt), the DSP-related lines of report_methodology and report_drc, and done.txt (seconds) or error.txt.
# The batch log carries DSC-START / DSC-END markers so that the synthesis "DSP Report" can be cut out per job.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
source [lindex $argv 0]

proc prop {c p} {
    if {[catch {set v [get_property $p $c]}]} { return "n/a" }
    return $v
}

foreach job $dsc(jobs) {
    lassign $job name top wd clock_ns generics
    file mkdir $wd
    set t0 [clock seconds]
    puts "DSC-START $name"
    if {[catch {
        create_project -in_memory -part $dsc(part)
        read_verilog -sv $dsc(sources)
        set f [open $wd/clock.xdc w]
        puts $f "create_clock -period $clock_ns -name clk \[get_ports clk\]"
        close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        set g {}
        foreach {k v} $generics { lappend g "$k=$v" }
        synth_design -top $top -part $dsc(part) -mode out_of_context -generic $g
        report_utilization -file $wd/utilization_synth.rpt
        opt_design
        place_design
        route_design
        report_utilization -file $wd/utilization.rpt
        report_timing_summary -max_paths 3 -file $wd/timing_summary.rpt
        report_timing -delay_type max -max_paths 1 -file $wd/timing_worst_setup.rpt
        report_timing -delay_type min -max_paths 1 -file $wd/timing_worst_hold.rpt
        report_methodology -file $wd/methodology.rpt
        report_drc -file $wd/drc.rpt
        set f [open $wd/dsp_cells.txt w]
        foreach c [lsort [get_cells -hier -filter {REF_NAME =~ DSP48*}]] {
            set line "$c [get_property REF_NAME $c]"
            foreach p {AREG BREG CREG DREG ADREG MREG PREG INMODEREG OPMODEREG ALUMODEREG CARRYINREG USE_MULT USE_SIMD USE_PATTERN_DETECT AUTORESET_PATDET SEL_PATTERN SEL_MASK PREADDINSEL AMULTSEL BMULTSEL} {
                set v [prop $c $p]
                if {$v ne "n/a"} { append line " $p=$v" }
            }
            puts $f $line
        }
        close $f
        set f [open $wd/done.txt w]; puts $f [expr {[clock seconds] - $t0}]; close $f
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "DSC: $name failed: $err"
    }
    close_project -quiet
    puts "DSC-END $name [expr {[clock seconds] - $t0}] s"
}
