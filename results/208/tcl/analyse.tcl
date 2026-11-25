# Brief 208: second-pass measurements on the routed checkpoints of run_jobs.tcl (one Vivado session).
#   vivado -mode batch -source analyse.tcl -tclargs <build root> <out file>
# d: for each cascade design, every BUFGCTRL's site and, for each MMCM output clock, the source clock delay (SCD) of the
#    same-clock path on the mux fanout: the insertion delay through the tree from that input.
# f: on the BUFGCE power design, whether report_power responds to activity set on the enable or on the gated clock net.
set_param general.maxThreads 1
lassign $argv root outf
set fh [open $outf w]
proc best_dcp {dir} {
  # the routed checkpoint if the arm was routed, else the placed one
  foreach f {post_route.dcp post_place.dcp} { if {[file exists $dir/$f]} { return $dir/$f } }
  return ""
}
foreach dir [lsort [glob -nocomplain -type d $root/*/*_bal4 $root/*/*_bal3 $root/*/*_chain7 $root/*/*_chain9]] {
  set dcp [best_dcp $dir]; if {$dcp eq ""} continue
  set name "[file tail $dir]:[file rootname [file tail $dcp]]"
  open_checkpoint $dcp
  foreach b [lsort [get_cells -hier -filter {REF_NAME == BUFGCTRL}]] {
    puts $fh [join [list D_SITE $name $b [get_property LOC $b]] "\t"]
  }
  for {set k 0} {$k < 7} {incr k} {
    set c [get_clocks -quiet -of_objects [get_pins -hier -filter "NAME =~ *u_mmcm/CLKOUT$k"]]
    if {$c eq ""} continue
    set p [get_timing_paths -quiet -from $c -to $c -max_paths 1]
    if {$p eq ""} { puts $fh [join [list D_DELAY $name CLKOUT$k $c none] "\t"]; continue }
    set s [report_timing -of_objects $p -return_string]
    set scd "-"; set dcd "-"
    regexp {Source Clock Delay\s+\(SCD\):\s+([-0-9.]+)ns} $s -> scd
    regexp {Destination Clock Delay \(DCD\):\s+([-0-9.]+)ns} $s -> dcd
    puts $fh [join [list D_DELAY $name CLKOUT$k $c $scd $dcd] "\t"]
  }
  close_design
}
foreach dir [lsort [glob -nocomplain -type d $root/*/*_pwr_bufgce]] {
  set dcp [best_dcp $dir]; if {$dcp eq ""} continue
  set name "[file tail $dir]:[file rootname [file tail $dcp]]"
  open_checkpoint $dcp
  set g [get_nets -of_objects [get_pins -hier -filter {NAME =~ *u_bufgce/O}]]
  set en [get_nets -hier -filter {NAME =~ *en_r}]
  foreach p {0.1 0.9} {
    set_switching_activity -static_probability $p -toggle_rate 2 $en
    set r [report_power -return_string]
    regexp {Dynamic \(W\)\s+\|\s+([0-9.]+)} $r -> dyn
    puts $fh [join [list F_POWER $name en_prob=$p dyn=$dyn] "\t"]
  }
  if {[catch {set_switching_activity -static_probability 0.1 -toggle_rate 20 $g} err]} {
    puts $fh [join [list F_POWER $name gated_clock_net_activity refused [string map {"\n" " "} $err]] "\t"]
  } else {
    set r [report_power -return_string]
    regexp {Dynamic \(W\)\s+\|\s+([0-9.]+)} $r -> dyn
    puts $fh [join [list F_POWER $name gated_clock_net_activity_0.1_20 dyn=$dyn] "\t"]
  }
  close_design
}
close $fh
