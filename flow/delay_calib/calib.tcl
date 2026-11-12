# Out-of-context build of the delay-model calibration design (dm_calib.sv) and one report per block.
#   vivado -mode batch -source flow/delay_calib/calib.tcl -tclargs <out_dir> [part]
# Thread limits as flow/build.tcl (house rules): FDA_VIVADO_THREADS (default 2), synth.maxThreads, chipscope.maxJobs 1.
set out  [lindex $argv 0]
set part [expr {[llength $argv] > 1 ? [lindex $argv 1] : "xc7a100tcsg324-1"}]
set thr  [expr {[info exists ::env(FDA_VIVADO_THREADS)] ? $::env(FDA_VIVADO_THREADS) : 2}]
file mkdir $out
set_param general.maxThreads $thr
catch {set_param synth.maxThreads $thr}
catch {set_param chipscope.maxJobs 1}
read_verilog -sv [file join [file dirname [info script]] dm_calib.sv]
synth_design -top dm_calib -part $part -mode out_of_context
create_clock -name clk -period 10.000 [get_ports clk]
report_utilization -hierarchical -file $out/utilization_hier_synth.rpt
opt_design
place_design
route_design
report_utilization -hierarchical -file $out/utilization_hier.rpt
report_timing_summary -max_paths 5 -file $out/timing_summary.rpt
foreach blk {u_add16 u_add32 u_add64 u_cmp32 u_tab u_mux16 u_mul9_lut u_mul18_lut u_mul9_dsp0 u_mul18_dsp2 u_mul18_dsp3 u_bram0 u_bram1} {
    set ends [get_cells -hierarchical -filter "NAME =~ $blk/* && IS_SEQUENTIAL"]
    report_timing -delay_type max -to $ends -max_paths 8 -nworst 1 -unique_pins -file $out/path_$blk.rpt
}
set dsps  [get_cells -hierarchical -filter {REF_NAME =~ DSP48*}]
set rams  [get_cells -hierarchical -filter {REF_NAME =~ RAMB*}]
report_timing -delay_type max -from $dsps -max_paths 12 -nworst 1 -unique_pins -file $out/path_from_dsp.rpt
report_timing -delay_type max -from $rams -max_paths 12 -nworst 1 -unique_pins -file $out/path_from_bram.rpt
report_timing -delay_type max -from $dsps -to $dsps -max_paths 12 -nworst 1 -unique_pins -file $out/path_dsp_internal.rpt
foreach c $dsps { puts "FDA-DSP [get_property NAME $c] AREG=[get_property AREG $c] BREG=[get_property BREG $c] MREG=[get_property MREG $c] PREG=[get_property PREG $c]" }
foreach c $rams { puts "FDA-RAM [get_property NAME $c] DOA_REG=[get_property DOA_REG $c] DOB_REG=[get_property DOB_REG $c]" }
puts "CALIB_DONE $out"
