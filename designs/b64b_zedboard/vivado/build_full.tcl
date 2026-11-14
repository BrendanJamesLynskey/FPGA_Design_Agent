# build_full.tcl: the ZedBoard HW/SW design (brief 64B), Vivado 2026.1. One bitstream with: the PS7 (GP0 master, HP0 and ACP
# slaves, FCLK0 100 MHz, IRQ_F2P), zb_ctrl (crossbar + latency probe + bus-error blocks), two chains of
# AXI DMA -> zb_accel -> AXI DMA (chain 0 on HP0, chain 1 on the ACP).
#   vivado -mode batch -source build_full.tcl -tclargs <out dir> <repo root>
set_param general.maxThreads 2
set_param synth.maxThreads 2
set_param chipscope.maxJobs 1
set here [file dirname [file normalize [info script]]]
source $here/ps7_zedboard.tcl
set out [lindex $argv 0]
set repo [lindex $argv 1]
set d $repo/designs/b64b_zedboard
file mkdir $out
create_project -force zbf $out/proj -part xc7z020clg484-1
add_files -norecurse [glob $d/rtl/*.sv] [glob $d/gen/regs/*.sv] [glob $repo/ip_lib/axil_xbar/rtl/*.sv] [glob $repo/ip_lib/fir/rtl/*.sv]
set_property file_type SystemVerilog [get_files *.sv]
update_compile_order -fileset sources_1
create_bd_design zb_hwsw
set ps [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:processing_system7:*] end] ps7]
zb_config_ps7 $ps [list \
    CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
    CONFIG.PCW_USE_S_AXI_ACP {1} \
    CONFIG.PCW_USE_FABRIC_INTERRUPT {1} CONFIG.PCW_IRQ_F2P_INTR {1}]
make_bd_intf_pins_external [get_bd_intf_pins ps7/DDR]
make_bd_intf_pins_external [get_bd_intf_pins ps7/FIXED_IO]
set rst0 [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:proc_sys_reset:*] end] rst0]
create_bd_cell -type module -reference zb_ctrl ctrl
create_bd_cell -type module -reference zb_accel acc0
create_bd_cell -type module -reference zb_accel acc1
set conv [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:axi_protocol_converter:*] end] conv]
set_property -dict [list CONFIG.SI_PROTOCOL {AXI3} CONFIG.MI_PROTOCOL {AXI4LITE}] $conv
foreach n {0 1} {
    set dma [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:axi_dma:*] end] dma$n]
    set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_sg_length_width {23} \
        CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axi_s2mm_data_width {64} \
        CONFIG.c_m_axis_mm2s_tdata_width {32} CONFIG.c_mm2s_burst_size {16} CONFIG.c_s2mm_burst_size {16}] $dma
    set sc [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:smartconnect:*] end] sc$n]
    set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] $sc
    connect_bd_intf_net [get_bd_intf_pins dma$n/M_AXI_MM2S] [get_bd_intf_pins sc$n/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins dma$n/M_AXI_S2MM] [get_bd_intf_pins sc$n/S01_AXI]
    connect_bd_intf_net [get_bd_intf_pins dma$n/M_AXIS_MM2S] [get_bd_intf_pins acc$n/s_axis]
    connect_bd_intf_net [get_bd_intf_pins acc$n/m_axis] [get_bd_intf_pins dma$n/S_AXIS_S2MM]
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins dma$n/s_axi_lite_aclk] [get_bd_pins dma$n/m_axi_mm2s_aclk] [get_bd_pins dma$n/m_axi_s2mm_aclk] [get_bd_pins sc$n/aclk] [get_bd_pins acc$n/aclk]
    connect_bd_net [get_bd_pins rst0/peripheral_aresetn] [get_bd_pins dma$n/axi_resetn] [get_bd_pins sc$n/aresetn] [get_bd_pins acc$n/aresetn]
}
connect_bd_intf_net [get_bd_intf_pins sc0/M00_AXI] [get_bd_intf_pins ps7/S_AXI_HP0]
connect_bd_intf_net [get_bd_intf_pins sc1/M00_AXI] [get_bd_intf_pins ps7/S_AXI_ACP]
# the ACP is coherent for a request with AxUSER[0] = 1 and AxCACHE[1] = 1 (the DMA drives AxCACHE = 0011)
set one [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:xlconstant:*] end] acp_user]
set_property -dict [list CONFIG.CONST_WIDTH {5} CONFIG.CONST_VAL {1}] $one
connect_bd_net [get_bd_pins acp_user/dout] [get_bd_pins ps7/S_AXI_ACP_ARUSER] [get_bd_pins ps7/S_AXI_ACP_AWUSER]
# control plane
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins conv/S_AXI]
connect_bd_intf_net [get_bd_intf_pins conv/M_AXI] [get_bd_intf_pins ctrl/s_axil]
connect_bd_intf_net [get_bd_intf_pins ctrl/m_dma0] [get_bd_intf_pins dma0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins ctrl/m_dma1] [get_bd_intf_pins dma1/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins ctrl/m_acc0] [get_bd_intf_pins acc0/s_axil]
connect_bd_intf_net [get_bd_intf_pins ctrl/m_acc1] [get_bd_intf_pins acc1/s_axil]
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins ps7/S_AXI_HP0_ACLK] [get_bd_pins ps7/S_AXI_ACP_ACLK] \
    [get_bd_pins rst0/slowest_sync_clk] [get_bd_pins conv/aclk] [get_bd_pins ctrl/aclk]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins rst0/ext_reset_in]
connect_bd_net [get_bd_pins rst0/peripheral_aresetn] [get_bd_pins conv/aresetn] [get_bd_pins ctrl/aresetn]
# interrupts into IRQ_F2P: [0] latency probe (GIC ID 61), [1] DMA 0 S2MM (62), [2] DMA 1 S2MM (63)
set cc [create_bd_cell -type ip -vlnv [lindex [get_ipdefs xilinx.com:ip:xlconcat:*] end] irqs]
set_property -dict [list CONFIG.NUM_PORTS {3}] $cc
connect_bd_net [get_bd_pins ctrl/irq_lat] [get_bd_pins irqs/In0]
connect_bd_net [get_bd_pins dma0/s2mm_introut] [get_bd_pins irqs/In1]
connect_bd_net [get_bd_pins dma1/s2mm_introut] [get_bd_pins irqs/In2]
connect_bd_net [get_bd_pins irqs/dout] [get_bd_pins ps7/IRQ_F2P]
make_bd_pins_external [get_bd_pins ctrl/led]
set_property name LD [get_bd_ports led_0]
assign_bd_address
validate_bd_design
save_bd_design
set wrap [make_wrapper -files [get_files zb_hwsw.bd] -top]
add_files -norecurse $wrap
set_property top zb_hwsw_wrapper [current_fileset]
add_files -fileset constrs_1 -norecurse $here/full.xdc
generate_target all [get_files zb_hwsw.bd]
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
open_run impl_1
report_utilization -file $out/utilization.rpt
report_timing_summary -file $out/timing.rpt
report_power -file $out/power.rpt
report_drc -file $out/drc.rpt
report_methodology -file $out/methodology.rpt
write_hw_platform -fixed -force -include_bit -file $out/zb_hwsw.xsa
write_bd_tcl -force $out/zb_hwsw_bd.tcl
puts "FULL-DONE"
