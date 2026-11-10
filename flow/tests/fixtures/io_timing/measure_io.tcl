# measure_io.tcl: one I/O-timing fixture group (brief 20 part B), a full top on xc7a100tcsg324-1, Vivado 2025.2.
#   vivado -mode batch -source measure_io.tcl -tclargs <flow dir> <fixture dir> <top> <out dir> <generics> <variant> ...
# Synthesises rtl/<top>.sv with xdc/<top>.pins.xdc and the first variant's xdc/<variant>.xdc, places and routes it, then
# for each variant (the first as built, the others re-timed on the same routed netlist: reset_timing + read_xdc) writes
# into <out dir>/<variant>/ the reports flow/io_check.py reads (io_paths.txt, check_timing, timing summary, I/O paths,
# methodology, clocks). "VARIANT <name>" in the log separates each variant's XDC messages.
set_param general.maxThreads 1
set_param synth.maxThreads 1
lassign $argv flow_dir fx_dir top out generics
set variants [lrange $argv 5 end]
file mkdir $out
if {[info exists ::env(FDA_IO_REUSE)] && [file exists $out/post_route.dcp]} {
    # re-time an earlier routed build of the group (every variant then re-reads its XDC)
    open_checkpoint $out/post_route.dcp
    set reuse 1
} else {
    set reuse 0
    read_verilog -sv $fx_dir/rtl/$top.sv
    read_xdc $fx_dir/xdc/$top.pins.xdc
    puts "VARIANT [lindex $variants 0]"
    read_xdc $fx_dir/xdc/[lindex $variants 0].xdc
    set gen_args {}
    foreach g $generics { lappend gen_args -generic $g }
    synth_design -top $top -part xc7a100tcsg324-1 {*}$gen_args
    opt_design
    place_design
    phys_opt_design
    route_design
    write_checkpoint -force $out/post_route.dcp
}
source $flow_dir/io_paths.tcl
set first [expr {!$reuse}]
foreach v $variants {
    if {!$first} {
        puts "VARIANT $v"
        reset_timing
        read_xdc $fx_dir/xdc/$v.xdc
    }
    set first 0
    set o $out/$v
    file mkdir $o
    io_dump_paths $o/io_paths.txt
    report_timing_summary -max_paths 5 -report_unconstrained -file $o/timing_summary.rpt
    check_timing -verbose -file $o/check_timing.rpt
    report_timing -from [all_inputs] -delay_type min_max -max_paths 4 -nworst 1 -file $o/timing_inputs.rpt
    report_timing -to [all_outputs] -delay_type min_max -max_paths 4 -nworst 1 -file $o/timing_outputs.rpt
    # every launch/capture edge pair of the first data input (DDR: both clock edges; -add_delay or not)
    report_timing -from [all_inputs] -delay_type min_max -max_paths 40 -nworst 8 -file $o/timing_inputs_edges.rpt
    report_timing -delay_type max -max_paths 1 -file $o/timing_worst_setup.rpt
    report_timing -delay_type min -max_paths 1 -file $o/timing_worst_hold.rpt
    report_methodology -file $o/methodology.rpt
    report_clocks -file $o/clocks.rpt
    report_clock_interaction -delay_type min_max -file $o/clock_interaction.rpt
    report_exceptions -ignored -file $o/exceptions_ignored.rpt
    puts "MEASURED $v"
}
report_utilization -file $out/utilization.rpt
report_clock_utilization -file $out/clock_utilization.rpt
puts "MEASURE-DONE $top"
