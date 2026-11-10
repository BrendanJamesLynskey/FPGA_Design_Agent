# xprobe_run.tcl: cross-probe a routed checkpoint (brief 18, section 3); see flow/xprobe.tcl.
#   vivado -mode batch -source flow/xprobe_run.tcl -tclargs <post_route.dcp> <out xprobe.json> [paths per group and kind]
set_param general.maxThreads 1
set flow_dir [file dirname [file normalize [info script]]]
source $flow_dir/xprobe.tcl
open_checkpoint [file normalize [lindex $argv 0]]
set n [expr {[llength $argv] > 2 ? [lindex $argv 2] : 5}]
xprobe_dump [file normalize [lindex $argv 1]] $n [file normalize [lindex $argv 0]]
