# Brief 206: AMD power-up value arms. One Vivado batch session per part.
#   vivado -mode batch -source arms.tcl -tclargs <part> <records.tsv> <netlist_dir>
# Every arm is synthesised out of context (X7 is synthesised in context and placed, for IOB packing). One run each.
# Each arm writes "### ARM <arm> <initv>" to the log so the messages can be split per arm afterwards (split_log.py).
set part    [lindex $argv 0]
set out     [lindex $argv 1]
set netdir  [lindex $argv 2]
set here    [file dirname [file normalize [info script]]]
set rtl     [file normalize $here/../rtl]
set_param general.maxThreads 1
catch {set_param synth.maxThreads 1}
set fh [open $out w]
proc rec {arm initv key val} { global fh part; puts $fh "$part\t$arm\t$initv\t$key\t$val"; flush $fh }

proc record_netlist {arm initv} {
  # cell counts by type
  set counts [dict create]
  foreach c [get_cells -hier -filter {IS_PRIMITIVE}] {
    set r [get_property REF_NAME $c]
    dict incr counts $r
  }
  foreach r [lsort [dict keys $counts]] { rec $arm $initv "cells.$r" [dict get $counts $r] }
  # flip-flops by type and INIT
  set ff [dict create]
  foreach c [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ FD*}] {
    dict incr ff "[get_property REF_NAME $c].INIT=[get_property INIT $c]"
  }
  foreach k [lsort [dict keys $ff]] { rec $arm $initv "ff.$k" [dict get $ff $k] }
  # block RAM output-latch and register values, register use, first content word
  foreach c [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ RAMB*}] {
    foreach p {INIT_A INIT_B SRVAL_A SRVAL_B DOA_REG DOB_REG INIT_00 READ_WIDTH_A READ_WIDTH_B} {
      if {![catch {get_property $p $c} v]} { rec $arm $initv "bram.[get_property NAME $c].$p" $v }
    }
  }
  foreach c [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ URAM*}] {
    foreach p {OREG_A OREG_B IREG_PRE_A IREG_PRE_B} {
      if {![catch {get_property $p $c} v]} { rec $arm $initv "uram.[get_property NAME $c].$p" $v }
    }
  }
  foreach c [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ DSP*}] {
    foreach p {AREG BREG ACASCREG BCASCREG MREG PREG} {
      if {![catch {get_property $p $c} v]} { rec $arm $initv "dsp.[get_property NAME $c].$p" $v }
    }
  }
  # distributed RAM and SRL contents
  foreach c [get_cells -hier -filter {IS_PRIMITIVE && (REF_NAME =~ RAM32* || REF_NAME =~ RAM64* || REF_NAME =~ RAM16* || REF_NAME =~ SRL*)}] {
    foreach p {INIT INIT_A INIT_B INIT_C INIT_D} {
      if {![catch {get_property $p $c} v] && $v ne ""} { rec $arm $initv "lutmem.[get_property NAME $c].[get_property REF_NAME $c].$p" $v }
    }
  }
  # LUT1 cells (inverters or buffers) and their function
  set inv 0
  foreach c [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME == LUT1}] { if {[get_property INIT $c] eq "2'h1"} { incr inv } }
  rec $arm $initv "lut1_inverters" $inv
}

proc run_arm {arm top initv {generics {}} {ooc 1}} {
  global part rtl netdir
  puts "### ARM $arm $initv"
  close_project -quiet
  create_project -in_memory -part $part
  read_verilog -sv $rtl/pu_arms.sv
  read_vhdl $rtl/x12_vhdl_int.vhd
  set g [concat [list INITV=$initv] $generics]
  set args [list -top $top -part $part -generic $g -flatten_hierarchy rebuilt]
  if {$ooc} { lappend args -mode out_of_context }
  if {[catch {synth_design {*}$args} err]} { rec $arm $initv "synth_error" [string map {"\n" " "} $err]; puts "### END $arm $initv"; return 0 }
  record_netlist $arm $initv
  write_verilog -force -mode funcsim $netdir/${part}_${arm}_${initv}.v
  puts "### END $arm $initv"
  return 1
}

set is_us [string match xck26* $part]
foreach initv {0 1} {
  run_arm x1  x1_plain   $initv
  run_arm x2  x2_sreset0 $initv
  run_arm x3  x3_sset1   $initv
  run_arm x4  x4_aclr    $initv
  run_arm x5  x5_apre    $initv
  run_arm x6  x6_pipe64  $initv
  run_arm x8  x8_dsp     $initv
  run_arm x9  x9_bram    $initv
  run_arm x10 x10_lutram_srl $initv
  if {$is_us} { run_arm x11 x11_uram $initv }
}
run_arm x12 x12_vhdl_int 1

# X7: IOB packing needs I/O buffers and placement
set iostd [expr {$is_us ? "LVCMOS18" : "LVCMOS33"}]
foreach initv {0 1} {
  foreach rm {0 1 2} {
    set arm "x7_r$rm"
    if {![run_arm $arm x7_iob $initv [list RST_MODE=$rm] 0]} continue
    puts "### ARM ${arm}_place $initv"
    set_property IOSTANDARD $iostd [get_ports *]
    create_clock -period 5.0 [get_ports clk]
    opt_design
    place_design
    foreach c [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ FD* && NAME =~ *reg*}] {
      set n [get_property NAME $c]
      if {![string match *ireg* $n] && ![string match *oreg* $n]} continue
      set site [get_sites -quiet -of_objects $c]
      set st [expr {$site eq "" ? "-" : [get_property SITE_TYPE $site]}]
      rec ${arm}_place $initv "placed.$n" "[get_property REF_NAME $c] INIT=[get_property INIT $c] IOB=[get_property IOB $c] site_type=$st bel=[get_property BEL $c]"
    }
    puts "### END ${arm}_place $initv"
  }
}
close $fh
