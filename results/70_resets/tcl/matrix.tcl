# Brief 70, Part 1: the reset-cost matrix on one part. Usage:
#   vivado -mode batch -source tcl/matrix.tcl -tclargs <part> <records.tsv> [variant-filter]
# One out-of-context synthesis per (variant, block) and one synthesis + opt/place/route of the four-block top per variant.
# general.maxThreads, synth.maxThreads and chipscope.maxJobs are 1 (house rule). Records: part, variant, blocks, key, value.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
set part [lindex $argv 0]
set out  [lindex $argv 1]
set filt [expr {[llength $argv] > 2 ? [lindex $argv 2] : "*"}]
set here [file dirname [file normalize [info script]]]
set src  [file normalize $here/../rtl/rb_top.sv]
set fh [open $out a]

# name  ASYNC ACTIVE_LOW RESET_ALL BOTH REGRST
set variants {
  {sH_all 0 0 1 0 0}  {sL_all 0 1 1 0 0}  {sH_ctl 0 0 0 0 0}  {sL_ctl 0 1 0 0 0}
  {aH_all 1 0 1 0 0}  {aL_all 1 1 1 0 0}  {aH_ctl 1 0 0 0 0}  {aL_ctl 1 1 0 0 0}
  {sBs_all 0 1 1 1 0}  {aBs_all 1 1 1 1 0}  {sB_all 0 1 1 2 0}  {aB_all 1 1 1 2 0}
}
# fan-out arms: reset registered once inside the module, with and without a synthesis max-fanout limit
set fanout_variants {
  {rH_all 0 0 1 0 1}  {rL_all 0 1 1 0 1}
}

proc rec {fh part v blocks key val} { puts $fh "$part\t$v\t$blocks\t$key\t$val"; flush $fh }

# histogram of the sinks reached from a reset net, through inverters (LUT1 cells)
proc walk {fh part v blocks stage net tag} {
  set seen {}
  set todo [list $net]
  set inv 0
  array set hist {}
  while {[llength $todo]} {
    set n [lindex $todo 0]; set todo [lrange $todo 1 end]
    if {[lsearch -exact $seen $n] >= 0} continue
    lappend seen $n
    foreach p [get_pins -quiet -of_objects $n -leaf -filter {DIRECTION == IN}] {
      set c [get_cells -of_objects $p]
      set ref [get_property REF_NAME $c]
      set pn [get_property REF_PIN_NAME $p]
      if {$ref eq "LUT1"} {
        incr inv
        foreach q [get_pins -quiet -of_objects $c -filter {DIRECTION == OUT}] {
          lappend todo [get_nets -of_objects $q]
        }
        continue
      }
      if {[string match LUT* $ref]} { set k "LUT_input" } else { set k "$ref/$pn" }
      if {![info exists hist($k)]} { set hist($k) 0 }
      incr hist($k)
    }
  }
  rec $fh $part $v $blocks "${stage}:${tag}_inverter_luts" $inv
  foreach k [lsort [array names hist]] { rec $fh $part $v $blocks "${stage}:${tag}_sink $k" $hist($k) }
}

proc measure {fh part v blocks stage} {
  array set cnt {}
  foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE}] {
    set r [get_property REF_NAME $c]
    if {![info exists cnt($r)]} { set cnt($r) 0 }
    incr cnt($r)
  }
  foreach r [lsort [array names cnt]] { rec $fh $part $v $blocks "${stage}:cell $r" $cnt($r) }
  set lut 0; set ff 0
  foreach r [array names cnt] {
    if {[regexp {^LUT[1-6]$} $r]} { incr lut $cnt($r) }
    if {[regexp {^(FDRE|FDSE|FDCE|FDPE|LDCE|LDPE)$} $r]} { incr ff $cnt($r) }
  }
  rec $fh $part $v $blocks "${stage}:luts" $lut
  rec $fh $part $v $blocks "${stage}:flipflops" $ff
  set ri 0; set ci 0; set di 0
  foreach c [get_cells -hier -quiet -filter {REF_NAME =~ FD* && IS_PRIMITIVE}] {
    catch {if {[get_property IS_R_INVERTED $c] == 1} {incr ri}}
    catch {if {[get_property IS_C_INVERTED $c] == 1} {incr ci}}
    catch {if {[get_property IS_D_INVERTED $c] == 1} {incr di}}
  }
  rec $fh $part $v $blocks "${stage}:ff_IS_R_INVERTED" $ri
  rec $fh $part $v $blocks "${stage}:ff_IS_C_INVERTED" $ci
  rec $fh $part $v $blocks "${stage}:ff_IS_D_INVERTED" $di
  set tmp [file rootname $::out].cs.tmp
  report_control_sets -verbose -file $tmp
  set f [open $tmp r]; set txt [read $f]; close $f; file delete $tmp
  if {[regexp {Total control sets\s*\|\s*(\d+)} $txt -> n]} { rec $fh $part $v $blocks "${stage}:control_sets" $n }
  set rp [get_ports -quiet rst_in]
  if {[llength $rp]} { walk $fh $part $v $blocks $stage [get_nets -of_objects $rp] rst_in }
  foreach c [get_cells -hier -quiet -filter {NAME =~ *g_rr.r_reg*}] {
    set q [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == Q}]
    if {[llength $q]} { walk $fh $part $v $blocks $stage [get_nets -of_objects $q] rstreg }
  }
  foreach c [get_cells -hier -quiet -filter {(REF_NAME =~ DSP48* || REF_NAME =~ RAMB*) && IS_PRIMITIVE}] {
    set r [get_property REF_NAME $c]
    foreach prop {AREG BREG CREG DREG ADREG MREG PREG DOA_REG DOB_REG DO_REG_A DO_REG_B} {
      catch {rec $fh $part $v $blocks "${stage}:$r reg $prop" [get_property $prop $c]}
    }
    foreach prop [list_property $c -regexp {IS_.*RST.*_INVERTED}] {
      rec $fh $part $v $blocks "${stage}:$r $prop" [get_property $prop $c]
    }
    foreach p [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME =~ RST* && DIRECTION == IN}] {
      set n [get_nets -quiet -of_objects $p]
      if {[llength $n] == 0} { set s unconnected } else {
        set t [get_property TYPE $n]
        set s [expr {$t eq "GROUND" ? "tied0" : ($t eq "POWER" ? "tied1" : "driven")}]
      }
      rec $fh $part $v $blocks "${stage}:$r pin [get_property REF_PIN_NAME $p]" $s
    }
  }
}

proc slack {kind} {
  set p [get_timing_paths -quiet -max_paths 1 -delay_type $kind]
  if {[llength $p] == 0} { return none }
  return [get_property SLACK $p]
}

# worst slack of the paths that end at a reset pin: synchronous (set-up to R/S or the DSP and RAM reset pins) or
# asynchronous (recovery to CLR/PRE)
proc reset_pin_slack {} {
  set pins [get_pins -quiet -hier -filter {(REF_PIN_NAME == R || REF_PIN_NAME == S || REF_PIN_NAME == CLR || REF_PIN_NAME == PRE || REF_PIN_NAME =~ RST*) && DIRECTION == IN && IS_LEAF}]
  if {[llength $pins] == 0} { return none }
  set p [get_timing_paths -quiet -to $pins -max_paths 1]
  if {[llength $p] == 0} { return none }
  return [get_property SLACK $p]
}

proc run_one {fh part v gen blocks maxfo do_impl} {
  global src
  set t0 [clock milliseconds]
  set args [list -top rb_top -part $part -mode out_of_context -flatten_hierarchy rebuilt]
  foreach {k val} $gen { lappend args -generic $k=$val }
  lappend args -generic BLOCKS=$blocks
  if {$maxfo > 0} { lappend args -fanout_limit $maxfo }
  read_verilog -sv $src
  if {[catch {synth_design {*}$args} err]} { rec $fh $part $v $blocks status "synth_failed: $err"; catch {close_design}; return }
  rec $fh $part $v $blocks synth_ms [expr {[clock milliseconds]-$t0}]
  measure $fh $part $v $blocks synth
  if {$do_impl} {
    # 5 ns clock; every input arrives 1 ns after the clock edge, the reset port 3 ns after it (so the reset's route to its
    # sinks is the path being timed); every output must be ready 1 ns before the next edge
    create_clock -name clk -period 5.0 [get_ports clk]
    set ins [get_ports -filter {DIRECTION == IN && NAME != clk && NAME != rst_in}]
    set_input_delay -clock clk 1.0 $ins
    set_input_delay -clock clk 3.0 [get_ports rst_in]
    set_output_delay -clock clk 1.0 [all_outputs]
    rec $fh $part $v $blocks synth:wns_setup [slack max]
    rec $fh $part $v $blocks synth:wns_to_reset_pins [reset_pin_slack]
    set t1 [clock milliseconds]
    if {[catch {opt_design; place_design; route_design} err]} {
      rec $fh $part $v $blocks status "impl_failed: $err"
    } else {
      rec $fh $part $v $blocks impl_ms [expr {[clock milliseconds]-$t1}]
      rec $fh $part $v $blocks route:wns_setup [slack max]
      rec $fh $part $v $blocks route:wns_hold [slack min]
      rec $fh $part $v $blocks route:wns_to_reset_pins [reset_pin_slack]
      measure $fh $part $v $blocks route
    }
  }
  catch {close_design}
}

foreach vd $variants {
  lassign $vd v a l all both rr
  if {![string match $filt $v]} continue
  set gen [list ASYNC $a ACTIVE_LOW $l RESET_ALL $all BOTH $both REGRST $rr]
  foreach b {1 2 4 8} { run_one $fh $part $v $gen $b 0 0 }
  run_one $fh $part $v $gen 15 0 1
}
foreach vd $fanout_variants {
  lassign $vd v a l all both rr
  set gen [list ASYNC $a ACTIVE_LOW $l RESET_ALL $all BOTH $both REGRST $rr]
  if {[string match $filt "${v}_fo_default"]} { run_one $fh $part "${v}_fo_default" $gen 15 0 0 }
  if {[string match $filt "${v}_fo_50"]} { run_one $fh $part "${v}_fo_50" $gen 15 50 0 }      ;# synth_design -fanout_limit 50 (deprecated option)
  if {[string match $filt "${v}_mf50"]} { run_one $fh $part "${v}_mf50" [concat $gen {MAXFO 50}] 15 0 0 }   ;# MAX_FANOUT = 50 on the reset register
}
close $fh
puts "matrix done $part"
