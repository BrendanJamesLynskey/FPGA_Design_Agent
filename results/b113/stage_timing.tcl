# Brief 113: the ML stage's in-context post-route timing at the core clock. Opens the post-route checkpoint of build rm_gp_ml and writes, for each part of the stage, the worst path ending in it (setup slack, data path
# delay, logic levels, start and end point) to stage_timing.json, plus the stage's resource use by hierarchy. usage: vivado -mode batch -source stage_timing.tcl -tclargs <post_route.dcp> <out dir>
set dcp [lindex $argv 0]
set out [lindex $argv 1]
open_checkpoint $dcp
file mkdir $out
set fh [open [file join $out stage_timing.json] w]
puts $fh "\{"
set groups {
  {state_to_stage1      *u_ml/s1_*}
  {stage1_to_features   *u_ml/feat_r*}
  {features_to_class    *u_ml/u_gbt/out_cls*}
  {apply_state          *u_ml/p_*}
  {apply_book           *u_ml/bpx* *u_ml/bsz* *u_ml/apx* *u_ml/asz*}
  {apply_windows        *u_ml/ofi_*  *u_ml/tr_*}
  {observe_pending      *u_ml/pt* *u_ml/ps* *u_ml/ppx* *u_ml/psz* *u_ml/pv*}
  {decision_fire        *u_td/fire* *u_td/o_price* *u_td/o_inst* *u_td/fired_this*}
  {class_to_fire        *u_td/o_seq*}
}
set first 1
foreach g $groups {
  set name [lindex $g 0]
  set cells {}
  foreach pat [lrange $g 1 end] { set cells [concat $cells [get_cells -quiet -hier -filter "NAME =~ $pat"]] }
  if {[llength $cells] == 0} { if {!$first} {puts $fh ","}; puts $fh "  \"$name\": \{\"error\": \"no cells\"\}"; set first 0; continue }
  set p [get_timing_paths -quiet -max_paths 1 -setup -to [get_pins -quiet -of_objects $cells -filter {IS_ENABLE==0 && DIRECTION==IN && REF_PIN_NAME==D}]]
  if {!$first} {puts $fh ","}; set first 0
  if {[llength $p] == 0} { puts $fh "  \"$name\": \{\"error\": \"no path\"\}"; continue }
  puts $fh [format "  \"%s\": \{\"slack_ns\": %s, \"data_path_delay_ns\": %s, \"logic_levels\": %s, \"start\": \"%s\", \"end\": \"%s\", \"endpoints\": %d\}" $name [get_property SLACK $p] [get_property DATAPATH_DELAY $p] [get_property LOGIC_LEVELS $p] [get_property STARTPOINT_PIN $p] [get_property ENDPOINT_PIN $p] [llength $cells]]
}
puts $fh "\}"
close $fh
report_timing_summary -file [file join $out stage_timing_summary.txt] -max_paths 5
report_utilization -hierarchical -hierarchical_depth 6 -file [file join $out utilization_hier.txt]
close_project
