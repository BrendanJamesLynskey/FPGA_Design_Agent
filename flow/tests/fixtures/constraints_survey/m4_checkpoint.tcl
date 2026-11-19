# m4_checkpoint.tcl (brief 105, M4): read-only look at a routed checkpoint's synchronisers. Opens the checkpoint, writes the CDC path dump
# (flow/cdc_paths.tcl, for flow/cdc_structure.py), report_synchronizer_mtbf, the count of ASYNC_REG flops, and the worst
# Missing-property rows. Changes nothing, writes only into <out>.
#   vivado -mode batch -source m4_checkpoint.tcl -tclargs <flow dir> <checkpoint.dcp> <out dir>
set_param general.maxThreads 1
lassign $argv flow_dir dcp out
file mkdir $out
open_checkpoint $dcp
source $flow_dir/cdc_paths.tcl
cdc_dump_paths $out/cdc_paths.rpt
report_cdc -details -file $out/cdc.rpt
catch {report_synchronizer_mtbf -file $out/mtbf.rpt}
set m [open $out/metrics.txt w]
puts $m "version [version -short]"
puts $m "part [get_property PART [current_design]]"
puts $m "ff_cells [llength [get_cells -hierarchical -quiet -filter {REF_NAME =~ FD*}]]"
puts $m "async_reg_ff_cells [llength [get_cells -hierarchical -quiet -filter {REF_NAME =~ FD* && ASYNC_REG == TRUE}]]"
puts $m "xpm_cdc_cells [llength [get_cells -hierarchical -quiet -filter {ORIG_REF_NAME =~ xpm_cdc_* || REF_NAME =~ xpm_cdc_*}]]"
puts $m "clocks [llength [get_clocks]]"
close $m
puts "M4-DONE $out"
