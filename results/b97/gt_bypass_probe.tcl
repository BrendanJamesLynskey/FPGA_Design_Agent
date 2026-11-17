# gt_bypass_probe.tcl (brief 97): can the 56A GT Wizard configuration be switched to TX and RX buffer bypass in Vivado 2026.1,
# which properties does it have for that, and what ports does the core then add? Generates a core in a scratch in-memory project (no
# bitstream, no board). Run: vivado -mode batch -source gt_bypass_probe.tcl -tclargs <out.txt>
lassign $argv out
set fo [open $out w]
create_project -in_memory -part xck26-sfvc784-2LV-c
set base [list \
    CONFIG.CHANNEL_ENABLE {X0Y6} CONFIG.TX_MASTER_CHANNEL {X0Y6} CONFIG.RX_MASTER_CHANNEL {X0Y6} \
    CONFIG.TX_LINE_RATE {10.3125} CONFIG.RX_LINE_RATE {10.3125} CONFIG.TX_REFCLK_FREQUENCY {156.25} CONFIG.RX_REFCLK_FREQUENCY {156.25} \
    CONFIG.TX_PLL_TYPE {QPLL0} CONFIG.RX_PLL_TYPE {QPLL0} CONFIG.TX_DATA_ENCODING {RAW} CONFIG.RX_DATA_DECODING {RAW} \
    CONFIG.TX_USER_DATA_WIDTH {64} CONFIG.TX_INT_DATA_WIDTH {32} CONFIG.RX_USER_DATA_WIDTH {64} CONFIG.RX_INT_DATA_WIDTH {32} \
    CONFIG.FREERUN_FREQUENCY {100} CONFIG.LOCATE_TX_USER_CLOCKING {CORE} CONFIG.LOCATE_RX_USER_CLOCKING {CORE} \
    CONFIG.TX_REFCLK_SOURCE {X0Y6 clk0} CONFIG.RX_REFCLK_SOURCE {X0Y6 clk0}]
file mkdir [pwd]/ip_probe
create_ip -vlnv xilinx.com:ip:gtwizard_ultrascale:1.7 -module_name gth_probe -dir [pwd]/ip_probe
set ip [get_ips gth_probe]
set_property -dict $base $ip
puts $fo "=== properties of the Wizard whose name mentions BUFFER, BYPASS, SYNC or LATENCY ==="
foreach p [lsort [list_property $ip -regexp {CONFIG\.(TX|RX|LOCATE).*(BUFFER|BYPASS|SYNC).*}]] {
    puts $fo "$p = [get_property $p $ip]"
}
puts $fo "=== ports of the default core (buffer on) ==="
catch {generate_target {instantiation_template} $ip}
set base_ports [get_property NAME [get_ips gth_probe]]
set_property -dict [list CONFIG.TX_BUFFER_MODE {0} CONFIG.RX_BUFFER_MODE {0}] $ip
puts $fo "=== after TX_BUFFER_MODE 0, RX_BUFFER_MODE 0 ==="
foreach p [lsort [list_property $ip -regexp {CONFIG\.(TX|RX|LOCATE).*(BUFFER|BYPASS|SYNC).*}]] {
    puts $fo "$p = [get_property $p $ip]"
}
puts $fo "validate: [catch {validate_ip $ip} msg] $msg"
close $fo
