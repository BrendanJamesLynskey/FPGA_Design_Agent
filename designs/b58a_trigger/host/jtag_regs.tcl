# jtag_regs.tcl: the host side of rtl/jtag_bus.sv: register reads and writes over the board's JTAG cable, from the
# Vivado hardware manager. NOT YET RUN ON A BOARD (written against the documented scan commands; the board run plan's
# first step checks it by reading the ID register, 0x58A00001).
#
#   source designs/b58a_trigger/host/jtag_regs.tcl
#   b58a_open <cable serial>            ;# hw_server, the target with that serial, the xck26 device, JTAG mode on
#   b58a_wr 0x002 0x3                   ;# core enable, speculative mode
#   puts [format %08x [b58a_rd 0x000]]  ;# 58a00001
#   b58a_close
#
# The design's data register is reached with the USER4 instruction of the PL TAP (BSCANE2 JTAG_CHAIN 4). The 64-bit
# register, least significant bit first: [31:0] write data, [43:32] address, [44] write, [45] read. Capture-DR loads
# {0x58A0 marker [63:48], 0 [47:40], command count [39:32], last read data [31:0]}. A read is the read scan and then
# two scans without a command (they clock the TCK-side synchroniser); the last one returns the data.
#
# The USER4 instruction code and the instruction-register length depend on the device and on what else is on the JTAG
# chain (the K26 also has the PS debug port): both are read from Vivado's device properties below, not assumed. If
# Vivado does not list USER4 for the device, the procedure stops and asks for the code from the device's BSDL file.

proc b58a_open {serial} {
    open_hw_manager
    connect_hw_server -allow_non_jtag
    set t [lsearch -inline -glob [get_hw_targets] "*$serial*"]
    if {$t eq ""} { error "no JTAG target with serial $serial" }
    current_hw_target $t
    set_property PARAM.FREQUENCY 1000000 [current_hw_target]
    open_hw_target -jtag_mode on
    set ::b58a_dev [lindex [get_hw_devices -filter {PART =~ xck26*}] 0]
    if {$::b58a_dev eq ""} { error "no xck26 PL device on the chain" }
    set ::b58a_drpad 0
    if {[llength [get_hw_devices]] == 2 && [llength [get_hw_devices -filter {PART == arm_dap}]] == 1} {
        # Zynq UltraScale+ (K26) cascaded chain, measured on the KR260 2026-11-17: TDI -> PL/PS TAP (IR 12) -> ARM DAP (IR 4)
        # -> TDO. USER4 is 0x923 in the 12-bit IR; the DAP gets BYPASS (0xF) in the low 4 bits; its 1-bit bypass register
        # sits between the PL user chain and TDO, so DR scans are 65 bits with the data one bit up.
        set ::b58a_ir 16
        set ::b58a_user4 923f
        set ::b58a_drpad 1
    } else {
        set ::b58a_ir [get_property IR_LENGTH $::b58a_dev]
        set ::b58a_user4 [b58a_user4_code $::b58a_dev]
    }
}

# USER4 for the selected device, from the device's own BSDL-derived instruction table (Vivado's USER instructions)
proc b58a_user4_code {dev} {
    foreach p [list USER4 JTAG_USER4] {
        if {[lsearch [list_property $dev] "*$p*"] >= 0} { return [get_property [lsearch -inline [list_property $dev] "*$p*"] $dev] }
    }
    error "USER4 instruction code not found for $dev: read it from the device's BSDL and set ::b58a_user4"
}

proc b58a_scan {bits64} {
    scan_ir_hw_jtag $::b58a_ir -tdi $::b58a_user4
    if {[info exists ::b58a_drpad] && $::b58a_drpad} {
        set w [scan $bits64 %llx]
        set r [scan_dr_hw_jtag 65 -tdi [format %017llx [expr {$w << 1}]]]
        set v [scan $r %llx]
        return [format %016llx [expr {($v >> 1) & 0xFFFFFFFFFFFFFFFF}]]
    }
    return [scan_dr_hw_jtag 64 -tdi $bits64]
}

proc b58a_cmd {write read addr data} {
    set v [expr {(($read & 1) << 45) | (($write & 1) << 44) | (($addr & 0xFFF) << 32) | ($data & 0xFFFFFFFF)}]
    return [format %016llx $v]
}

proc b58a_wr {addr data} {
    b58a_scan [b58a_cmd 1 0 $addr $data]
}

proc b58a_rd {addr} {
    b58a_scan [b58a_cmd 0 1 $addr 0]
    b58a_scan [format %016llx 0]
    set r [b58a_scan [format %016llx 0]]
    set v [expr 0x$r]
    if {(($v >> 48) & 0xFFFF) != 0x58A0} { error "no 0x58A0 marker in the captured data ($r): wrong instruction or design" }
    return [expr {$v & 0xFFFFFFFF}]
}

proc b58a_close {} {
    close_hw_target
    disconnect_hw_server
    close_hw_manager
}
