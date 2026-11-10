# wizard_probe.tcl: which wizard results can be read back in batch, with no GUI? (brief 18, section 2b)
#   cd <scratch dir> && vivado -mode batch -source flow/wizard_probe.tcl -tclargs <out dir>   (the block design writes .srcs and clockInfo.txt into the cwd)
# One section per wizard: create_ip (or the batch equivalent), set CONFIG.*, read back, generate output products, and
# record what came back in <out dir>/wizards.txt (one block per wizard, "OK" / "FAIL" lines).
set_param general.maxThreads 1
set out [file normalize [lindex $argv 0]]
file mkdir $out
set lf [open $out/wizards.txt w]
proc log {args} { global lf; puts $lf [join $args " "]; flush $lf }
proc props_like {obj pats} {
    set r {}
    foreach p [lsort [list_property $obj]] {
        foreach pat $pats { if {[string match -nocase $pat $p]} { lappend r "$p = [get_property $p $obj]"; break } }
    }
    return $r
}
proc section {name body} {
    log "\n== $name"
    if {[catch {uplevel 1 $body} err]} { log "FAIL: [string map [list \n { }] $err]" }
}

# ---- Artix-7 IP wizards ------------------------------------------------------------------------------------
create_project -in_memory -part xc7a100tcsg324-1

section "Block Memory Generator" {
    set d $out/ip_bmg; file mkdir $d
    create_ip -name blk_mem_gen -vendor xilinx.com -library ip -module_name bmg -dir $d
    set_property -dict [list CONFIG.Memory_Type True_Dual_Port_RAM CONFIG.Write_Width_A 32 CONFIG.Write_Depth_A 4096 \
        CONFIG.Read_Width_A 32 CONFIG.Write_Width_B 32 CONFIG.Read_Width_B 32 CONFIG.Enable_32bit_Address false] [get_ips bmg]
    log "OK set_property"
    foreach l [props_like [get_ips bmg] {CONFIG.*Latency* CONFIG.*Primitive* CONFIG.*Resource* CONFIG.*BRAM* CONFIG.Memory_Type CONFIG.Write_Depth_A CONFIG.Register_PortA* CONFIG.Operating_Mode_A}] { log "  $l" }
    generate_target all [get_ips bmg]
    log "OK generate_target; XDC files: [glob -nocomplain -directory $d -types f */*.xdc]"
}
section "FIFO Generator" {
    set d $out/ip_fifo; file mkdir $d
    create_ip -name fifo_generator -vendor xilinx.com -library ip -module_name fg -dir $d
    set_property -dict [list CONFIG.Fifo_Implementation Independent_Clocks_Block_RAM CONFIG.Input_Data_Width 32 CONFIG.Input_Depth 1024 \
        CONFIG.Performance_Options First_Word_Fall_Through] [get_ips fg]
    log "OK set_property"
    foreach l [props_like [get_ips fg] {CONFIG.Output_Depth CONFIG.Full_Threshold* CONFIG.Data_Count* CONFIG.Read_Data_Count_Width CONFIG.Write_Data_Count_Width CONFIG.Reset_Type CONFIG.Synchronization_Stages* CONFIG.Fifo_Implementation CONFIG.Output_Data_Width}] { log "  $l" }
    generate_target all [get_ips fg]
    set x [glob -nocomplain -directory $d -types f */*.xdc]
    log "OK generate_target; XDC files: $x"
    foreach f $x { if {![string match *_ooc.xdc $f]} { log "  --- $f"; set fh [open $f]; log [string range [read $fh] 0 1500]; close $fh } }
}
section "XADC Wizard" {
    set d $out/ip_xadc; file mkdir $d
    create_ip -name xadc_wiz -vendor xilinx.com -library ip -module_name xw -dir $d
    set_property -dict [list CONFIG.XADC_STARUP_SELECTION channel_sequencer CONFIG.ENABLE_TEMP_BUS false] [get_ips xw]
    log "OK set_property"
    foreach l [props_like [get_ips xw] {CONFIG.*SEQ* CONFIG.*ALARM* CONFIG.DCLK* CONFIG.ADC_CONVERSION_RATE CONFIG.XADC_STARUP_SELECTION CONFIG.TIMING_MODE CONFIG.CHANNEL_ENABLE_*}] { log "  $l" }
    generate_target all [get_ips xw]
    log "OK generate_target"
}
section "Transceivers Wizard (Artix-7 GTP)" {
    set d $out/ip_gt; file mkdir $d
    log "gtwizard IPs in catalog: [get_ipdefs -filter {NAME =~ *gtwizard*}]"
    log "gt (7 series) IPs: [get_ipdefs -filter {NAME =~ *gt* && NAME !~ *gtwizard_ultra* }]"
}
section "Set Up Debug (ILA / VIO IP)" {
    set d $out/ip_ila; file mkdir $d
    create_ip -name ila -vendor xilinx.com -library ip -module_name ila0 -dir $d
    set_property -dict [list CONFIG.C_NUM_OF_PROBES 2 CONFIG.C_PROBE0_WIDTH 8 CONFIG.C_DATA_DEPTH 2048] [get_ips ila0]
    log "OK ila IP set_property (the agent's flow/debug.tcl uses create_debug_core instead)"
    log "  create_debug_core exists: [expr {[llength [info commands create_debug_core]] > 0}]; connect_debug_port: [expr {[llength [info commands connect_debug_port]] > 0}]; implement_debug_core: [expr {[llength [info commands implement_debug_core]] > 0}]"
}

# ---- commands that stand in for GUI wizards ---------------------------------------------------------------------
section "Timing Constraints Wizard (any Tcl command?)" {
    foreach pat {*wizard* *recommend* *constraints* create_timing* *auto_constr*} {
        log "info commands $pat: [lsort [info commands $pat]]"
    }
}
section "I/O Planning" {
    foreach c {place_ports report_ssn report_io report_drc open_io_design create_property get_package_pins write_csv read_csv} {
        log "$c: [expr {[llength [info commands $c]] > 0}]"
    }
}
section "Example design (Open Example Project)" {
    log "open_example_project: [expr {[llength [info commands open_example_project]] > 0}]; list_example_designs: [expr {[llength [info commands get_example_designs]] > 0}]"
}
close_project

# ---- Zynq PS7 configuration and block automation -----------------------------------------------------------------
create_project -in_memory -part xc7z020clg484-1
section "Zynq PS7 configuration (IP, no block design)" {
    set d $out/ip_ps7; file mkdir $d
    create_ip -name processing_system7 -vendor xilinx.com -library ip -module_name ps0 -dir $d
    set_property -dict [list CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ 100 CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41J256M8 HX-15E} \
        CONFIG.PCW_UIPARAM_DDR_MEMORY_TYPE {DDR 3} CONFIG.PCW_QSPI_PERIPHERAL_ENABLE 1] [get_ips ps0]
    log "OK set_property"
    foreach l [props_like [get_ips ps0] {CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ CONFIG.PCW_ACT_APU_PERIPHERAL_FREQMHZ CONFIG.PCW_UIPARAM_DDR_FREQ_MHZ CONFIG.PCW_UIPARAM_DDR_BUS_WIDTH CONFIG.PCW_UIPARAM_DDR_PARTNO CONFIG.PCW_UIPARAM_DDR_DEVICE_CAPACITY CONFIG.PCW_UIPARAM_DDR_TRAIN_*}] { log "  $l" }
    generate_target all [get_ips ps0]
    log "OK generate_target"
}
section "Block automation and address editor (batch)" {
    create_bd_design bd1
    set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7]
    apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} $ps
    set g [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio gpio0]
    apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master "/ps7/M_AXI_GP0" Clk "Auto"} [get_bd_intf_pins gpio0/S_AXI]
    assign_bd_address
    log "OK processing_system7 block automation + AXI connection automation + assign_bd_address"
    log "  cells: [get_bd_cells]"
    log "  address segments: [llength [get_bd_addr_segs]]"
    log "  segment gpio0: [get_property OFFSET [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *gpio0*}]]"
    validate_bd_design
    log "OK validate_bd_design"
    close_bd_design bd1
}
close $lf
