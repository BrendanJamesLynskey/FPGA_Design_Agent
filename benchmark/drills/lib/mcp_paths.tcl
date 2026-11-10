# mcp_paths.tcl (brief 20 drills): flow/mcp_paths.tcl on a checkpoint.
#   vivado -mode batch -source mcp_paths.tcl -tclargs <checkpoint.dcp> <out.txt>
set_param general.maxThreads 1
lassign $argv dcp outf
open_checkpoint $dcp
source [file normalize [file join [file dirname [info script]] .. .. .. flow mcp_paths.tcl]]
mcp_dump_paths $outf
