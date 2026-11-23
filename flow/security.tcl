# security.tcl: the Tcl of the production_secure build (brief 196). Definitions only; flow/build.tcl calls them.
#
#   fda_security_apply <out> <props> <switches>   sets each {property value} pair on the design, before write_bitstream, and records every result in
#                                      <out>/security_apply.txt (APPLY ok / APPLY ERROR ...), never stopping the build: a setting Vivado refuses
#                                      is a failed gate (flow/security.py), not a crash
#   fda_security_dump <out>            after write_bitstream: every BITSTREAM.* property read back from the design, the debug inventory, the
#                                      top-level ports and the SYSMONE4 cells with their alarm-pin loads, into <out>/security_design.txt
#
# No command here reads, writes, loads or programs a key, an eFUSE or a BBRAM, and none touches hardware. Vivado itself makes the .nky beside
# the bitstream when encryption is on (a key for a build that is never programmed; flow/security.py documents the handling).

proc fda_security_apply {out props switches} {
    set f [open $out/security_apply.txt w]
    foreach {p v} $props {
        if {[catch {set_property $p $v [current_design]} err]} {
            puts $f "APPLY ERROR $p $v :: [string map {\n { }} $err]"
        } else {
            puts $f "APPLY ok $p $v"
        }
    }
    # Key FILES are the owner's (or a throw-away file made by hand for a build that is never programmed). The flow never makes or reads one: an
    # environment variable names the file, Vivado reads it, and neither its path nor its content goes into a record.
    #   FDA_SECURITY_KEYFILE      an .nky for the encryption key (without it Vivado makes its own key and writes an .nky beside the bitstream)
    #   FDA_SECURITY_RSAKEYFILE   the RSA private key file that bitstream authentication needs
    array set sw $switches
    foreach {var prop need} {FDA_SECURITY_KEYFILE BITSTREAM.ENCRYPTION.KEYFILE encrypt FDA_SECURITY_RSAKEYFILE BITSTREAM.AUTHENTICATION.RSAPRIVATEKEYFILE authenticate} {
        if {[info exists sw($need)] && $sw($need) && [info exists ::env($var)] && $::env($var) ne ""} {
            if {![file isfile $::env($var)]} {
                puts $f "APPLY ERROR $prop <file> :: the file named by $var does not exist"
            } elseif {[catch {set_property $prop $::env($var) [current_design]} err]} {
                puts $f "APPLY ERROR $prop <file> :: [string map {\n { }} $err]"
            } else {
                puts $f "APPLY ok $prop <file given by $var>"
            }
        }
    }
    close $f
}

proc fda_security_dump {out} {
    set f [open $out/security_design.txt w]
    set d [current_design]
    puts $f "PART [get_property PART $d]"
    foreach p [lsort [list_property $d BITSTREAM.*]] {
        puts $f "PROP $p [get_property $p $d]"
    }
    # debug inventory (the implemented design, so a core Vivado inserted in opt_design or by flow/debug.tcl is in it)
    puts $f "DEBUG_CORES [llength [get_debug_cores -quiet]] [get_debug_cores -quiet]"
    set pat {(?i)(dbg_hub|u_ila|ila_[0-9]|^ila$|vio_|u_vio|debug_bridge|jtag_axi|xsdb|labtools|\mmdm\M)}
    set n 0
    foreach c [get_cells -quiet -hierarchical] {
        set ref [get_property -quiet REF_NAME $c]
        if {[regexp $pat $c] || [regexp $pat $ref]} {
            if {$n < 400} { puts $f "DEBUG_CELL $ref $c" }
            incr n
        }
    }
    puts $f "DEBUG_CELL_COUNT $n"
    set nb 0
    foreach c [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE && REF_NAME =~ BSCAN*}] {
        puts $f "BSCAN_CELL [get_property REF_NAME $c] $c"
        incr nb
    }
    puts $f "BSCAN_COUNT $nb"
    set md [get_nets -quiet -hierarchical -filter {MARK_DEBUG == 1}]
    puts $f "MARK_DEBUG_NETS [llength $md]"
    foreach nn [lrange $md 0 19] { puts $f "MARK_DEBUG_NET $nn" }
    foreach p [get_ports -quiet] {
        puts $f "PORT [get_property DIRECTION $p] $p"
    }
    # the system monitor: its attributes and where each alarm output goes
    foreach c [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE && REF_NAME == SYSMONE4}] {
        puts $f "SYSMON_CELL $c"
        foreach a [lsort [list_property $c INIT_*]] {
            puts $f "SYSMON_ATTR $a [get_property $a $c]"
        }
        foreach pn {OT ALM[0] ALM[1] ALM[2] ALM[3] ALM[4] ALM[5] ALM[6]} {
            set pin [get_pins -quiet $c/$pn]
            if {$pin eq ""} { puts $f "SYSMON_PIN $pn none"; continue }
            set net [get_nets -quiet -of_objects $pin]
            set loads {}
            if {$net ne ""} { set loads [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}] }
            set l {}
            foreach ld [lrange $loads 0 5] { lappend l "[get_property REF_NAME [get_cells -of_objects $ld]]:$ld" }
            puts $f "SYSMON_PIN $pn [llength $loads] $l"
        }
    }
    close $f
}
