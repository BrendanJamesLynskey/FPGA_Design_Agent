# measure_rmii.tcl (brief 129): the RMII network design of the repo (designs/b63d_nexys_net, Nexys A7-100T, Vivado 2026.1)
# placed and routed with its own constraints, once per variant, into a directory the flow's checks read like a build dir.
#   vivado -mode batch -log <out>/vivado.log -source measure_rmii.tcl -tclargs <repo root> <out dir> <variant> [place directive]
# variants:
#   packed     the design as it is (set_property IOB TRUE on the RMII ports in design.xdc)
#   unpacked   the same, then set_property IOB FALSE on those ports (the registers are forced out of the I/O block)
#   gate_in    planted fault 1: an AND gate between the RXD pads and their registers (eth_mac_rmii.sv patched in the copy)
#   fanout_out ETH_TXEN's register is also read by logic (a LED): Vivado duplicates the register, so this is NOT a fault (a null result)
#   gate_out   planted fault 2: a gate between the ETH_TXEN register and its pad (ETH_TXEN = register & ~rst)
# The design's own files are never edited: patched files are written under <out>/patched and read instead.
set_param general.maxThreads 2
set_param synth.maxThreads 2
lassign $argv root out variant directive
file mkdir $out
file mkdir $out/patched
set d $root/designs/b63d_nexys_net
set files {}
foreach pat {shell/rtl/*.sv ip_lib/eth_mac_rmii/rtl/*.sv ip_lib/eth_mac_rgmii/rtl/eth_rx_classify.sv
             ip_lib/eth_mac_rgmii/rtl/eth_mac_stats.sv ip_lib/arp_responder/rtl/*.sv ip_lib/icmp_echo/rtl/*.sv
             ip_lib/igmp_join/rtl/*.sv ip_lib/ipv4_udp_rx/rtl/*.sv ip_lib/ipv4_udp_tx/rtl/*.sv ip_lib/mdio_master/rtl/*.sv
             designs/b63d_nexys_net/rtl/*.sv} {
    foreach f [lsort [glob -nocomplain $root/$pat]] { lappend files $f }
}
proc fda_patch {src dst from to} {
    set fh [open $src]; set t [read $fh]; close $fh
    set n [string first $from $t]
    if {$n < 0} { error "patch: text not found in $src: $from" }
    set t [string replace $t $n [expr {$n + [string length $from] - 1}] $to]
    set fh [open $dst w]; puts -nonewline $fh $t; close $fh
}
if {$variant eq "gate_in"} {
    set src $root/ip_lib/eth_mac_rmii/rtl/eth_mac_rmii.sv
    fda_patch $src $out/patched/eth_mac_rmii.sv "rxd_q <= rmii_rxd;" "rxd_q <= rmii_rxd & \{2\{speed_100\}\};"
    set files [lmap f $files {expr {$f eq $src ? "$out/patched/eth_mac_rmii.sv" : $f}}]
} elseif {$variant eq "fanout_out"} {
    set src $d/rtl/b63d_nexys_net_top.sv
    fda_patch $src $out/patched/b63d_nexys_net_top.sv "rx_led != '0, beat\[25\]\}" "rx_led != '0, beat\[25\] ^ ETH_TXEN\}"
    set files [lmap f $files {expr {$f eq $src ? "$out/patched/b63d_nexys_net_top.sv" : $f}}]
}
if {$variant eq "gate_out"} {
    set src $d/rtl/b63d_nexys_net_top.sv
    fda_patch $src $out/patched/b63d_nexys_net_top.sv "always_ff @(negedge clk) begin ETH_TXEN <= mac_txen;" \
        "logic txen_q; assign ETH_TXEN = txen_q & ~rst;\n    always_ff @(negedge clk) begin txen_q <= mac_txen;"
    set files [lmap f $files {expr {$f eq $src ? "$out/patched/b63d_nexys_net_top.sv" : $f}}]
}
foreach f $files { read_verilog -sv $f }
set rmii_ports_pat {ETH_CRSDV ETH_RXERR ETH_RXD[*] ETH_TXEN ETH_TXD[*]}
set rmii_ports_unused 1
synth_design -top b63d_nexys_net_top -part xc7a100tcsg324-1
# the design's own XDC, read on the synthesised netlist (its create_generated_clock names a pin, which needs an open design here)
read_xdc $d/design.xdc
if {$variant eq "unpacked"} { set_property IOB FALSE [get_ports {ETH_CRSDV ETH_RXERR ETH_RXD[*] ETH_TXEN ETH_TXD[*]}] }
opt_design
if {$directive ne ""} { place_design -directive $directive } else { place_design }
phys_opt_design
route_design
write_checkpoint -force $out/post_route.dcp
source $root/flow/io_paths.tcl
source $root/flow/iob_paths.tcl
io_dump_paths $out/io_paths_route.txt
iob_dump $out/iob_route.txt
report_drc -file $out/drc.rpt
report_timing_summary -max_paths 5 -file $out/timing_summary.rpt
report_timing -from [get_ports {ETH_CRSDV ETH_RXD[*]}] -delay_type min_max -max_paths 4 -nworst 1 -file $out/timing_rx.rpt
report_timing -to [get_ports {ETH_TXEN ETH_TXD[*]}] -delay_type min_max -max_paths 4 -nworst 1 -file $out/timing_tx.rpt
# per port: the worst setup (max) and hold (min) path, numbers from the path object
set f [open $out/io_times.csv w]
puts $f "port,dir,type,slack_ns,datapath_ns,logic_ns,net_ns,requirement_ns,startpoint_clock_delay_ns,endpoint_clock_delay_ns,endpoint"
foreach {dir ports} [list in [get_ports {ETH_CRSDV ETH_RXERR ETH_RXD[*]}] out [get_ports {ETH_TXEN ETH_TXD[*]}]] {
    foreach port [lsort $ports] {
        foreach {dt tp} {max setup min hold} {
            if {$dir eq "in"} { set p [lindex [get_timing_paths -quiet -from $port -delay_type $dt -max_paths 1] 0] } \
            else              { set p [lindex [get_timing_paths -quiet -to $port -delay_type $dt -max_paths 1] 0] }
            if {$p eq ""} { puts $f "$port,$dir,$tp,,,,,,,,"; continue }
            puts $f [join [list $port $dir $tp [get_property SLACK $p] [get_property DATAPATH_DELAY $p] \
                [get_property -quiet DATAPATH_LOGIC_DELAY $p] [get_property -quiet DATAPATH_NET_DELAY $p] \
                [get_property REQUIREMENT $p] [get_property -quiet STARTPOINT_CLOCK_DELAY $p] \
                [get_property -quiet ENDPOINT_CLOCK_DELAY $p] [get_property ENDPOINT_PIN $p]] ,]
        }
    }
}
close $f
puts "MEASURE-DONE $variant"
