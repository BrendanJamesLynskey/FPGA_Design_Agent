# zb.tcl: xsdb helpers for ZedBoard bump (Digilent "Zed" cable; its serial comes from the environment variable ZB_SERIAL and is
# never committed). Every call selects the target by
# cable serial, never "the first target". SRAM/JTAG only: this file never writes flash or SD. Needs hw_server on $ZB_URL.
if {![info exists ::env(ZB_SERIAL)]} { error "set ZB_SERIAL to the Zed cable serial (kept out of the repository)" }
set ZB_SERIAL $::env(ZB_SERIAL)
proc zb_connect {} {
    global ZB_SERIAL
    set url tcp:localhost:3133
    if {[info exists ::env(ZB_URL)]} { set url $::env(ZB_URL) }
    connect -url $url
    # confirm the cable really is the ZedBoard's: product Zed + serial + an xc7z020 on its chain
    set ok 0
    foreach t [targets -target-properties] {
        if {[dict exists $t jtag_cable_serial] && [dict get $t jtag_cable_serial] eq $ZB_SERIAL} {
            if {[dict get $t jtag_cable_product] ne "Zed"} { error "cable $ZB_SERIAL is not a Zed" }
            if {[dict get $t name] eq "xc7z020"} { set ok 1 }
        }
    }
    if {!$ok} { error "ZedBoard bump (cable $ZB_SERIAL, xc7z020) not found" }
}
proc zb_sel {name} {
    global ZB_SERIAL
    targets -set -nocase -filter "jtag_cable_serial == \"$ZB_SERIAL\" && name =~ \"$name\""
}
# Load PS init, program the PL, post-config, then run an ELF on core 0 (all JTAG/SRAM). args: ps7_init.tcl bitstream elf
proc zb_run {ps7init bit elf} {
    zb_sel "ARM Cortex-A9 MPCore #0"
    catch {stop}
    # a processor reset (not a system reset) clears the core's L1 caches and MMU left by the previous program, so no stale
    # cache line shadows the image loaded below; rt_init invalidates the L2 before it enables it
    rst -processor
    uplevel #0 [list source $ps7init]
    uplevel #0 ps7_init
    mwr 0x03000000 0
    mwr 0x03000004 0
    zb_sel "xc7z020"
    fpga -file $bit
    zb_sel "ARM Cortex-A9 MPCore #0"
    uplevel #0 ps7_post_config
    dow $elf
    con
}
proc zb_log {} {
    zb_sel "ARM Cortex-A9 MPCore #0"
    set w [mrd -value 0x03000004]
    if {$w == 0} { return "" }
    set n [expr {$w}]
    set words [mrd -value 0x03000010 [expr {($n+3)/4}]]
    set s ""
    foreach x $words { for {set i 0} {$i<4} {incr i} { append s [format %c [expr {($x >> (8*$i)) & 0xff}]] } }
    return [string range $s 0 [expr {$n-1}]]
}
