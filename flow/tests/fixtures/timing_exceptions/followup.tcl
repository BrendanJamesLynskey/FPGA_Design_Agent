# followup.tcl (brief 20): questions the first pass left open, on the fixtures' post-synthesis checkpoints.
#   vivado -mode batch -source followup.tcl -tclargs <out dir> <drills lib dir>
# 1. Does TIMING-46 (multicycle with tied CE) appear after implementation where it did not after synthesis (E3, E10b, E10c)?
# 2. The clk0 -> clk1 crossing's requirement under E8 (-end) and E8b (-start), setup and hold.
# 3. The multicycle dump (benchmark/drills/lib/mcp_paths.tcl) on E10, E10b, E10c, for the drill grader's tests.
set_param general.maxThreads 1
lassign $argv out lib
foreach n {tex_e3 tex_e10b tex_e10c} {
    open_checkpoint $out/$n/post_synth.dcp
    opt_design
    place_design
    report_methodology -file $out/$n/methodology_place.rpt
    close_design
}
foreach n {tex_e8 tex_e8b} {
    open_checkpoint $out/$n/post_synth.dcp
    report_timing -from [get_cells {s_reg[*]}] -to [get_cells {acc_reg[*]}] -delay_type max -file $out/$n/crossing_setup.rpt
    report_timing -from [get_cells {s_reg[*]}] -to [get_cells {acc_reg[*]}] -delay_type min -file $out/$n/crossing_hold.rpt
    close_design
}
foreach n {tex_e10 tex_e10b tex_e10c} {
    set argv [list $out/$n/post_synth.dcp $out/$n/mcp_paths.txt]
    source $lib/mcp_paths.tcl
    close_design
}
