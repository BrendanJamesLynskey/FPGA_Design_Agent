# flow/clock_mux_dump.tcl (brief 208): dump the clock-mux structure of the open design, one fact per line, for flow/clock_mux_check.py.
#   source clock_mux_dump.tcl; clock_mux_dump <out file>
# Lines (tab-separated):
#   PART    <part> <architecture> <7|us>   (7: 7 series / Zynq-7000; us: UltraScale and UltraScale+)
#   MUX     <cell> <ref> <orig_ref> <n_inputs>
#   MUXIN   <cell> <pin> <driver cell> <driver ref> <clocks on pin, comma list>
#   MUXOUT  <cell> <clocks on O, comma list>
#   MUXOCLK <cell> <clock on O> <its master clock, or - for a clock propagated through the mux>
#   MUXCTL  <cell> <pin> <constant 0|1|-> <driver cell> <driver ref>
#   LUTCLK  <lut cell> <ref> <number of clock pins it drives, through buffers> <clocks on its output, comma list>
#   FANOUT  <mux cell> <registers whose clock comes through the mux>
#   INTER   <mux cell> <A|C> <count> <example>   registers outside the fanout that feed it (A) or that it feeds (C)
#   INTERCLK <mux cell> <A|C> <clocks of those registers, comma list> <count> <example register>
#   (structural, constraint-independent; one all_fanin and one all_fanout per mux, review fix of brief 208)
# Driver fields: "-" when the pin has no net (unconnected), "?" when the net has no driver the dump can see (a black box
# or a hierarchical boundary); MUXCTL constant field: 0, 1, "-" (driven by logic) or "x" (no net).
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
    return [list "?" "?"]
  }
  set c [get_cells -of_objects [lindex $drv 0]]
  return [list [get_property NAME $c] [get_property REF_NAME $c]]
}
proc _cm_const {pin} {
  set net [get_nets -quiet -of_objects $pin]
  if {$net eq ""} { return "x" }
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
    set opin0 [get_pins -of_objects $m -filter {REF_PIN_NAME == O}]
    puts $fh [join [list MUXOUT $name [_cm_clocks $opin0]] "\t"]
    foreach ck [get_clocks -quiet -of_objects $opin0] {
      set mc [get_property -quiet MASTER_CLOCK $ck]
      if {$mc eq ""} { set mc "-" }
      puts $fh [join [list MUXOCLK $name [get_property NAME $ck] $mc] "\t"]
    }
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
    # registers outside the fanout feeding it (A) and fed by it (C), grouped by their own clocks
    foreach dir {A C} {
      if {$dir eq "A"} {
        set pins [get_pins -quiet -of_objects $fo -filter {DIRECTION == IN && !IS_CLOCK}]
        set other {}
        if {[llength $pins]} { set other [get_cells -quiet [all_fanin -quiet -flat -startpoints_only -only_cells $pins] -filter {IS_SEQUENTIAL}] }
      } else {
        set pins [get_pins -quiet -of_objects $fo -filter {DIRECTION == OUT}]
        set other {}
        if {[llength $pins]} { set other [get_cells -quiet [all_fanout -quiet -flat -endpoints_only -only_cells $pins] -filter {IS_SEQUENTIAL}] }
      }
      set n 0; set ex "-"; set byclk [dict create]
      foreach c $other {
        set cn [get_property NAME $c]
        if {[dict exists $foset $cn]} continue
        incr n
        if {$ex eq "-"} { set ex $cn }
        set ck [_cm_clocks [get_pins -quiet -of_objects $c -filter {IS_CLOCK}]]
        if {![dict exists $byclk $ck]} { dict set byclk $ck [list 0 $cn] }
        dict set byclk $ck [list [expr {[lindex [dict get $byclk $ck] 0] + 1}] [lindex [dict get $byclk $ck] 1]]
      }
      puts $fh [join [list INTER $name $dir $n $ex] "\t"]
      dict for {ck v} $byclk { puts $fh [join [list INTERCLK $name $dir $ck [lindex $v 0] [lindex $v 1]] "\t"] }
    }
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
