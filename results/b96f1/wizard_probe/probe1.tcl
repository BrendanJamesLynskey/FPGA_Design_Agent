# probe1.tcl (brief 96F1 stage 0): list every Wizard property, then try buffer bypass. Every step in catch: brief 97's probe wrote nothing.
# Run: vivado -mode batch -source probe1.tcl -tclargs <outdir>
lassign $argv outdir
file mkdir $outdir
proc say {f msg} { puts $f $msg; flush $f; puts $msg }
set fo [open $outdir/probe1.txt w]
create_project -in_memory -part xck26-sfvc784-2LV-c
set base [list \
    CONFIG.CHANNEL_ENABLE {X0Y6} CONFIG.TX_MASTER_CHANNEL {X0Y6} CONFIG.RX_MASTER_CHANNEL {X0Y6} \
    CONFIG.TX_LINE_RATE {10.3125} CONFIG.RX_LINE_RATE {10.3125} CONFIG.TX_REFCLK_FREQUENCY {156.25} CONFIG.RX_REFCLK_FREQUENCY {156.25} \
    CONFIG.TX_PLL_TYPE {QPLL0} CONFIG.RX_PLL_TYPE {QPLL0} CONFIG.TX_DATA_ENCODING {RAW} CONFIG.RX_DATA_DECODING {RAW} \
    CONFIG.TX_USER_DATA_WIDTH {64} CONFIG.TX_INT_DATA_WIDTH {32} CONFIG.RX_USER_DATA_WIDTH {64} CONFIG.RX_INT_DATA_WIDTH {32} \
    CONFIG.FREERUN_FREQUENCY {100} CONFIG.LOCATE_TX_USER_CLOCKING {CORE} CONFIG.LOCATE_RX_USER_CLOCKING {CORE} \
    CONFIG.TX_REFCLK_SOURCE {X0Y6 clk0} CONFIG.RX_REFCLK_SOURCE {X0Y6 clk0}]
set d [file join [pwd] ip_probe1]
file mkdir $d
say $fo "step create_ip: [catch {create_ip -vlnv xilinx.com:ip:gtwizard_ultrascale:1.7 -module_name gth_probe -dir $d} m] $m"
set ip [get_ips gth_probe]
say $fo "step set base: [catch {set_property -dict $base $ip} m] $m"
say $fo "=== ALL CONFIG properties (default + base) ==="
foreach p [lsort [list_property $ip -regexp {CONFIG\..*}]] { say $fo "$p = [get_property $p $ip]" }
close $fo
