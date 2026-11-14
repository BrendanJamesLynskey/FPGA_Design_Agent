# run_elf.tcl <xsa dir with ps7_init.tcl and the .bit> <bitstream name> <elf> <log out> <timeout s>
# One clean run on ZedBoard bump over JTAG: ps7_init, program the PL (SRAM), ps7_post_config, load the ELF into DDR, run, poll the
# DDR console log (rt.c) until it ends with DONE, save it. Needs ZB_SERIAL (the cable serial) and hw_server on ZB_URL (default tcp:localhost:3133).
source [file join [file dirname [info script]] zb.tcl]
lassign $argv xdir bitname elf logfile tmo
zb_connect
zb_run $xdir/ps7_init.tcl $xdir/$bitname $elf
set t0 [clock seconds]
set last ""
while {[expr {[clock seconds] - $t0}] < $tmo} {
    after 2000
    zb_sel "ARM Cortex-A9 MPCore #0"
    set n [mrd -value 0x03000004]
    if {$n != $last} { set last $n } else {
        set s [zb_log]
        if {[string match "*DONE*" $s]} { break }
    }
}
set s [zb_log]
set f [open $logfile w]; puts -nonewline $f $s; close $f
puts "LOG BYTES [string length $s] ELAPSED [expr {[clock seconds]-$t0}]"
catch {zb_sel "ARM Cortex-A9 MPCore #0"; puts "CORE: [state]"}
