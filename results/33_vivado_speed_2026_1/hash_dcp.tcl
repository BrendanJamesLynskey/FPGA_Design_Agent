# hash_dcp.tcl (brief 33): open each saved post_route.dcp and write its result dump next to it (flow/result_hash.tcl).
#   vivado -mode batch -source hash_dcp.tcl -tclargs <a.dcp> [<b.dcp> ...]   -> <a>.dump.txt ...
# Used for the CDC rig, whose builds ran without FDA_RESULT_HASH so that their time and memory are the build's own.
set_param general.maxThreads 1
source [file join [file dirname [file normalize [info script]]] .. .. flow result_hash.tcl]
foreach dcp $argv {
    set t0 [clock milliseconds]
    open_checkpoint $dcp
    result_dump [file rootname $dcp].dump.txt
    close_design
    puts "HASH-DCP $dcp dumped in [expr {([clock milliseconds] - $t0) / 1000.0}] s"
}
