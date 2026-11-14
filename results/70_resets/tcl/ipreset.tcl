# Brief 70 Part 2c: what each AMD IP's synthesised netlist does with its resets (Vivado 2026.1, out of context, default settings
# unless noted). For every IP: the storage cells by type (FDRE/FDSE are synchronous set or reset, FDCE/FDPE asynchronous),
# control sets, the sinks of each reset-named input port, and the root nets that drive asynchronous pins.
#   vivado -mode batch -source tcl/ipreset.tcl -tclargs <part> <workdir> <records.tsv> [ip-filter]
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
lassign $argv part work out
set filt [expr {[llength $argv] > 3 ? [lindex $argv 3] : "*"}]
file mkdir $work
set fh [open $out a]
proc rec {name key val} { global fh part; puts $fh "$part\t$name\t$key\t$val"; flush $fh }

# name, catalogue name, configuration
set ips {
  {psr           proc_sys_reset  {}}
  {gpio          axi_gpio        {CONFIG.C_GPIO_WIDTH 8 CONFIG.C_INTERRUPT_PRESENT 1}}
  {uartlite      axi_uartlite    {CONFIG.C_BAUDRATE 115200}}
  {timer         axi_timer       {}}
  {intc          axi_intc        {CONFIG.C_NUM_INTR_INPUTS 4}}
  {iic           axi_iic         {}}
  {qspi          axi_quad_spi    {CONFIG.C_SPI_MODE 0 CONFIG.FIFO_INCLUDED 1}}
  {dma           axi_dma         {CONFIG.c_include_sg 0}}
  {regslice      axi_register_slice {CONFIG.PROTOCOL AXI4LITE}}
  {fifogen_sync  fifo_generator  {CONFIG.Fifo_Implementation Common_Clock_Block_RAM CONFIG.Input_Data_Width 32 CONFIG.Input_Depth 512}}
  {fifogen_async fifo_generator  {CONFIG.Fifo_Implementation Independent_Clocks_Block_RAM CONFIG.Input_Data_Width 32 CONFIG.Input_Depth 512}}
}

proc walk {net} {
  set seen {}; set todo [list $net]; set inv 0; array set h {}
  while {[llength $todo]} {
    set n [lindex $todo 0]; set todo [lrange $todo 1 end]
    if {[lsearch -exact $seen $n] >= 0} continue
    lappend seen $n
    foreach p [get_pins -quiet -of_objects $n -leaf -filter {DIRECTION == IN}] {
      set c [get_cells -of_objects $p]; set ref [get_property REF_NAME $c]
      if {$ref eq "LUT1"} { incr inv; foreach q [get_pins -quiet -of_objects $c -filter {DIRECTION == OUT}] { lappend todo [get_nets -of_objects $q] }; continue }
      if {[string match LUT* $ref]} { set k LUT_input } else { set k "$ref/[get_property REF_PIN_NAME $p]" }
      if {![info exists h($k)]} { set h($k) 0 }
      incr h($k)
    }
  }
  return [list $inv [array get h]]
}

foreach e $ips {
  lassign $e name ip cfg
  if {![string match $filt $name]} continue
  set t0 [clock seconds]
  create_project -in_memory -part $part
  set def [lindex [lsort [get_ipdefs -all xilinx.com:ip:$ip:*]] end]
  rec $name vlnv $def
  file mkdir $work/$name
  create_ip -name $ip -vendor xilinx.com -library ip -module_name dut_$name -dir $work/$name
  if {[llength $cfg]} { set_property -dict $cfg [get_ips dut_$name] }
  generate_target all [get_ips dut_$name]
  if {[catch {synth_ip [get_ips dut_$name]} err]} { rec $name status "synth_failed: $err"; close_project; continue }
  set dcp [lindex [get_files -all -of_objects [get_ips dut_$name] -filter {NAME =~ *.dcp}] 0]
  open_checkpoint $dcp
  rec $name synth_s [expr {[clock seconds]-$t0}]
  array set cnt {}
  foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE}] {
    set r [get_property REF_NAME $c]
    if {![info exists cnt($r)]} { set cnt($r) 0 }
    incr cnt($r)
  }
  foreach r [lsort [array names cnt]] { if {[regexp {^(FD|LD|SRL|RAMB|DSP|LUT1$)} $r]} { rec $name "cell $r" $cnt($r) } }
  set tmp $work/cs_$name.rpt
  report_control_sets -verbose -file $tmp
  set f [open $tmp r]; set txt [read $f]; close $f
  if {[regexp {Total control sets\s*\|\s*(\d+)} $txt -> n]} { rec $name control_sets $n }
  # sinks of each reset-named input port
  foreach p [get_ports -quiet -filter {DIRECTION == IN}] {
    set pn [get_property NAME $p]
    if {![string match -nocase *reset* $pn] && ![string match -nocase *rst* $pn]} continue
    set n [get_nets -quiet -of_objects $p]
    if {![llength $n]} continue
    lassign [walk $n] inv hist
    set s {}
    foreach {k v} $hist { lappend s "$k=$v" }
    rec $name "port $pn" "inverter_luts=$inv sinks=[lsort $s]"
  }
  # asynchronous set/reset pins: which nets drive them (grouped by the driver's primitive and hierarchy leaf name)
  array unset roots
  foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE && (REF_NAME == FDCE || REF_NAME == FDPE || REF_NAME == LDCE || REF_NAME == LDPE)}] {
    foreach p [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == CLR || REF_PIN_NAME == PRE || REF_PIN_NAME == GE}] {
      set n [get_nets -quiet -of_objects $p]
      if {![llength $n]} continue
      set d [get_pins -quiet -of_objects $n -leaf -filter {DIRECTION == OUT}]
      set k [expr {[llength $d] ? "[get_property REF_NAME [get_cells -of_objects $d]] [regsub {\[\d+\]$} [get_property NAME [get_cells -of_objects $d]] {}]" : "port [get_property NAME $n]"}]
      if {![info exists roots($k)]} { set roots($k) 0 }
      incr roots($k)
    }
  }
  foreach k [lsort [array names roots]] { rec $name "async_pin_driver $k" $roots($k) }
  array unset cnt
  close_design
  close_project
}
close $fh
puts "ipreset done"
