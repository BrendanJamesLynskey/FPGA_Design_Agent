# gth_regs.tcl: the host side of designs/b56a_gth_serdes: register reads and writes over the board's JTAG cable (Vivado hardware
# manager), by the same BSCANE2 USER4 register bus as designs/b58a_trigger (host/jtag_regs.tcl). NOT YET RUN ON A BOARD: written
# against the documented scan commands; docs/board_run_plan.md step 3 reads the ID register (0x56A00001) first.
#
#   source designs/b56a_gth_serdes/host/gth_regs.tcl
#   b58a_open <cable serial>          ;# from jtag_regs.tcl: hw_server, the target with that serial, the xck26 device, JTAG mode on
#   gth_id                            ;# 56a00001
#   gth_status                        ;# decoded STATUS
#   gth_snapshot                      ;# counters (words, error bits, hard cycles, hard errors) from one snapshot
#   gth_temp_code                     ;# die temperature ADC code (16-bit, left-justified) from the SYSMON window; convert with UG580
#   b58a_close
#
# Laser: the design holds sfp_tx_disable high after reset. gth_laser_on writes CTRL.tx_disable = 0 and only works after you have
# confirmed the polarity (docs/board_run_plan.md step 1); there is no procedure here that enables it by default.
source [file join [file dirname [info script]] .. .. b58a_trigger host jtag_regs.tcl]

proc gth_id {} { return [format %08x [b58a_rd 0x000]] }

proc gth_status {} {
    set s [b58a_rd 0x014]
    set names {tx_done rx_done gt_powergood cdr_lock txpma_done rxpma_done - - cdr_stable fab_locked hard_locked mod_abs rx_los tx_fault}
    set out {}
    for {set i 0} {$i < [llength $names]} {incr i} {
        set n [lindex $names $i]
        if {$n ne "-"} { lappend out $n [expr {($s >> $i) & 1}] }
    }
    return $out
}

proc gth_pulse {bits} { b58a_wr 0x010 $bits }          ;# bit 0 reset_all ... bit 5 clear, 6 force_err_fab, 7 force_err_hard, 8 snap

proc gth_snapshot {} {
    gth_pulse 0x100
    after 1
    gth_pulse 0x100
    after 1
    set w [expr {[b58a_rd 0x024] << 32 | [b58a_rd 0x020]}]
    set e [expr {[b58a_rd 0x02C] << 32 | [b58a_rd 0x028]}]
    set hc [expr {[b58a_rd 0x03C] << 32 | [b58a_rd 0x038]}]
    set he [expr {[b58a_rd 0x044] << 32 | [b58a_rd 0x040]}]
    return [list fab_words $w fab_errbits $e fab_errwords [b58a_rd 0x030] losses [expr {[b58a_rd 0x034] & 0xFFFF}] hard_cycles $hc hard_err_cycles $he]
}

# die temperature: SYSMONE4 register 0x00 holds a 16-bit left-justified ADC code. The conversion to degrees C is in AMD UG580 (UltraScale
# System Management Wizard / SYSMON guide) and is NOT implemented here: it has not been read for this part, and a wrong constant
# would look like a measurement. Log the code and convert it once the formula is confirmed (brief 56B, operating-conditions record).
proc gth_sysmon {addr} {
    b58a_wr 0x060 $addr
    after 1
    set v [b58a_rd 0x064]
    if {!(($v >> 16) & 1)} { error "SYSMON read not valid" }
    return [expr {$v & 0xFFFF}]
}
proc gth_temp_code {} { return [gth_sysmon 0x00] }

proc gth_laser_on {}  { set c [b58a_rd 0x00C]; b58a_wr 0x00C [expr {$c & ~0x8}] }
proc gth_laser_off {} { set c [b58a_rd 0x00C]; b58a_wr 0x00C [expr {$c | 0x8}] }

# SFP+ I2C bit-bang (open drain, 0x050: bit 0 SCL low, bit 1 SDA low). One byte read of the module EEPROM is >100 register writes at
# JTAG speed: slow but enough for the 256-byte A0h page (docs/board_run_plan.md step 6). Not implemented here: the first board run
# checks MOD_ABS and the pin levels only.
