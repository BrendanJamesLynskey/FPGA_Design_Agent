# ip_probe.tcl (brief 56A): licence and build probe of one AMD IP on the KR260's part, Vivado 2026.1, Basic tier.
#   PROBE=<name> vivado -mode batch -source designs/b56a_gth_serdes/probe/ip_probe.tcl      (run from the repo root; see run_probe.sh)
# Stages, each logged as "RESULT <name> <stage> OK|FAIL <first 300 characters of the error>":
#   create   create_ip with the configuration below
#   generate generate_target all (IP files, simulation models, instantiation template)
#   synth_ip out-of-context synthesis of the IP (its checkpoint)
#   top      synth_design of the IP wrapper as the top module (the IP's own ports become the top-level ports)
#   impl     opt_design, place_design, route_design
#   bit      write_bitstream
# For the top, impl and bit stages the unplaced-I/O and unconstrained-I/O DRCs (UCIO-1, NSTD-1) and the Kria pin-placement DRC (KLOC-1:
# the placer put a port on a VRP pin, which a Kria SOM forbids) are downgraded to warnings, because the IP's ports have no pins: that is a probe convenience, not a licence workaround, and nothing here changes any
# licence-related behaviour. A licence refusal is recorded with its exact text and never worked around.
set part xck26-sfvc784-2LV-c
set name $::env(PROBE)
set wd [file normalize ./probe_$name]
file mkdir $wd
cd $wd
create_project -in_memory -part $part
puts "PROBE $name VERSION [version -short] TIER [expr {[catch {get_vivado_tier} t] ? {n/a} : $t}]"

# name -> {vlnv config}
set cfgs [dict create \
  gtwizard      [list xilinx.com:ip:gtwizard_ultrascale:1.7 [list CONFIG.CHANNEL_ENABLE {X0Y6} CONFIG.TX_MASTER_CHANNEL {X0Y6} CONFIG.RX_MASTER_CHANNEL {X0Y6} CONFIG.TX_LINE_RATE {10.3125} CONFIG.RX_LINE_RATE {10.3125} CONFIG.TX_REFCLK_FREQUENCY {156.25} CONFIG.RX_REFCLK_FREQUENCY {156.25} CONFIG.TX_DATA_ENCODING {RAW} CONFIG.RX_DATA_DECODING {RAW} CONFIG.TX_USER_DATA_WIDTH {64} CONFIG.TX_INT_DATA_WIDTH {32} CONFIG.RX_USER_DATA_WIDTH {64} CONFIG.RX_INT_DATA_WIDTH {32}]] \
  ibert_gth     [list xilinx.com:ip:ibert_ultrascale_gth:1.4 [list CONFIG.C_PROTOCOL_MAXLINERATE_1 {10.3125}]] \
  ibert_gth_top [list xilinx.com:ip:ibert_ultrascale_gth:1.4 [list CONFIG.C_PROTOCOL_MAXLINERATE_1 {10.3125}]] \
  in_system_ibert [list xilinx.com:ip:in_system_ibert:1.0 {}] \
  aurora_64b66b [list xilinx.com:ip:aurora_64b66b:13.0 [list CONFIG.C_START_LANE {X0Y6} CONFIG.C_LINE_RATE {10.3125} CONFIG.C_REFCLK_FREQUENCY {156.25} CONFIG.C_INIT_CLK {100}]] \
  aurora_8b10b  [list xilinx.com:ip:aurora_8b10b:11.1 [list CONFIG.C_START_LANE {X0Y6}]] \
  xxv_ethernet  [list xilinx.com:ip:xxv_ethernet:5.1 [list CONFIG.LANE1_GT_LOC {X0Y6} CONFIG.LINE_RATE {10} CONFIG.GT_REF_CLK_FREQ {156.25} CONFIG.GT_DRP_CLK {100}]] \
  gig_ethernet_pcs_pma [list xilinx.com:ip:gig_ethernet_pcs_pma:17.0 {}] \
  ten_gig_eth_pcs_pma [list xilinx.com:ip:ten_gig_eth_pcs_pma:6.0 {}] \
  ten_gig_eth_mac [list xilinx.com:ip:ten_gig_eth_mac:15.1 {}] \
  xdma          [list xilinx.com:ip:xdma:4.2 {}] \
  pcie4_uscale_plus [list xilinx.com:ip:pcie4_uscale_plus:1.3 {}] \
  jesd204c      [list xilinx.com:ip:jesd204c:4.3 {}] \
  jesd204_phy   [list xilinx.com:ip:jesd204_phy:4.1 {}] \
  cmac_usplus   [list xilinx.com:ip:cmac_usplus:3.1 {}] \
]
# how far each probe goes (the last stage run). Brief 56A: the IP the K26 link work could use are taken to a bitstream; the rest to the
# stage that settles the licence question (the cores' top-level synthesis, or out-of-context synthesis where the part is not supported),
# to keep the shared machine's time: a probe that stops early says so in its RESULT line.
set last [dict create ibert_gth bit ibert_gth_top bit in_system_ibert bit aurora_64b66b bit xxv_ethernet bit aurora_8b10b top gig_ethernet_pcs_pma top \
  ten_gig_eth_pcs_pma synth_ip ten_gig_eth_mac synth_ip xdma top pcie4_uscale_plus top jesd204c top jesd204_phy top cmac_usplus synth_ip]
set order {create generate synth_ip top impl bit}
proc beyond {st} { global last name order; return [expr {[lsearch $order $st] > [lsearch $order [dict get $last $name]]}] }
if {![dict exists $cfgs $name]} { puts "RESULT $name create FAIL no such probe"; exit 1 }
lassign [dict get $cfgs $name] vlnv cfg

proc stage {n body} {
    global name
    set t0 [clock seconds]
    if {[catch {uplevel 1 $body} e]} {
        set e [string map [list "\n" " "] $e]
        puts "RESULT $name $n FAIL [string range $e 0 600]"
        return 0
    }
    puts "RESULT $name $n OK ([expr {[clock seconds]-$t0}] s)"
    return 1
}

set ok [stage create {
    file mkdir $wd/ip
    create_ip -vlnv $vlnv -module_name p_$name -dir $wd/ip
    if {[llength $cfg]} { set_property -dict $cfg [get_ips p_$name] }
}]
if {$ok} { set ok [stage generate { generate_target all [get_ips p_$name] }] }
if {$ok} { set ok [stage synth_ip { synth_ip [get_ips p_$name] }] }
if {$ok && [beyond top]} { puts "RESULT $name top STOPPED by plan after [dict get $last $name]"; set ok 0 }
if {$ok} {
    set ok [stage top {
        if {$name eq "ibert_gth_top"} {
            # a routable wrapper (reference buffer, system clock, pins) so that implementation can be judged, not the unplaced IP
            read_verilog [file join $::env(PROBE_DIR) ibert_top.v]
            read_xdc [file join $::env(PROBE_DIR) ibert_top.xdc]
            synth_design -top ibert_top -part $part
        } else {
            synth_design -top p_$name -part $part
        }
    }]
}
if {$ok && [beyond impl]} { puts "RESULT $name impl STOPPED by plan after [dict get $last $name]"; set ok 0 }
if {$ok} {
    set_property SEVERITY {Warning} [get_drc_checks {UCIO-1 NSTD-1 KLOC-1}]
    set ok [stage impl { opt_design; place_design; route_design; report_utilization -file $wd/util.rpt; report_timing_summary -file $wd/timing.rpt }]
}
if {$ok && [beyond bit]} { puts "RESULT $name bit STOPPED by plan after [dict get $last $name]"; set ok 0 }
if {$ok} { stage bit { write_bitstream -force $wd/p_$name.bit } }
puts "PROBEDONE $name"
