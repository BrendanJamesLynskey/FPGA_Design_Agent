# amd_ip_xvc.tcl (brief 131, build dbg_xvc only): the AMD IP of the debug path, created in flow/build.tcl's in-memory project next to ip/amd_ip.tcl's GT Wizard.
#   psu_xvc  Zynq UltraScale+ MPSoC (zynq_ultra_ps_e 3.5), default configuration: only its M_AXI_HPM0_LPD master (32-bit data) and pl_clk0 (100 MHz) are used here
#   apc_xvc  AXI Protocol Converter: the PS master's AXI4 (16-bit ID) to AXI4-Lite
#   dbb_xvc  Debug Bridge (debug_bridge 3.0), Bridge Type "From AXI to BSCAN" (PG245): the AXI-Lite slave drives a soft JTAG TAP that the ILA's debug hub uses
#   ila_xvc  Integrated Logic Analyzer (ila 6.2), one probe of 38 bits, 1024 samples, no storage qualification (a smaller ILA: the 4096-sample version was OOM-killed twice at the 6 GiB synthesis cap)
# Same helper as ip/amd_ip.tcl (global synthesis, no out-of-context checkpoint).
set_part $part
set fda_ip_dir [file join $out ip]
file mkdir $fda_ip_dir
proc fda_ip {vlnv name cfg} {
    global fda_ip_dir
    create_ip -vlnv $vlnv -module_name $name -dir $fda_ip_dir
    set ip [get_ips $name]
    if {[llength $cfg]} { set_property -dict $cfg $ip }
    set_property GENERATE_SYNTH_CHECKPOINT false [get_files [get_property IP_FILE $ip]]
    generate_target {synthesis instantiation_template} $ip
}
fda_ip xilinx.com:ip:zynq_ultra_ps_e:3.5 psu_xvc {}
fda_ip xilinx.com:ip:axi_protocol_converter:2.1 apc_xvc [list CONFIG.SI_PROTOCOL AXI4 CONFIG.MI_PROTOCOL AXI4LITE CONFIG.TRANSLATION_MODE 2 \
    CONFIG.ID_WIDTH 16 CONFIG.ADDR_WIDTH 32 CONFIG.DATA_WIDTH 32]
fda_ip xilinx.com:ip:debug_bridge:3.0 dbb_xvc [list CONFIG.C_DEBUG_MODE 2 CONFIG.C_DESIGN_TYPE 0]
fda_ip xilinx.com:ip:ila:6.2 ila_xvc [list CONFIG.C_NUM_OF_PROBES 1 CONFIG.C_PROBE0_WIDTH 38 CONFIG.C_DATA_DEPTH 1024 CONFIG.C_EN_STRG_QUAL 0 CONFIG.C_INPUT_PIPE_STAGES 1]
