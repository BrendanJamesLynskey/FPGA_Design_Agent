# build_p0.tcl: bring-up design p0 for the ZedBoard: PS7 + AXI GPIO on LD0-LD7. Vivado 2026.1.
#   vivado -mode batch -source build_p0.tcl -tclargs <out dir>
set_param general.maxThreads 2
set_param synth.maxThreads 2
set_param chipscope.maxJobs 1
set here [file dirname [file normalize [info script]]]
source $here/ps7_zedboard.tcl
set out [lindex $argv 0]
file mkdir $out
create_project -force p0 $out/proj -part xc7z020clg484-1
create_bd_design zb_p0
set ps [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:processing_system7:*] end] ps7]
zb_config_ps7 $ps {}
make_bd_intf_pins_external [get_bd_intf_pins ps7/DDR]
make_bd_intf_pins_external [get_bd_intf_pins ps7/FIXED_IO]
set gpio [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:axi_gpio:*] end] gpio_led]
set_property -dict [list CONFIG.C_GPIO_WIDTH {8} CONFIG.C_ALL_OUTPUTS {1}] $gpio
set rst [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:proc_sys_reset:*] end] rst0]
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins gpio_led/s_axi_aclk] [get_bd_pins rst0/slowest_sync_clk]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins rst0/ext_reset_in]
connect_bd_net [get_bd_pins rst0/peripheral_aresetn] [get_bd_pins gpio_led/s_axi_aresetn]
set ic [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:smartconnect:*] end] ic0]
set_property -dict [list CONFIG.NUM_MI {1} CONFIG.NUM_SI {1}] $ic
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ic0/aclk]
connect_bd_net [get_bd_pins rst0/peripheral_aresetn] [get_bd_pins ic0/aresetn]
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins ic0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins ic0/M00_AXI] [get_bd_intf_pins gpio_led/S_AXI]
make_bd_pins_external [get_bd_pins gpio_led/gpio_io_o]
set_property name LD [get_bd_ports gpio_io_o_0]
assign_bd_address -offset 0x40000000 -range 4K [get_bd_addr_segs gpio_led/S_AXI/Reg]
validate_bd_design
save_bd_design
set wrap [make_wrapper -files [get_files zb_p0.bd] -top]
add_files -norecurse $wrap
set_property top zb_p0_wrapper [current_fileset]
add_files -fileset constrs_1 -norecurse $here/p0.xdc
generate_target all [get_files zb_p0.bd]
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
open_run impl_1
report_utilization -file $out/utilization.rpt
report_timing_summary -file $out/timing.rpt
report_power -file $out/power.rpt
report_drc -file $out/drc.rpt
write_hw_platform -fixed -force -include_bit -file $out/zb_p0.xsa
puts "P0-DONE"
