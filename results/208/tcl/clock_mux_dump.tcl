# Brief 208: dump the clock-mux structure of the open design, one fact per line, for flow/clock_mux_check.py.
#   source clock_mux_dump.tcl; clock_mux_dump <out file>
# Lines (tab-separated):
#   PART    <part> <architecture> <7|us>   (7: 7 series / Zynq-7000; us: UltraScale and UltraScale+)
#   MUX     <cell> <ref> <orig_ref> <n_inputs>
#   MUXIN   <cell> <pin> <driver cell> <driver ref> <clocks on pin, comma list>
#   MUXOUT  <cell> <clocks on O, comma list>
#   MUXCTL  <cell> <pin> <constant 0|1|-> <driver cell> <driver ref>
#   LUTCLK  <lut cell> <ref> <number of clock pins it drives, through buffers> <clocks on its output, comma list>
#   FANOUT  <mux cell> <registers whose clock comes through the mux>
#   INTER   <mux cell> <A|C> <count> <example start> <example end>   (structural, constraint-independent)
proc _cm_clocks {pin} {
  set c [get_clocks -quiet -of_objects $pin]
  if {[llength $c] == 0} { return "-" }
  return [join [lsort [get_property NAME $c]] ","]
}
proc _cm_driver {pin} {
  set net [get_nets -quiet -of_objects $pin]
  if {$net eq ""} { return [list "-" "-"] }
  set drv [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}]
  if {$drv eq ""} {
    set p [get_ports -quiet -of_objects $net]
    if {$p ne ""} { return [list $p PORT] }
    return [list "-" "-"]
  }
  set c [get_cells -of_objects [lindex $drv 0]]
  return [list [get_property NAME $c] [get_property REF_NAME $c]]
}
proc _cm_const {pin} {
  set net [get_nets -quiet -of_objects $pin]
  if {$net eq ""} { return "-" }
  set t [get_property TYPE $net]
  if {$t eq "GROUND"} { return 0 }
  if {$t eq "POWER"} { return 1 }
  return "-"
}
proc clock_mux_dump {out} {
  set fh [open $out w]
  set part [get_property -quiet PART [current_design]]
  set arch [get_property -quiet ARCHITECTURE [get_parts -quiet $part]]
  puts $fh [join [list PART $part $arch [expr {[regexp {^(artix7|kintex7|virtex7|zynq|spartan7|aartix7|azynq|qartix7|qkintex7|qvirtex7|qzynq)$} $arch] ? "7" : "us"}]] "\t"]
  set muxes [get_cells -quiet -hier -filter {IS_PRIMITIVE && (REF_NAME =~ BUFGMUX* || REF_NAME == BUFGCTRL || ORIG_REF_NAME =~ BUFGMUX*)}]
  foreach m $muxes {
    set name [get_property NAME $m]
    set ref [get_property REF_NAME $m]
    set orig [get_property ORIG_REF_NAME $m]
    if {$orig eq ""} { set orig "-" }
    set ins [get_pins -of_objects $m -filter {REF_PIN_NAME == I0 || REF_PIN_NAME == I1}]
    puts $fh [join [list MUX $name $ref $orig [llength $ins]] "\t"]
    foreach p $ins {
      lassign [_cm_driver $p] dc dr
      puts $fh [join [list MUXIN $name [get_property REF_PIN_NAME $p] $dc $dr [_cm_clocks $p]] "\t"]
    }
    puts $fh [join [list MUXOUT $name [_cm_clocks [get_pins -of_objects $m -filter {REF_PIN_NAME == O}]]] "\t"]
    foreach p [get_pins -of_objects $m -filter {DIRECTION == IN && REF_PIN_NAME != I0 && REF_PIN_NAME != I1}] {
      lassign [_cm_driver $p] dc dr
      puts $fh [join [list MUXCTL $name [get_property REF_PIN_NAME $p] [_cm_const $p] $dc $dr] "\t"]
    }
    # registers clocked through this mux, and structural paths between them and registers on other clock trees
    set opin [get_pins -of_objects $m -filter {REF_PIN_NAME == O}]
    set fo [get_cells -quiet [all_fanout -quiet -flat -endpoints_only -only_cells $opin] -filter {IS_SEQUENTIAL}]
    puts $fh [join [list FANOUT $name [llength $fo]] "\t"]
    set foset [dict create]
    foreach c $fo { dict set foset [get_property NAME $c] 1 }
    set nA 0; set exA "-"; set nC 0; set exC "-"
    foreach c $fo {
      set d [get_pins -quiet -of_objects $c -filter {DIRECTION == IN && !IS_CLOCK}]
      if {$d eq ""} continue
      foreach s [get_cells -quiet [all_fanin -quiet -flat -startpoints_only -only_cells $d] -filter {IS_SEQUENTIAL}] {
        if {![dict exists $foset [get_property NAME $s]]} { incr nA; if {$exA eq "-"} { set exA "[get_property NAME $s] -> [get_property NAME $c]" } }
      }
      set q [get_pins -quiet -of_objects $c -filter {DIRECTION == OUT}]
      if {$q eq ""} continue
      foreach e [get_cells -quiet [all_fanout -quiet -flat -endpoints_only -only_cells $q] -filter {IS_SEQUENTIAL}] {
        if {![dict exists $foset [get_property NAME $e]]} { incr nC; if {$exC eq "-"} { set exC "[get_property NAME $c] -> [get_property NAME $e]" } }
      }
    }
    puts $fh [join [list INTER $name A $nA $exA] "\t"]
    puts $fh [join [list INTER $name C $nC $exC] "\t"]
  }
  # LUTs whose output reaches a clock pin (directly or through clock buffers)
  foreach l [get_cells -quiet -hier -filter {IS_PRIMITIVE && REF_NAME =~ LUT*}] {
    set o [get_pins -of_objects $l -filter {DIRECTION == OUT}]
    set ck [get_pins -quiet [all_fanout -quiet -flat -endpoints_only $o] -filter {IS_CLOCK}]
    if {[llength $ck] > 0} {
      puts $fh [join [list LUTCLK [get_property NAME $l] [get_property REF_NAME $l] [llength $ck] [_cm_clocks $o]] "\t"]
    }
  }
  close $fh
}
