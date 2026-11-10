# wizard_probe2.tcl: the Transceivers Wizard on a GTP part, and the MIG command census (brief 18, section 2b / 2).
#   vivado -mode batch -source flow/wizard_probe2.tcl -tclargs <out dir>
set_param general.maxThreads 1
set out [file normalize [lindex $argv 0]]; file mkdir $out
set lf [open $out/wizards2.txt w]
proc log {args} { global lf; puts $lf [join $args " "]; flush $lf }
log "== MIG commands in the Tcl interpreter"
foreach pat {*mig* *verify* *validate_ip* validate_*} { log "info commands $pat: [lsort [info commands $pat]]" }
log "== Transceivers Wizard on xc7a200tfbg484-1 (GTP)"
create_project -in_memory -part xc7a200tfbg484-1
if {[catch {
    set d $out/ip_gt; file mkdir $d
    create_ip -name gtwizard -vendor xilinx.com -library ip -module_name gtw -dir $d
    log "OK create_ip gtwizard (7 series)"
    foreach p [lsort [list_property [get_ips gtw]]] {
        if {[regexp -nocase {LINE_RATE|REFCLK|REF_CLK|PLL|CLK_FREQ|GT_REFCLK|INTERNAL_DATA_WIDTH|ENCODING|^CONFIG.(gt_)?(type|protocol)|RXPROT|PROT} $p]} { log "  $p = [get_property $p [get_ips gtw]]" }
    }
} err]} { log "FAIL: $err" }
if {[catch {
    set_property -dict [list CONFIG.gt0_val true CONFIG.gt0_line_rate 12.5 CONFIG.gt0_refclk_freq 100.0] [get_ips gtw]
    log "set line rate 12.5 Gb/s on a GTP: accepted"
} err]} { log "set line rate 12.5 Gb/s on a GTP: [string map [list \n { }] $err]" }
if {[catch {
    set_property -dict [list CONFIG.gt0_val true CONFIG.gt0_line_rate 3.125 CONFIG.gt0_refclk_freq 125.0] [get_ips gtw]
    log "set line rate 3.125 Gb/s, refclk 125 MHz: accepted"
    foreach p [lsort [list_property [get_ips gtw]]] { if {[regexp -nocase {PLL.*FREQ|PLL.*DIV|PLL.*MULT|gt0_.*(rate|clk|pll)} $p]} { log "  $p = [get_property $p [get_ips gtw]]" } }
    generate_target all [get_ips gtw]
    log "OK generate_target"
} err]} { log "FAIL: [string map [list \n { }] $err]" }
close $lf
