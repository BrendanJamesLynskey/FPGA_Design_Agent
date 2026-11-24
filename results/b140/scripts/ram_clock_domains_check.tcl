# usage: vivado -mode batch -source ram_clock_domains_check.tcl -tclargs <post_synth.dcp>
# the check the flow makes after implement_debug_core (flow/build.tcl), then report_drc: with CLOCK_DOMAINS COMMON on the ILA trace RAMs AVAL-244/-245 are gone
open_checkpoint [lindex $argv 0]
set n_cd 0
foreach core [get_debug_cores -quiet] {
  puts "CORE $core"
  foreach r [get_cells -quiet -hierarchical -filter "IS_PRIMITIVE && REF_NAME =~ RAMB* && NAME =~ $core/* && CLOCK_DOMAINS == INDEPENDENT"] {
    set a [get_pins -quiet -leaf -of_objects [get_nets -quiet -of_objects [get_pins -quiet $r/CLKARDCLK]] -filter {DIRECTION == OUT}]
    set b [get_pins -quiet -leaf -of_objects [get_nets -quiet -of_objects [get_pins -quiet $r/CLKBWRCLK]] -filter {DIRECTION == OUT}]
    if {$a ne "" && $a eq $b} { set_property CLOCK_DOMAINS COMMON $r; incr n_cd }
  }
}
puts "NCD $n_cd"
report_drc -file q13_drc.rpt
