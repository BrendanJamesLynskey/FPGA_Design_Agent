open_checkpoint /home/brendan/Claude_sandbox/_worktrees/243-scratch/w_G/vendor/prj/fda_shell/build/redpitaya.runs/impl_1/red_pitaya_top_routed.dcp
proc nm {o} { if {[llength $o]==0} {return none}; return [lrange [get_property NAME $o] 0 5] }
puts "=== cells under each user block"
foreach b {i_user_block i_user6_block} {
  set c [get_cells -quiet -hier -filter "NAME =~ $b/*"]
  puts "$b: [llength $c] leaf cells; regs: [llength [get_cells -quiet -hier -filter "NAME =~ $b/* && IS_SEQUENTIAL"]]"
}
puts "=== ack / rdata / wen / ren registers named in each block"
foreach b {i_user_block i_user6_block} {
  foreach pat {*sys_ack* *sys_rdata* *sys_err*} {
    set c [get_cells -quiet -hier -filter "NAME =~ $b/$pat && IS_SEQUENTIAL"]
    puts "$b $pat: [llength $c] regs, e.g. [nm $c]"
  }
}
puts "=== slot bridges (sys_bus_cdc) present per slot"
foreach i {0 1 2 3 4 5 6 7} {
  set c [get_cells -quiet -hier -filter "NAME =~ sys_bus_interconnect/for_bus\[$i\].inst_sys_bus_cdc/*"]
  puts "slot $i: [llength $c] cells under for_bus\[$i\].inst_sys_bus_cdc"
}
puts "=== ren/wen into the blocks: driver of each block's sys_wen/sys_ren-fed registers"
foreach {b i} {i_user6_block 6 i_user_block 7} {
  set rr [get_cells -quiet -hier -filter "NAME =~ sys_bus_interconnect/for_bus\[$i\].inst_sys_bus_cdc/reg_read_reg*"]
  set rw [get_cells -quiet -hier -filter "NAME =~ sys_bus_interconnect/for_bus\[$i\].inst_sys_bus_cdc/reg_write_reg*"]
  foreach r [concat $rr $rw] {
    set n [get_nets -of [get_pins $r/Q]]
    set loads [get_pins -of $n -filter DIRECTION==IN]
    puts "slot $i [get_property NAME $r] -> net [get_property NAME $n]: [llength $loads] loads: [nm $loads]"
  }
}
puts "=== block ack register output nets and their loads"
foreach b {i_user6_block i_user_block} {
  foreach r [get_cells -quiet -hier -filter "NAME =~ $b/* && IS_SEQUENTIAL && NAME =~ *sys_ack*"] {
    set n [get_nets -of [get_pins $r/Q]]
    set loads [get_pins -of $n -filter DIRECTION==IN]
    puts "$b: [get_property NAME $r] -> [get_property NAME $n]: [llength $loads] loads: [nm $loads]"
  }
}
puts "=== a sample path: block rdata bit0 register to the PS-side"
foreach b {i_user6_block i_user_block} {
  set r [lindex [get_cells -quiet -hier -filter "NAME =~ $b/* && IS_SEQUENTIAL && NAME =~ *sys_rdata_reg\[0\]*"] 0]
  if {$r ne ""} {
    set n [get_nets -of [get_pins $r/Q]]
    puts "$b [get_property NAME $r] -> [get_property NAME $n]: loads [nm [get_pins -of $n -filter DIRECTION==IN]]"
  }
}
puts "=== any constant-driven ports or removed cells in the blocks"
puts "unconnected nets under blocks: [llength [get_nets -quiet -hier -filter {NAME =~ i_user*_block/* && ROUTE_STATUS == UNROUTED}]]"
report_utilization -hierarchical -hierarchical_depth 1 -file /home/brendan/Claude_sandbox/_worktrees/243-scratch/ck/util_hier.rpt
puts "=== done"
