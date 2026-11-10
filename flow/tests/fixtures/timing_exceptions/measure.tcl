# measure.tcl: one timing-exception fixture (brief 20), out-of-context on xc7a100tcsg324-1, Vivado 2025.2.
#   vivado -mode batch -source measure.tcl -tclargs <flow dir> <fixture dir> <name> <out dir> <impl 0|1>
# Reads xdc/<name>.clocks.xdc then xdc/<name>.xdc (the exceptions), synthesises, and writes the reports the exception
# gate reads (flow/gates.py: exceptions_*.rpt, methodology, timing summary), then re-times with the clocks only
# (reset_timing + the clocks file) so each report exists with and without the exception (*_noexc.rpt).
set_param general.maxThreads 1
set_param synth.maxThreads 1
lassign $argv flow_dir fx_dir name out impl
file mkdir $out
read_verilog -sv $fx_dir/rtl/$name.sv
read_xdc $fx_dir/xdc/$name.clocks.xdc
read_xdc $fx_dir/xdc/$name.xdc
synth_design -top $name -part xc7a100tcsg324-1 -mode out_of_context
source $flow_dir/xpm_cdc.tcl
apply_xpm_cdc_constraints
write_checkpoint -force $out/post_synth.dcp
source $flow_dir/mcp_paths.tcl
proc reports {out sfx} {
    mcp_dump_paths $out/mcp_paths_$sfx.txt
    report_timing_summary -max_paths 5 -file $out/timing_summary_$sfx.rpt
    report_methodology -file $out/methodology_$sfx.rpt
    report_exceptions -file $out/exceptions_$sfx.rpt
    report_exceptions -ignored -file $out/exceptions_ignored_$sfx.rpt
    report_exceptions -coverage -file $out/exceptions_coverage_$sfx.rpt
    report_timing -delay_type max -max_paths 3 -file $out/timing_setup_$sfx.rpt
    report_timing -delay_type min -max_paths 3 -file $out/timing_hold_$sfx.rpt
    report_clock_interaction -delay_type min_max -file $out/clock_interaction_$sfx.rpt
}
reports $out synth
report_cdc -details -file $out/cdc_synth.rpt
source $flow_dir/cdc_paths.tcl
cdc_dump_paths $out/cdc_paths_synth.rpt
report_utilization -file $out/utilization_synth.rpt
report_clock_utilization -file $out/clock_utilization_synth.rpt
if {$impl} {
    opt_design
    place_design
    route_design
    reports $out route
    report_utilization -file $out/utilization_route.rpt
}
# the same netlist re-timed without the exception file
reset_timing
read_xdc $fx_dir/xdc/$name.clocks.xdc
report_timing_summary -max_paths 5 -file $out/timing_summary_noexc.rpt
report_timing -delay_type max -max_paths 3 -file $out/timing_setup_noexc.rpt
report_timing -delay_type min -max_paths 3 -file $out/timing_hold_noexc.rpt
report_methodology -file $out/methodology_noexc.rpt
puts "MEASURE-DONE $name"
