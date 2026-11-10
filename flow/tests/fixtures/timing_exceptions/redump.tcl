# redump.tcl (brief 20): rewrite mcp_paths_synth.txt of every fixture from its post-synthesis checkpoint, so the dumps come
# from the committed flow/mcp_paths.tcl.   vivado -mode batch -source redump.tcl -tclargs <out dir> <flow dir> <fixture ...>
set_param general.maxThreads 1
set out [lindex $argv 0]
source [lindex $argv 1]/mcp_paths.tcl
foreach n [lrange $argv 2 end] {
    open_checkpoint $out/$n/post_synth.dcp
    mcp_dump_paths $out/$n/mcp_paths_synth.txt
    close_design
}
