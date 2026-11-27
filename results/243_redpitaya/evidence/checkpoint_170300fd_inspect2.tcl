open_checkpoint /home/brendan/Claude_sandbox/_worktrees/243-scratch/w_G/vendor/prj/fda_shell/build/redpitaya.runs/impl_1/red_pitaya_top_routed.dcp
proc nm {o} { if {[llength $o]==0} {return none}; return [lrange [get_property NAME $o] 0 7] }
proc fan {pin} {
  set n [get_nets -of [get_pins $pin] -top_net_of_hierarchical_group -segments]
  set l [get_pins -leaf -of $n -filter {DIRECTION==IN}]
  return "[llength $l] leaf loads: [nm $l]"
}
puts "=== leaf fan-out of the blocks' answer registers (flat netlist, nets followed through hierarchy)"
puts "slot 6 ack  : [fan i_user6_block/u_reg/sys_ack_reg/Q]"
puts "slot 7 ack  : [fan i_user_block/sys_ack_reg/Q]"
puts "slot 6 rdata0: [fan {i_user6_block/u_reg/sys_rdata_reg[0]/Q}]"
puts "slot 7 rdata0: [fan {i_user_block/sys_rdata_reg[0]/Q}]"
puts "=== the bridge's own state registers per slot (reg_read, reg_write, reg_done, ctrl_do)"
foreach i {6 7} {
  foreach r {reg_read_reg reg_write_reg reg_done_reg ctrl_do_reg} {
    puts "slot $i $r: [llength [get_cells -quiet sys_bus_interconnect/for_bus\[$i\].inst_sys_bus_cdc/$r]] cell"
  }
}
puts "=== registers fed by slot 6/7 rdata at the PS side (AXI slave RDATA path): first loads of the bridge rdata net"
set c [get_cells -quiet -hier -filter {NAME =~ ps/* && IS_SEQUENTIAL && NAME =~ *RDATA*}]
puts "PS-side RDATA registers: [llength $c]"
