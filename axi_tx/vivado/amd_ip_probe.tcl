# amd_ip_probe.tcl (brief 59A): do AMD's AXI protocol checker, AXI traffic generator and AXI BRAM controller build on this
# Vivado and licence tier? For each core: catalogue entry and REQUIRES_LICENSE, create_ip with the configuration 59A uses,
# generate_target, out-of-context synth_ip, utilisation. One "FDA-IP" line per core; nothing is programmed.
#   vivado -mode batch -source axi_tx/vivado/amd_ip_probe.tcl -tclargs <out dir>
lassign $argv out
file mkdir $out
set_param general.maxThreads 1
set_param synth.maxThreads 1
create_project -in_memory -part xc7a100tcsg324-1
set tier "n/a"
catch {set tier [get_vivado_tier]}
puts "FDA-IP VIVADO [version -short] TIER $tier"
proc probe {vlnv_glob name cfg} {
    global out
    set defs [get_ipdefs -all $vlnv_glob]
    if {[llength $defs] == 0} { puts "FDA-IP $name CATALOGUE absent"; return }
    set def [lindex [lsort $defs] end]
    set lic [get_property REQUIRES_LICENSE $def]
    puts "FDA-IP $name CATALOGUE $def REQUIRES_LICENSE $lic"
    set t0 [clock seconds]
    if {[catch {
        create_ip -vlnv $def -module_name $name -dir $out
        set ip [get_ips $name]
        if {[llength $cfg]} { set_property -dict $cfg $ip }
        generate_target all $ip
        synth_ip $ip
    } err]} {
        puts "FDA-IP $name BUILD FAIL [string map {"\n" " "} $err] (see the ERROR lines above in the log)"
        return
    }
    set dcp [glob -nocomplain $out/$name/$name.dcp]
    if {$dcp ne ""} {
        open_checkpoint $dcp
        report_utilization -file $out/${name}_util.rpt
        set lut [llength [get_cells -hier -filter {PRIMITIVE_GROUP == LUT}]]
        set ff  [llength [get_cells -hier -filter {PRIMITIVE_GROUP == FLOP_LATCH}]]
        set bram [llength [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM}]]
        close_design
        puts "FDA-IP $name BUILD PASS seconds [expr {[clock seconds]-$t0}] LUT $lut FF $ff BRAM $bram"
    } else {
        puts "FDA-IP $name BUILD PASS seconds [expr {[clock seconds]-$t0}] (no dcp found)"
    }
}
# AXI4-Lite, 32-bit data: the bus 59A checks
probe xilinx.com:ip:axi_protocol_checker:* amd_axi_pc {CONFIG.PROTOCOL AXI4LITE CONFIG.DATA_WIDTH 32 CONFIG.ADDR_WIDTH 32 CONFIG.HAS_SYSTEM_RESET 0}
probe xilinx.com:ip:axis_protocol_checker:* amd_axis_pc {CONFIG.TDATA_NUM_BYTES 4 CONFIG.HAS_TKEEP 1 CONFIG.HAS_TSTRB 1 CONFIG.HAS_TLAST 1}
probe xilinx.com:ip:axi_traffic_gen:* amd_atg {}
probe xilinx.com:ip:axi_bram_ctrl:* amd_bram_ctrl {CONFIG.PROTOCOL AXI4LITE CONFIG.SINGLE_PORT_BRAM 1 CONFIG.DATA_WIDTH 32 CONFIG.MEM_DEPTH 2048}
probe xilinx.com:ip:blk_mem_gen:* amd_bram {CONFIG.Memory_Type Single_Port_RAM CONFIG.Use_BRAM_Block BRAM_Controller CONFIG.Enable_32bit_Address true CONFIG.Use_Byte_Write_Enable true CONFIG.Byte_Size 8 CONFIG.Write_Width_A 32 CONFIG.Write_Depth_A 2048 CONFIG.Register_PortA_Output_of_Memory_Primitives false CONFIG.Use_RSTA_Pin true}
puts "FDA-IP DONE"
