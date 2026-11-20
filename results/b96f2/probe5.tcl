# probe5.tcl (brief 96F2): generate the AMD Transceiver Wizard EXAMPLE DESIGN for the b96 bypass core (and the LOCATE_COMMON = EXAMPLE_DESIGN variant) so the way it drives the buffer-bypass
# controllers' reset/start and uses done/error can be read. No synthesis, no implementation. Run: vivado -mode batch -source probe5.tcl -tclargs <outdir>
lassign $argv outdir
file mkdir $outdir
set fo [open $outdir/probe5.txt w]
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
set d [file join [pwd] ip5]
file mkdir $d
foreach {name extra} [list gth_ex_in {CONFIG.TX_BUFFER_MODE 0 CONFIG.RX_BUFFER_MODE 0} gth_ex_xc {CONFIG.TX_BUFFER_MODE 0 CONFIG.RX_BUFFER_MODE 0 CONFIG.LOCATE_COMMON EXAMPLE_DESIGN}] {
    say "== $name"
    say "create_ip: [catch {create_ip -vlnv xilinx.com:ip:gtwizard_ultrascale:1.7 -module_name $name -dir $d} m] $m"
    set ip [get_ips $name]
    say "base: [catch {set_property -dict $base $ip} m] $m"
    say "extra: [catch {set_property -dict $extra $ip} m] $m"
    catch {set_property CONFIG.FREERUN_FREQUENCY {100} $ip}
    set_property GENERATE_SYNTH_CHECKPOINT false [get_files [get_property IP_FILE $ip]]
    say "generate_target: [catch {generate_target all $ip} m] $m"
    set ed [file join $outdir ex_$name]
    say "open_example_project: [catch {open_example_project -in_process -force -dir $ed $ip} m] $m"
    catch {close_project}
    create_project -in_memory -part xck26-sfvc784-2LV-c
    # re-add the IP for the next variant
    set d [file join [pwd] ip5_[string range $name 7 end]]
    file mkdir $d
}
close $fo
