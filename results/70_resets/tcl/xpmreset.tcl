# Brief 70 Part 2c: the XPM macros' reset structure (rtl/xpm_probe.sv). vivado -mode batch -source tcl/xpmreset.tcl -tclargs <part> <records.tsv>
set_param general.maxThreads 1
set_param synth.maxThreads 1
lassign $argv part out
set here [file dirname [file normalize [info script]]]
set fh [open $out a]
proc rec {name key val} { global fh part; puts $fh "$part\t$name\t$key\t$val"; flush $fh }
foreach top {xp_fifo_sync xp_fifo_async xp_rst_async xp_rst_sync xp_mem_ram} {
  read_verilog -sv $here/../rtl/xpm_probe.sv
  synth_design -top $top -part $part -mode out_of_context
  array set cnt {}
  foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE}] {
    set r [get_property REF_NAME $c]
    if {![info exists cnt($r)]} { set cnt($r) 0 }
    incr cnt($r)
  }
  foreach r [lsort [array names cnt]] { if {[regexp {^(FD|LD|RAMB|LUT1$)} $r]} { rec $top "cell $r" $cnt($r) } }
  array unset cnt
  # reset-named input ports: sinks
  foreach p [get_ports -filter {DIRECTION == IN && (NAME =~ *rst* || NAME =~ *arst*)}] {
    set n [get_nets -of_objects $p]
    array set h {}
    foreach q [get_pins -quiet -of_objects $n -leaf -filter {DIRECTION == IN}] {
      set k "[get_property REF_NAME [get_cells -of_objects $q]]/[get_property REF_PIN_NAME $q]"
      if {![info exists h($k)]} { set h($k) 0 }
      incr h($k)
    }
    set s {}
    foreach {k v} [array get h] { lappend s "$k=$v" }
    rec $top "port [get_property NAME $p]" [lsort $s]
    array unset h
  }
  # the cell names of the asynchronous flops (the macro's own reset synchroniser shows here)
  set names {}
  foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE && (REF_NAME == FDCE || REF_NAME == FDPE)}] { lappend names [get_property NAME $c] }
  rec $top async_flop_names [lrange [lsort $names] 0 7]
  close_design
}
close $fh
puts "xpmreset done"
