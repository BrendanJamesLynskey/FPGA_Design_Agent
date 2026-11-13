# core_ooc.tcl (brief 64A+): out-of-context build of the BRV32P SoC, as copied and patched by run_bench.py, to measure
# what a custom-instruction unit costs the core in logic and clock rate. Same flow for the baseline and each variant:
#   vivado -mode batch -source hwsw/cfu_core/core_ooc.tcl -tclargs <run dir> <part> <period_ns>
# The run dir holds rtl/ (and rtl/cfu/ with the generated unit and the library entry's RTL for a patched core). Reports
# and summary.txt go to <run dir>/vivado/. One thread, as the house rules require.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
lassign $argv rd part period
set out $rd/vivado
file mkdir $out
cd $rd
read_verilog [glob rtl/core/*.v rtl/cache/*.v rtl/bus/*.v rtl/periph/*.v] rtl/brv32p_soc.v
set sv [glob -nocomplain rtl/cfu/*.sv]
if {[llength $sv]} { read_verilog -sv $sv }
set_property include_dirs [list rtl/pkg rtl/core rtl/cfu] [current_fileset]
synth_design -top brv32p_soc -part $part -mode out_of_context
create_clock -name clk -period $period [get_ports clk]
opt_design
place_design
route_design
report_utilization -file $out/utilization.rpt
report_utilization -hierarchical -file $out/utilization_hier.rpt
report_timing_summary -max_paths 5 -file $out/timing_summary.rpt
report_timing -max_paths 1 -nworst 1 -path_type full -file $out/critical_path.rpt
set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set fh [open $out/summary.txt w]
puts $fh "part $part"
puts $fh "clock_period_ns $period"
puts $fh "wns_ns $wns"
puts $fh "fmax_mhz [format %.1f [expr {1000.0 / ($period - $wns)}]]"
puts $fh "lut [llength [get_cells -hierarchical -filter {PRIMITIVE_GROUP == LUT}]]"
puts $fh "ff [llength [get_cells -hierarchical -filter {PRIMITIVE_GROUP == FLOP_LATCH}]]"
puts $fh "dsp [llength [get_cells -hierarchical -filter {PRIMITIVE_GROUP == ARITHMETIC}]]"
puts $fh "cfu_lut [llength [get_cells -hierarchical -quiet -filter {PRIMITIVE_GROUP == LUT && NAME =~ *u_cfu/*}]]"
puts $fh "cfu_ff [llength [get_cells -hierarchical -quiet -filter {PRIMITIVE_GROUP == FLOP_LATCH && NAME =~ *u_cfu/*}]]"
close $fh
puts "core_ooc: done"
