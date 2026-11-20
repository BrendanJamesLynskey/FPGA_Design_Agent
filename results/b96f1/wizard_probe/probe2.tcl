# probe2.tcl (brief 96F1 stage 0): which Wizard settings give TX/RX buffer bypass for the design's 10GBASE-R configuration, what ports and
# wrapper the core then has, and are dynamic QPLL fractional-N (SDM) ports reachable. Every step is in catch so a failure leaves a trace
# (brief 97's probe left an empty file).  Run: vivado -mode batch -source probe2.tcl -tclargs <outdir>
lassign $argv outdir
file mkdir $outdir
set fo [open $outdir/probe2.txt w]
proc say {msg} { global fo; puts $fo $msg; flush $fo; puts $msg }
proc props {ip} { set r {}; foreach p [lsort [list_property $ip -regexp {CONFIG\..*}]] { lappend r $p [get_property $p $ip] }; return $r }
proc diffprops {a b} {
    array set A $a; array set B $b
    foreach k [lsort [array names B]] { if {![info exists A($k)]} { say "  + $k = $B($k)" } elseif {$A($k) ne $B($k)} { say "  ~ $k : $A($k) -> $B($k)" } }
    foreach k [lsort [array names A]] { if {![info exists B($k)]} { say "  - $k (was $A($k))" } }
}
set opt {loopback_in txprbssel_in rxprbssel_in txprbsforceerr_in rxprbserr_out rxprbslocked_out rxprbscntreset_in drpaddr_in drpclk_in drpdi_in drpen_in drpwe_in drpdo_out drprdy_out eyescanreset_in eyescantrigger_in eyescandataerror_out rxlpmen_in rxpolarity_in txpolarity_in txdiffctrl_in txpostcursor_in txprecursor_in rxcdrhold_in txpippmen_in txpippmsel_in txpippmstepsize_in rxcdrlock_out txelecidle_in rxdfelpmreset_in txbufstatus_out rxbufstatus_out}
set base [list \
    CONFIG.CHANNEL_ENABLE {X0Y6} CONFIG.TX_MASTER_CHANNEL {X0Y6} CONFIG.RX_MASTER_CHANNEL {X0Y6} \
    CONFIG.TX_LINE_RATE {10.3125} CONFIG.RX_LINE_RATE {10.3125} CONFIG.TX_REFCLK_FREQUENCY {156.25} CONFIG.RX_REFCLK_FREQUENCY {156.25} \
    CONFIG.TX_PLL_TYPE {QPLL0} CONFIG.RX_PLL_TYPE {QPLL0} CONFIG.TX_DATA_ENCODING {RAW} CONFIG.RX_DATA_DECODING {RAW} \
    CONFIG.TX_USER_DATA_WIDTH {64} CONFIG.TX_INT_DATA_WIDTH {32} CONFIG.RX_USER_DATA_WIDTH {64} CONFIG.RX_INT_DATA_WIDTH {32} \
    CONFIG.FREERUN_FREQUENCY {100} CONFIG.LOCATE_TX_USER_CLOCKING {CORE} CONFIG.LOCATE_RX_USER_CLOCKING {CORE} \
    CONFIG.TX_REFCLK_SOURCE {X0Y6 clk0} CONFIG.RX_REFCLK_SOURCE {X0Y6 clk0} CONFIG.ENABLE_OPTIONAL_PORTS $opt]
create_project -in_memory -part xck26-sfvc784-2LV-c
set d [file join [pwd] ip_probe2]
file mkdir $d
create_ip -vlnv xilinx.com:ip:gtwizard_ultrascale:1.7 -module_name gth_probe -dir $d
set ip [get_ips gth_probe]
set_property -dict $base $ip
say "validate base: [catch {validate_ip $ip} m] $m"
set P0 [props $ip]
say "=== allowed values of selected properties (list_property_value) ==="
foreach p {TX_BUFFER_MODE RX_BUFFER_MODE RX_BUFFER_BYPASS_MODE TX_OUTCLK_SOURCE RX_OUTCLK_SOURCE LOCATE_TX_BUFFER_BYPASS_CONTROLLER LOCATE_RX_BUFFER_BYPASS_CONTROLLER TX_QPLL_FRACN_NUMERATOR RX_QPLL_FRACN_NUMERATOR RX_SLIDE_MODE RX_RECCLK_OUTPUT TXPROGDIV_FREQ_ENABLE ENABLE_OPTIONAL_PORTS LOCATE_TX_USER_CLOCKING LOCATE_RX_USER_CLOCKING} {
    say "CONFIG.$p : [catch {list_property_value CONFIG.$p $ip} v] $v"
}
say "=== stage A: TX_BUFFER_MODE 0 only ==="
say "set: [catch {set_property CONFIG.TX_BUFFER_MODE {0} $ip} m] $m"
set PA [props $ip]; diffprops $P0 $PA
say "validate: [catch {validate_ip $ip} m] $m"
say "=== stage B: + RX_BUFFER_MODE 0 ==="
say "set: [catch {set_property CONFIG.RX_BUFFER_MODE {0} $ip} m] $m"
set PB [props $ip]; diffprops $PA $PB
say "validate: [catch {validate_ip $ip} m] $m"
say "=== allowed values after bypass ==="
foreach p {TX_BUFFER_BYPASS_MODE RX_BUFFER_BYPASS_MODE TX_OUTCLK_SOURCE RX_OUTCLK_SOURCE} {
    say "CONFIG.$p : [catch {list_property_value CONFIG.$p $ip} v] $v  (value: [catch {get_property CONFIG.$p $ip} g] $g)"
}
say "=== try alternatives (each from the stage B state; reverted) ==="
foreach {n v} {RX_BUFFER_BYPASS_MODE SINGLE TX_BUFFER_BYPASS_MODE SINGLE TX_BUFFER_BYPASS_MODE MULTI TX_OUTCLK_SOURCE TXPROGDIVCLK TX_OUTCLK_SOURCE TXOUTCLKPMA RX_OUTCLK_SOURCE RXOUTCLKPMA RX_OUTCLK_SOURCE RXPROGDIVCLK} {
    set old [catch {get_property CONFIG.$n $ip} o]
    say "set $n=$v: [catch {set_property CONFIG.$n $v $ip} m] $m  -> now [catch {get_property CONFIG.$n $ip} g] $g ; validate: [catch {validate_ip $ip} m2] $m2"
    catch {set_property CONFIG.$n $o $ip}
}
say "=== fractional-N: set TX/RX_QPLL_FRACN_NUMERATOR 1000 ==="
say "set: [catch {set_property -dict {CONFIG.TX_QPLL_FRACN_NUMERATOR 1000 CONFIG.RX_QPLL_FRACN_NUMERATOR 1000} $ip} m] $m"
set PC [props $ip]; diffprops $PB $PC
say "validate: [catch {validate_ip $ip} m] $m"
catch {set_property -dict {CONFIG.TX_QPLL_FRACN_NUMERATOR 0 CONFIG.RX_QPLL_FRACN_NUMERATOR 0} $ip}
say "=== generate_target on both variants; port lists compared ==="
puts $fo "(see ports_*.txt and the generated wrapper directories)"
close $fo
