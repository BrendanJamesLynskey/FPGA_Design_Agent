# usage: vivado -mode batch -source place_hold_groups.tcl -tclargs <post_place.dcp> <tag>   (FDA_INSPECT_CKPTS=1 makes the build write post_place.dcp)
# worst hold slack per launch/capture clock pair and the worst hold path, from a placed checkpoint
set dcp [lindex $argv 0]; set tag [lindex $argv 1]
open_checkpoint $dcp
report_timing -delay_type min -max_paths 3 -nworst 1 -file ${tag}_worst_hold.rpt
set paths [get_timing_paths -delay_type min -max_paths 400 -slack_lesser_than -0.0]
set n 0
array set cnt {}
array set worst {}
foreach p $paths {
  set k "[get_property STARTPOINT_CLOCK $p]->[get_property ENDPOINT_CLOCK $p]"
  if {![info exists cnt($k)]} { set cnt($k) 0; set worst($k) 1e9 }
  incr cnt($k)
  set s [get_property SLACK $p]
  if {$s < $worst($k)} { set worst($k) $s }
}
foreach k [array names cnt] { puts "HOLDGROUP $k n=$cnt($k) worst=$worst($k)" }
