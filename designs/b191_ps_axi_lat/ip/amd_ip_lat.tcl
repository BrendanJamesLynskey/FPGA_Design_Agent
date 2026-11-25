# amd_ip_lat.tcl (brief 191, build ps_axi_lat only): the AMD IP of the latency image, created in flow/build.tcl's in-memory project (same helper as ip/amd_ip_xvc.tcl of dbg_xvc).
#   psu_lat  Zynq UltraScale+ MPSoC (zynq_ultra_ps_e 3.5): M_AXI_HPM0_FPD (maxigp0) and M_AXI_HPM0_LPD (maxigp2) enabled and 32 bits wide, M_AXI_HPM1_FPD off, pl_clk0 at 100 MHz.
#            Every other setting is the IP's default (the KR260 board preset is not applied: nothing but the two masters and the clock is used).
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
fda_ip xilinx.com:ip:zynq_ultra_ps_e:3.5 psu_lat [list \
    CONFIG.PSU__USE__M_AXI_GP0 1 CONFIG.PSU__USE__M_AXI_GP1 0 CONFIG.PSU__USE__M_AXI_GP2 1 \
    CONFIG.PSU__MAXIGP0__DATA_WIDTH 32 CONFIG.PSU__MAXIGP2__DATA_WIDTH 32 \
    CONFIG.PSU__FPGA_PL0_ENABLE 1 CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ 100]
