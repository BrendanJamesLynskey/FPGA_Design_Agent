# b96_regs.tcl: the host side of designs/b96_kr260_10g: register access over the board's JTAG cable (Vivado hardware manager), by
# the same BSCANE2 USER4 register bus as designs/b58a_trigger (host/jtag_regs.tcl). NOT YET RUN ON A BOARD. host/b96_bench.py drives
# these procedures from Python (it starts `vivado -mode tcl` and feeds it lines); you can also source this file by hand:
#
#   source designs/b96_kr260_10g/host/b96_regs.tcl
#   b58a_open <cable serial>          ;# hw_server, the target with that serial, the xck26 device, JTAG mode on
#   b96_id                            ;# 96a00001
#   b58a_close
#
# The laser stays off (CTRL.tx_disable = 1 from reset) until b96_laser_on, which the bench calls only after the polarity step.
source [file join [file dirname [info script]] .. .. b58a_trigger host jtag_regs.tcl]

proc b96_id {} { return [format %08x [b58a_rd 0x000]] }
proc b96_rd {a} { return [format %08x [b58a_rd $a]] }
proc b96_wr {a v} { b58a_wr $a $v; return ok }
# one line per word of the two snapshots, "RXV<i> <hex>" and "TXV<i> <hex>", taken after a snapshot command (CMD bit 2)
proc b96_dump {} {
    b58a_wr 0x018 0x4
    after 2
    for {set i 0} {$i < 16} {incr i} { puts "RXV$i [b96_rd [expr {0x100 + 4 * $i}]]" }
    for {set i 0} {$i < 26} {incr i} { puts "TXV$i [b96_rd [expr {0x200 + 4 * $i}]]" }
}
proc b96_laser_on {}  { set c [b58a_rd 0x00C]; b58a_wr 0x00C [expr {$c & ~0x8}]; return ok }
proc b96_laser_off {} { set c [b58a_rd 0x00C]; b58a_wr 0x00C [expr {$c | 0x8}]; return ok }
