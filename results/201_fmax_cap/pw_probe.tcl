# pw_probe.tcl (brief 201): the clock-buffer minimum period of three more parts, from report_pulse_width on a routed out-of-context run with the clock
# through a BUFG (the brief-199 wrapper). One run per part; prints the part's speed grade.
#   vivado -mode batch -source pw_probe.tcl -tclargs <outdir> <rtl185dir> <rtl199dir>
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
lassign $argv out rtl185 rtl199
file mkdir $out
foreach job {
    {a35_bufg   xc7a35tcpg236-1       1.8}
    {z7020_bufg xc7z020clg484-1       1.8}
    {zu3eg_bufg xczu3eg-sfvc784-2-e   1.0}
} {
    lassign $job name part clk
    set wd $out/$name
    file mkdir $wd
    puts "PW-START $name"
    if {[catch {
        create_project -in_memory -part $part
        read_verilog -sv [list $rtl185/dsp_mul_pipe.sv $rtl185/dsp_mul_pipe_ooc.sv $rtl199/dsp_mul_pipe_ooc_bufg.sv]
        set f [open $wd/clock.xdc w]; puts $f "create_clock -period $clk -name clk \[get_ports clk_in\]"; close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        synth_design -top dsp_mul_pipe_ooc_bufg -part $part -mode out_of_context
        opt_design; place_design; route_design
        report_timing_summary -max_paths 3 -file $wd/timing_summary.rpt
        report_pulse_width -file $wd/pulse_width.rpt
        report_pulse_width -all_violators -file $wd/pulse_width_violators.rpt
        set f [open $wd/info.txt w]
        puts $f "part $part speed=[get_property SPEED [get_parts $part]]"
        puts $f "wns [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]"
        close $f
    } err]} { puts "PW: $name failed: $err"; set f [open $wd/error.txt w]; puts $f $err; close $f }
    close_project -quiet
    puts "PW-END $name"
}
