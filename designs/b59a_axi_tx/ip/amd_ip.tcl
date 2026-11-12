# amd_ip.tcl (brief 59A): the AMD IP of designs/b59a_axi_tx, created in flow/build.tcl's in-memory project (build.yaml
# ip_tcl). Global synthesis (no out-of-context checkpoint): the cores are synthesised with the top in one synth_design.
#   amd_bram_ctrl  AXI BRAM Controller 4.1, AXI4-Lite, 32-bit, single port, 8 KB (2048 words)
#   amd_bram       Block Memory Generator 8.4 in BRAM Controller mode, single port, byte writes, 32 x 2048
#   amd_axi_pc     AXI Protocol Checker 2.0 on AXI4-Lite, 32-bit data, 32-bit address: the cross-check
# The configuration is the one brief 59A's probe built on Vivado 2026.1 Basic (axi_tx/vivado/amd_ip_probe.tcl).
set_part $part
set fda_ip_dir [file join $out ip]
file mkdir $fda_ip_dir
proc fda_ip {vlnv name cfg} {
    global fda_ip_dir
    create_ip -vlnv $vlnv -module_name $name -dir $fda_ip_dir
    set ip [get_ips $name]
    set_property -dict $cfg $ip
    set_property GENERATE_SYNTH_CHECKPOINT false [get_files [get_property IP_FILE $ip]]
    generate_target {synthesis instantiation_template} $ip
}
fda_ip xilinx.com:ip:axi_bram_ctrl:4.1 amd_bram_ctrl {CONFIG.PROTOCOL AXI4LITE CONFIG.SINGLE_PORT_BRAM 1 CONFIG.DATA_WIDTH 32 CONFIG.MEM_DEPTH 2048}
fda_ip xilinx.com:ip:blk_mem_gen:8.4 amd_bram {CONFIG.Memory_Type Single_Port_RAM CONFIG.Use_BRAM_Block BRAM_Controller CONFIG.Enable_32bit_Address true CONFIG.Use_Byte_Write_Enable true CONFIG.Byte_Size 8 CONFIG.Write_Width_A 32 CONFIG.Write_Depth_A 2048 CONFIG.Register_PortA_Output_of_Memory_Primitives false CONFIG.Use_RSTA_Pin true}
fda_ip xilinx.com:ip:axi_protocol_checker:2.0 amd_axi_pc {CONFIG.PROTOCOL AXI4LITE CONFIG.DATA_WIDTH 32 CONFIG.ADDR_WIDTH 32 CONFIG.HAS_SYSTEM_RESET 0}
