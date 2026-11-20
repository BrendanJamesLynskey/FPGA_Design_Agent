# probe3.tcl (brief 96F1 stage 0): generate the design's Wizard core twice (buffers on = as built today; both buffers bypassed) and keep the generated
# sources for comparison. Run: vivado -mode batch -source probe3.tcl -tclargs <outdir>
lassign $argv outdir
file mkdir $outdir
set fo [open $outdir/probe3.txt w]
proc say {msg} { global fo; puts $fo $msg; flush $fo; puts $msg }
set opt {loopback_in txprbssel_in rxprbssel_in txprbsforceerr_in rxprbserr_out rxprbslocked_out rxprbscntreset_in drpaddr_in drpclk_in drpdi_in drpen_in drpwe_in drpdo_out drprdy_out eyescanreset_in eyescantrigger_in eyescandataerror_out rxlpmen_in rxpolarity_in txpolarity_in txdiffctrl_in txpostcursor_in txprecursor_in rxcdrhold_in txpippmen_in txpippmsel_in txpippmstepsize_in rxcdrlock_out txelecidle_in rxdfelpmreset_in txbufstatus_out rxbufstatus_out}
set base [list \
    CONFIG.CHANNEL_ENABLE {X0Y6} CONFIG.TX_MASTER_CHANNEL {X0Y6} CONFIG.RX_MASTER_CHANNEL {X0Y6} \
    CONFIG.TX_LINE_RATE {10.3125} CONFIG.RX_LINE_RATE {10.3125} CONFIG.TX_REFCLK_FREQUENCY {156.25} CONFIG.RX_REFCLK_FREQUENCY {156.25} \
    CONFIG.TX_PLL_TYPE {QPLL0} CONFIG.RX_PLL_TYPE {QPLL0} CONFIG.TX_DATA_ENCODING {RAW} CONFIG.RX_DATA_DECODING {RAW} \
    CONFIG.TX_USER_DATA_WIDTH {64} CONFIG.TX_INT_DATA_WIDTH {32} CONFIG.RX_USER_DATA_WIDTH {64} CONFIG.RX_INT_DATA_WIDTH {32} \
    CONFIG.FREERUN_FREQUENCY {100} CONFIG.LOCATE_TX_USER_CLOCKING {CORE} CONFIG.LOCATE_RX_USER_CLOCKING {CORE} \
    CONFIG.TX_REFCLK_SOURCE {X0Y6 clk0} CONFIG.RX_REFCLK_SOURCE {X0Y6 clk0} CONFIG.ENABLE_OPTIONAL_PORTS $opt]
create_project -in_memory -part xck26-sfvc784-2LV-c
set d [file join [pwd] ip_gen]
file mkdir $d
foreach {name extra} [list gth_buf {} gth_byp {CONFIG.TX_BUFFER_MODE 0 CONFIG.RX_BUFFER_MODE 0}] {
    create_ip -vlnv xilinx.com:ip:gtwizard_ultrascale:1.7 -module_name $name -dir $d
    set ip [get_ips $name]
    set_property -dict $base $ip
    if {$extra ne {}} { set_property -dict $extra $ip }
    say "$name: freerun after set = [get_property CONFIG.FREERUN_FREQUENCY $ip]"
    catch {set_property CONFIG.FREERUN_FREQUENCY {100} $ip}
    say "$name: freerun forced to [get_property CONFIG.FREERUN_FREQUENCY $ip]; TX_OUTCLK=[get_property CONFIG.TX_OUTCLK_SOURCE $ip] TXBUF=[get_property CONFIG.TX_BUFFER_MODE $ip] RXBUF=[get_property CONFIG.RX_BUFFER_MODE $ip]"
    set_property GENERATE_SYNTH_CHECKPOINT false [get_files [get_property IP_FILE $ip]]
    say "$name generate_target: [catch {generate_target {synthesis instantiation_template} $ip} m] $m"
}
close $fo
