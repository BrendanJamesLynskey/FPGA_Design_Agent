# Brief 70 Part 2c: a small block design made by IP Integrator's own automation, and how the tools wire its resets.
#   vivado -mode batch -source tcl/bd.tcl -tclargs <kind mb|ps> <intc ic|sc> <workdir> <records.tsv>
#   mb: MicroBlaze (xc7a100t), ps: Zynq UltraScale+ processing system (xck26).
# Always: Processor System Reset (made by the automation), the chosen interconnect, AXI GPIO and AXI UART Lite.
# Records: kind, intc, key, value (the BD's reset pins and their drivers; after synthesis, the netlist's reset structure).
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
lassign $argv kind intc work out
file mkdir $work
set fh [open $out a]
proc rec {key val} { global fh kind intc; puts $fh "$kind\t$intc\t$key\t$val"; flush $fh }
set part [expr {$kind eq "mb" ? "xc7a100tcsg324-1" : "xck26-sfvc784-2LV-c"}]
create_project -force bdp $work/proj -part $part
rec vivado [version -short]
rec part $part
create_bd_design bd
set icvlnv [expr {$intc eq "ic" ? "New AXI Interconnect" : "New AXI SmartConnect"}]

if {$kind eq "mb"} {
  create_bd_cell -type ip -vlnv [lindex [lsort -dictionary [get_ipdefs -all xilinx.com:ip:microblaze:*]] end] microblaze_0
  # SmartConnect arm: the automation makes the peripheral interconnect; AXI Interconnect arm: it is left out and placed by hand
  set periph [expr {$intc eq "sc" ? "Enabled" : "Disabled"}]
  apply_bd_automation -rule xilinx.com:bd_rule:microblaze -config [list local_mem "8KB" ecc "None" cache "None" debug_module "Debug Only" axi_periph $periph axi_intc "0" clk "New External Port"] [get_bd_cells microblaze_0]
  if {$intc ne "sc"} { set_property -dict [list CONFIG.C_D_AXI 1] [get_bd_cells microblaze_0] }     ;# the data port, left off by "Disabled"
  set mst [expr {$intc eq "sc" ? {/microblaze_0 (Periph)} : {microblaze_0/M_AXI_DP}}]
} else {
  create_bd_cell -type ip -vlnv [lindex [lsort -dictionary [get_ipdefs -all xilinx.com:ip:zynq_ultra_ps_e:*]] end] zynq_ultra_ps_e_0
  apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "0"} [get_bd_cells zynq_ultra_ps_e_0]
  set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 {1} CONFIG.PSU__USE__M_AXI_GP2 {0}] [get_bd_cells zynq_ultra_ps_e_0]
  set mst /zynq_ultra_ps_e_0/M_AXI_HPM0_FPD
  connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins zynq_ultra_ps_e_0/maxihpm0_fpd_aclk]
}
create_bd_cell -type ip -vlnv [lindex [lsort -dictionary [get_ipdefs -all xilinx.com:ip:axi_gpio:*]] end] axi_gpio_0
create_bd_cell -type ip -vlnv [lindex [lsort -dictionary [get_ipdefs -all xilinx.com:ip:axi_uartlite:*]] end] axi_uartlite_0
if {$intc eq "sc"} {
  foreach s {axi_gpio_0 axi_uartlite_0} {
    apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config [list Clk_master Auto Clk_slave Auto Clk_xbar Auto Master $mst Slave /$s/S_AXI intc_ip {New AXI SmartConnect} master_apm 0] [get_bd_intf_pins $s/S_AXI]
  }
} else {
  # the 2026.1 connection automation only offers SmartConnect, so the AXI Interconnect is placed by hand and wired the way the
  # Processor System Reset is built to be used: interconnect_aresetn to the interconnect's ARESETN, peripheral_aresetn to every
  # interface's aresetn and to the peripherals (the connections are ours, not the tool's: the record says so)
  if {$kind eq "ps"} {
    create_bd_cell -type ip -vlnv [lindex [lsort -dictionary [get_ipdefs -all xilinx.com:ip:proc_sys_reset:*]] end] rst_ps
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins rst_ps/slowest_sync_clk]
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0] [get_bd_pins rst_ps/ext_reset_in]
    set psr rst_ps
  } else {
    set psr rst_Clk_100M
  }
  create_bd_cell -type ip -vlnv [lindex [lsort -dictionary [get_ipdefs -all xilinx.com:ip:axi_interconnect:*]] end] axi_ic
  set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 2] [get_bd_cells axi_ic]
  connect_bd_intf_net [get_bd_intf_pins $mst] [get_bd_intf_pins axi_ic/S00_AXI]
  connect_bd_intf_net [get_bd_intf_pins axi_ic/M00_AXI] [get_bd_intf_pins axi_gpio_0/S_AXI]
  connect_bd_intf_net [get_bd_intf_pins axi_ic/M01_AXI] [get_bd_intf_pins axi_uartlite_0/S_AXI]
  set clknet [get_bd_nets -of_objects [get_bd_pins $psr/slowest_sync_clk]]
  foreach p {axi_ic/ACLK axi_ic/S00_ACLK axi_ic/M00_ACLK axi_ic/M01_ACLK axi_gpio_0/s_axi_aclk axi_uartlite_0/s_axi_aclk} {
    connect_bd_net -net $clknet [get_bd_pins $p]
  }
  connect_bd_net [get_bd_pins $psr/interconnect_aresetn] [get_bd_pins axi_ic/ARESETN]
  foreach p {axi_ic/S00_ARESETN axi_ic/M00_ARESETN axi_ic/M01_ARESETN axi_gpio_0/s_axi_aresetn axi_uartlite_0/s_axi_aresetn} {
    connect_bd_net [get_bd_pins $psr/peripheral_aresetn] [get_bd_pins $p]
  }
  rec note_wiring "axi_interconnect placed and wired by hand (the 2026.1 automation offers SmartConnect only)"
}
if {$kind eq "mb"} {
  # the automation leaves the Processor System Reset's external reset input open: add the board's reset button as a port
  if {[llength [get_bd_nets -quiet -of_objects [get_bd_pins -quiet rst_Clk_100M/ext_reset_in]]] == 0} {
    set rp [create_bd_port -dir I -type rst reset]
    set_property CONFIG.POLARITY ACTIVE_LOW $rp
    connect_bd_net $rp [get_bd_pins rst_Clk_100M/ext_reset_in]
    rec "note" "ext_reset_in was left open by the automation; connected an active-low port"
  }
}
if {$kind eq "ps"} {
  # the automation leaves the PS reset-controller wiring to the user: add one Processor System Reset on pl_clk0
  if {[llength [get_bd_cells -quiet -filter {VLNV =~ *proc_sys_reset*}]] == 0} {
    create_bd_cell -type ip -vlnv [lindex [lsort -dictionary [get_ipdefs -all xilinx.com:ip:proc_sys_reset:*]] end] rst_ps
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins rst_ps/slowest_sync_clk]
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0] [get_bd_pins rst_ps/ext_reset_in]
  }
}
catch {validate_bd_design} verr
rec validate $verr
save_bd_design

# ---- the block design's reset wiring: every reset-typed pin, its direction, its net and the net's other pins -------------
foreach c [lsort [get_bd_cells -hier]] { rec "cell $c" [get_property VLNV $c] }
foreach p [lsort [get_bd_pins -hier -filter {TYPE == rst}]] {
  set n [get_bd_nets -quiet -of_objects $p]
  set others {}
  if {[llength $n]} { foreach q [get_bd_pins -quiet -of_objects $n] { if {$q ne $p} { lappend others $q } } }
  set pol ""
  catch {set pol [get_property CONFIG.POLARITY $p]}
  rec "rstpin $p" "dir=[get_property DIR $p] polarity=$pol net=[expr {[llength $n] ? $n : {none}}] peers=[lsort $others]"
}
foreach p [lsort [get_bd_ports -filter {TYPE == rst}]] {
  set n [get_bd_nets -quiet -of_objects $p]
  set peers {}
  if {[llength $n]} { foreach q [get_bd_pins -quiet -of_objects $n] { lappend peers $q } }
  rec "rstport $p" "dir=[get_property DIR $p] polarity=[get_property CONFIG.POLARITY $p] peers=[lsort $peers]"
}
# inverters or logic cells inserted by the tools between resets
rec util_logic_cells [llength [get_bd_cells -quiet -hier -filter {VLNV =~ *util_vector_logic*}]]

# ---- generate, synthesise (project flow, one job), measure the netlist ---------------------------------------------------
generate_target all [get_files bd.bd]
make_wrapper -files [get_files bd.bd] -top
add_files -norecurse [glob $work/proj/bdp.gen/sources_1/bd/bd/hdl/bd_wrapper.v]
update_compile_order -fileset sources_1
set_property top bd_wrapper [current_fileset]
set_property -name {STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY} -value rebuilt -objects [get_runs synth_1]
set t0 [clock seconds]
launch_runs synth_1 -jobs 1
wait_on_run synth_1
rec synth_status [get_property STATUS [get_runs synth_1]]
rec synth_s [expr {[clock seconds]-$t0}]
open_run synth_1
array set cnt {}
foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE}] {
  set r [get_property REF_NAME $c]
  if {![info exists cnt($r)]} { set cnt($r) 0 }
  incr cnt($r)
}
foreach r [lsort [array names cnt]] { if {[regexp {^(FD|LD|LUT1$|BUFG|SRL|CARRY|DSP|RAMB|PS8|MicroBlaze)} $r]} { rec "synth cell $r" $cnt($r) } }
set tmp $work/cs.rpt
report_control_sets -verbose -file $tmp
set f [open $tmp r]; set txt [read $f]; close $f
if {[regexp {Total control sets\s*\|\s*(\d+)} $txt -> n]} { rec synth_control_sets $n }
# reset pins of every flip-flop, grouped by the IP that owns it (first hierarchy level under the BD) and primitive type
array unset g
foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE && (REF_NAME =~ FD* || REF_NAME =~ LD*)}] {
  set r [get_property REF_NAME $c]
  set nm [get_property NAME $c]
  set parts [split $nm /]
  set owner [expr {[llength $parts] > 2 ? [lindex $parts 1] : "top"}]
  set k "$owner $r"
  if {![info exists g($k)]} { set g($k) 0 }
  incr g($k)
}
foreach k [lsort [array names g]] { rec "ff_by_owner $k" $g($k) }
# fan-out of every Processor System Reset output through inverters (LUT1) to its sinks, by sink primitive and pin
proc sinks_of {net} {
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
foreach c [get_cells -hier -quiet -filter {IS_PRIMITIVE && REF_NAME == FDRE && NAME =~ *FDRE_*}] {
  set nm [get_property NAME $c]
  if {![regexp {(FDRE_BSR_N|FDRE_BSR|FDRE_PER_N|FDRE_PER|FDRE_inst)} $nm -> tag]} continue
  set q [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == Q}]
  if {![llength $q]} continue
  set net [get_nets -of_objects $q]
  lassign [sinks_of $net] inv hist
  set s {}
  foreach {k v} $hist { lappend s "$k=$v" }
  rec "psr_output $tag" "inverter_luts=$inv sinks=[lsort $s]"
}
close $fh
puts "bd done $kind $intc"
