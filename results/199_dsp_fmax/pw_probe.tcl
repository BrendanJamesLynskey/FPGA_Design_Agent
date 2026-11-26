# pw_probe.tcl (brief 199): is the DSP Fmax of brief 185 bounded by the pulse-width / minimum-period checks? One routed out-of-context run per
# (part, clock, wrapper); writes the checkpoint and report_pulse_width / report_timing_summary / report_clock_utilization, and prints the part's speed grade.
#   vivado -mode batch -source pw_probe.tcl -tclargs <outdir> <rtl185dir> <rtl199dir>
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
lassign $argv out rtl185 rtl199
file mkdir $out
foreach job {
    {a7_bare   xc7a100tcsg324-1     1.8 dsp_mul_pipe_ooc      clk}
    {a7_bufg   xc7a100tcsg324-1     1.8 dsp_mul_pipe_ooc_bufg clk_in}
    {k26_bare  xck26-sfvc784-2LV-c  1.0 dsp_mul_pipe_ooc      clk}
    {k26_bufg  xck26-sfvc784-2LV-c  1.0 dsp_mul_pipe_ooc_bufg clk_in}
    {k26_bufg13 xck26-sfvc784-2LV-c 1.3 dsp_mul_pipe_ooc_bufg clk_in}
} {
    lassign $job name part clk top port
    set wd $out/$name
    file mkdir $wd
    puts "PW-START $name"
    if {[catch {
        create_project -in_memory -part $part
        read_verilog -sv [list $rtl185/dsp_mul_pipe.sv $rtl185/dsp_mul_pipe_ooc.sv $rtl199/dsp_mul_pipe_ooc_bufg.sv]
        set f [open $wd/clock.xdc w]; puts $f "create_clock -period $clk -name clk \[get_ports $port\]"; close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        synth_design -top $top -part $part -mode out_of_context
        opt_design; place_design; route_design
        write_checkpoint -force $wd/routed.dcp
        report_timing_summary -max_paths 3 -file $wd/timing_summary.rpt
        report_pulse_width -file $wd/pulse_width.rpt
        report_pulse_width -all_violators -file $wd/pulse_width_violators.rpt
        report_timing -delay_type max -max_paths 1 -file $wd/timing_worst_setup.rpt
        set f [open $wd/info.txt w]
        puts $f "part $part speed=[get_property SPEED [get_parts $part]]"
        puts $f "wns [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]"
        close $f
    } err]} { puts "PW: $name failed: $err"; set f [open $wd/error.txt w]; puts $f $err; close $f }
    close_project -quiet
    puts "PW-END $name"
}
