# Brief 127: in-context timing of brief 110's critical paths inside the 10G core (post-route checkpoint of build rm_gp_itch).
#   vivado -mode batch -source results/b127/ctx_timing.tcl -tclargs <post_route.dcp> <out dir>
# brief 110 saw these out of context (results/b110/ooc/itch_ouch_top.json): at the required clock (6.2061 ns) the worst path was the risk verdict into the position register; at 5.0 ns the price-ladder
# update (B3). Here: the worst setup path ending in each of those register groups, the worst path of the whole design, and of each block of the ITCH path, with the clock they run on.
set dcp [lindex $argv 0]
set out [lindex $argv 1]
file mkdir $out
open_checkpoint $dcp
set fh [open $out/ctx_timing.txt w]
proc one {fh title cells} {
    puts $fh "=== $title"
    if {[llength $cells] == 0} { puts $fh "no cells matched"; return }
    set p [get_timing_paths -delay_type max -to $cells -max_paths 1 -nworst 1]
    if {[llength $p] == 0} { puts $fh "no timing path"; return }
    puts $fh "SLACK [get_property SLACK $p] STARTPOINT [get_property STARTPOINT_PIN $p] ENDPOINT [get_property ENDPOINT_PIN $p] REQ [get_property REQUIREMENT $p] LOGIC_LEVELS [get_property LOGIC_LEVELS $p]"
}
one $fh "risk_glue position registers (pos[])" [get_cells -hier -filter {NAME =~ *u_ip/u_it/u_risk/pos_reg*}]
one $fh "risk_glue verdict counters and queue (the rest of the risk verdict)" [get_cells -hier -filter {NAME =~ *u_ip/u_it/u_risk/dq*}]
one $fh "book_core price ladder (lv_*)" [get_cells -hier -filter {NAME =~ *u_ip/u_it/u_book/*lv_*}]
one $fh "book_core top of book and update record" [get_cells -hier -filter {NAME =~ *u_ip/u_it/u_book/tu_*}]
one $fh "mold_rx" [get_cells -hier -filter {NAME =~ *u_ip/u_it/u_mold/*}]
one $fh "itch_dec" [get_cells -hier -filter {NAME =~ *u_ip/u_it/u_dec/*}]
one $fh "udp_strip" [get_cells -hier -filter {NAME =~ *u_ip/u_us/*}]
one $fh "order_seg" [get_cells -hier -filter {NAME =~ *u_ip/u_it/u_seg/*}]
one $fh "tx_mux" [get_cells -hier -filter {NAME =~ *u_tx/u_mx/*}]
one $fh "mac64_tx (the CRC path with the multiplexer in front)" [get_cells -hier -filter {NAME =~ *u_tx/u_mt/*}]
one $fh "itch_path (poison policy, counters, statistics)" [get_cells -hier -filter {NAME =~ *u_ip/*}]
puts $fh "=== whole design, worst 3 setup paths per clock group"
foreach c [get_clocks] {
    set p [get_timing_paths -delay_type max -from [get_clocks $c] -to [get_clocks $c] -max_paths 3 -nworst 1]
    foreach q $p { puts $fh "CLOCK $c SLACK [get_property SLACK $q] START [get_property STARTPOINT_PIN $q] END [get_property ENDPOINT_PIN $q]" }
}
close $fh
close_design
