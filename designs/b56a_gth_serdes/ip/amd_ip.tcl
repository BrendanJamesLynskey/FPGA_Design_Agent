# amd_ip.tcl (brief 56A): the GT Wizard core of designs/b56a_gth_serdes, created in flow/build.tcl's in-memory project
# (build.yaml ip_tcl). Global synthesis (no out-of-context checkpoint), as designs/b59a_axi_tx/ip/amd_ip.tcl.
#   gth_wiz  UltraScale FPGAs Transceivers Wizard 1.7 (gtwizard_ultrascale), GTHE4 channel X0Y6 of quad 224 (the KR260's SFP+
#            lane: RX pair T2/T1, TX pair R4/R3), RAW 64-bit user data on a 32-bit internal path, QPLL0 at 10.3125 Gb/s from a
#            156.25 MHz reference (MGTREFCLK0 of the quad), 100 MHz free-running clock, user clocks and reset helper in the core.
# The configuration is the one brief 56A's probe built on Vivado 2026.1 Basic (results/56a_serdes/probe/).
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
fda_ip xilinx.com:ip:gtwizard_ultrascale:1.7 gth_wiz [list \
    CONFIG.CHANNEL_ENABLE {X0Y6} CONFIG.TX_MASTER_CHANNEL {X0Y6} CONFIG.RX_MASTER_CHANNEL {X0Y6} \
    CONFIG.TX_LINE_RATE {10.3125} CONFIG.RX_LINE_RATE {10.3125} \
    CONFIG.TX_REFCLK_FREQUENCY {156.25} CONFIG.RX_REFCLK_FREQUENCY {156.25} \
    CONFIG.TX_PLL_TYPE {QPLL0} CONFIG.RX_PLL_TYPE {QPLL0} \
    CONFIG.TX_DATA_ENCODING {RAW} CONFIG.RX_DATA_DECODING {RAW} \
    CONFIG.TX_USER_DATA_WIDTH {64} CONFIG.TX_INT_DATA_WIDTH {32} CONFIG.RX_USER_DATA_WIDTH {64} CONFIG.RX_INT_DATA_WIDTH {32} \
    CONFIG.FREERUN_FREQUENCY {100} CONFIG.LOCATE_TX_USER_CLOCKING {CORE} CONFIG.LOCATE_RX_USER_CLOCKING {CORE} \
    CONFIG.TX_REFCLK_SOURCE {X0Y6 clk0} CONFIG.RX_REFCLK_SOURCE {X0Y6 clk0} \
    CONFIG.ENABLE_OPTIONAL_PORTS {loopback_in txprbssel_in rxprbssel_in txprbsforceerr_in rxprbserr_out rxprbslocked_out \
        rxprbscntreset_in drpaddr_in drpclk_in drpdi_in drpen_in drpwe_in drpdo_out drprdy_out eyescanreset_in eyescantrigger_in \
        eyescandataerror_out rxlpmen_in rxpolarity_in txpolarity_in txdiffctrl_in txpostcursor_in txprecursor_in rxcdrhold_in \
        txpippmen_in txpippmsel_in txpippmstepsize_in rxcdrlock_out txelecidle_in rxdfelpmreset_in}]
