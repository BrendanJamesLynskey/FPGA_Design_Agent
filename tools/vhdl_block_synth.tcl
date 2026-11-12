# Brief 55: out-of-context synthesis of one block (SystemVerilog/Verilog or VHDL), with the reports the comparison reads.
#   vivado -mode batch -source tools/vhdl_block_synth.tcl -tclargs <flow dir> <top> <out dir> <xdc|-> <source> [<source> ...]
# VHDL (.vhd) is read with read_vhdl -vhdl2008, the rest with read_verilog -sv. Writes utilization.rpt, timing.rpt, and for a
# design with two clocks the brief 16 CDC reports (cdc_synth.rpt, cdc_paths_synth.rpt) that flow/cdc_structure.py grades.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set flow_dir [lindex $argv 0]
set top      [lindex $argv 1]
set out      [lindex $argv 2]
set xdc      [lindex $argv 3]
set srcs     [lrange $argv 4 end]
file mkdir $out
foreach f $srcs {
    if {[string match -nocase *.vhd $f]} { read_vhdl -vhdl2008 $f } else { read_verilog -sv $f }
}
if {$xdc ne "-"} { foreach x [split $xdc ,] { read_xdc -unmanaged $x } }
synth_design -top $top -part xc7a100tcsg324-1 -mode out_of_context
source $flow_dir/xpm_cdc.tcl
apply_xpm_cdc_constraints
report_utilization -file $out/utilization.rpt
report_timing_summary -file $out/timing.rpt
if {[llength [get_clocks -quiet]] > 1} {
    report_cdc -details -file $out/cdc_synth.rpt
    source $flow_dir/cdc_paths.tcl
    cdc_dump_paths $out/cdc_paths_synth.rpt
}
set f [open $out/summary.txt w]
puts $f "vivado [version -short]"
puts $f "lut [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]"
puts $f "ff [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]"
puts $f "lutram [llength [get_cells -hier -filter {REF_NAME =~ RAM*}]]"
puts $f "bram [llength [get_cells -hier -filter {REF_NAME =~ RAMB*}]]"
set p [lindex [get_timing_paths -max_paths 1 -nworst 1 -setup] 0]
if {$p ne ""} { puts $f "wns_ns [get_property SLACK $p]" }
close $f
