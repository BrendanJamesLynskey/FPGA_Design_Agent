# iob_paths.tcl (brief 129): for every port of the open (placed or routed) design, the register next to its I/O buffer, whether
# it sits in the I/O block, and the facts that decide whether it could: for flow/iob_check.py (gate iob_packed, check iob).
#   source flow/iob_paths.tcl; iob_dump <out file>
# PART|<part>|<family>                          the device family (Vivado's ARCHITECTURE of the part)
# PORT|<port>|<dir in/out>|<port IOB>|<buffer ref>|<buffer>|<loads>|<reg>|<reg ref>|<reg IOB>|<bel>|<site>|<reg fanout>|<d driver>
#      port IOB:  the IOB property on the port (TRUE, FALSE or empty)
#      buffer:    the IBUF/OBUF-type cell the port drives or is driven by (empty: none found)
#      loads:     input: the REF_NAMEs of every load of the buffer's output net, joined by ","; output: the REF_NAME of the
#                 driver of the buffer's input, followed by "(" its other loads ")"; "-" when none
#      reg:       the register the buffer talks to when that is the only thing on the net ("" when there is none, or more
#                 than one load or a combinational driver)
#      reg IOB:   the IOB property on the register cell; bel/site: where it was placed (empty if unplaced)
#      reg fanout: loads of the register's Q net (input registers: all loads; output registers: loads other than the buffer)
#      d driver:  the REF_NAME of the cell driving the register's D (input) or the buffer's driver (output when not a register)
# MARKED|<cell>|<ref>|<IOB>|<bel>|<site>|<kind>   a sequential cell with IOB TRUE that no port line above names
# ERROR|<what>|<message>
# The file ends with "# end". Everything is read from the netlist; nothing here decides pass or fail.

proc iob__prop {obj name} {
    set v [get_property -quiet $name $obj]
    return [string map {| / \n { }} $v]
}

proc iob__leaf_loads {net} {
    return [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}]
}

proc iob__drivers {net} {
    return [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}]
}

proc iob__is_buf {ref dir} {
    if {$dir eq "in"} { return [regexp {^(IBUF|IBUFDS|IBUFE3|IBUF_|INBUF|IBUFCTRL)} $ref] }
    return [regexp {^(OBUF|OBUFT|OBUFDS|OBUFTDS|OUTBUF|IOBUF)} $ref]
}

proc iob_dump {out} {
    set f [open $out w]
    set seen {}
    if {[catch {
        set part [get_parts -quiet [get_property PART [current_design]]]
        puts $f "PART|[get_property PART [current_design]]|[get_property -quiet ARCHITECTURE $part]"
        foreach port [lsort [get_ports -quiet -filter {DIRECTION == IN || DIRECTION == OUT}]] {
            set dir [expr {[get_property DIRECTION $port] eq "IN" ? "in" : "out"}]
            set pnet [get_nets -quiet -of_objects $port]
            if {$pnet eq ""} { continue }
            set buf ""; set bref ""; set loads "-"; set reg ""; set rref ""; set riob ""; set bel ""; set site ""
            set rfan ""; set drv ""
            if {$dir eq "in"} {
                set bc [get_cells -quiet -of_objects [iob__leaf_loads $pnet]]
                foreach c $bc { if {[iob__is_buf [get_property REF_NAME $c] in]} { set buf $c } }
                if {$buf ne ""} {
                    # UltraScale+: the pad buffer is INBUF followed by IBUFCTRL (both inside the IBUF macro): walk to the last stage
                    for {set k 0} {$k < 3} {incr k} {
                        set onet [get_nets -quiet -of_objects [get_pins -quiet -of_objects $buf -filter {DIRECTION == OUT && IS_CONNECTED}]]
                        set nx [get_cells -quiet -of_objects [iob__leaf_loads $onet]]
                        if {[llength $nx] == 1 && [regexp {^(IBUFCTRL|IBUF_ANALOG|INBUF|DIFFINBUF)$} [get_property REF_NAME $nx]]} { set buf $nx } else { break }
                    }
                    set bref [get_property REF_NAME $buf]
                    set onet [get_nets -quiet -of_objects [get_pins -quiet -of_objects $buf -filter {DIRECTION == OUT && IS_CONNECTED}]]
                    set lp [iob__leaf_loads $onet]
                    set refs {}
                    foreach c [get_cells -quiet -of_objects $lp] { lappend refs [get_property REF_NAME $c] }
                    if {[llength $refs]} { set loads [join $refs ","] }
                    if {[llength $lp] == 1} {
                        set c [get_cells -quiet -of_objects $lp]
                        if {$c ne "" && [get_property -quiet IS_SEQUENTIAL $c]} {
                            set reg $c
                            set dp [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == D}]
                            if {$dp ne ""} {
                                set d [iob__drivers [get_nets -quiet -of_objects $dp]]
                                if {$d ne ""} { set drv [get_property REF_NAME [get_cells -quiet -of_objects $d]] }
                            }
                            set qp [get_pins -quiet -of_objects $c -filter {DIRECTION == OUT}]
                            set rfan [llength [iob__leaf_loads [get_nets -quiet -of_objects $qp]]]
                        }
                    }
                }
            } else {
                set bc [get_cells -quiet -of_objects [iob__drivers $pnet]]
                foreach c $bc { if {[iob__is_buf [get_property REF_NAME $c] out]} { set buf $c } }
                if {$buf ne ""} {
                    set bref [get_property REF_NAME $buf]
                    set ip [get_pins -quiet -of_objects $buf -filter {REF_PIN_NAME == I}]
                    set inet [expr {$ip eq "" ? "" : [get_nets -quiet -of_objects $ip]}]
                    set dp [expr {$inet eq "" ? "" : [iob__drivers $inet]}]
                    if {$dp ne ""} {
                        set c [get_cells -quiet -of_objects $dp]
                        set dref [get_property REF_NAME $c]
                        set others [expr {[llength [iob__leaf_loads $inet]] - 1}]
                        set loads "${dref}(${others})"
                        set drv $dref
                        if {[get_property -quiet IS_SEQUENTIAL $c]} {
                            set reg $c
                            set qp [get_pins -quiet -of_objects $c -filter {DIRECTION == OUT}]
                            set rfan [expr {[llength [iob__leaf_loads [get_nets -quiet -of_objects $qp]]] - 1}]
                            set dd [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == D}]
                            if {$dd ne ""} {
                                set dr [iob__drivers [get_nets -quiet -of_objects $dd]]
                                if {$dr ne ""} { set drv [get_property REF_NAME [get_cells -quiet -of_objects $dr]] }
                            }
                        }
                    }
                }
            }
            if {$reg ne ""} {
                set rref [get_property REF_NAME $reg]
                set riob [iob__prop $reg IOB]
                set bel [iob__prop $reg BEL]
                set site [iob__prop $reg SITE]
                lappend seen $reg
            }
            puts $f [join [list PORT $port $dir [iob__prop $port IOB] $bref $buf $loads $reg $rref $riob $bel $site $rfan $drv] |]
        }
        foreach c [get_cells -quiet -hierarchical -filter {IS_SEQUENTIAL && IOB == TRUE}] {
            if {[lsearch -exact $seen $c] >= 0} { continue }
            puts $f [join [list MARKED $c [get_property REF_NAME $c] [iob__prop $c IOB] [iob__prop $c BEL] [iob__prop $c SITE] \
                [iob__prop $c PRIMITIVE_TYPE]] |]
        }
    } err]} {
        puts $f "ERROR|dump|[string map {| / \n { }} $err]"
    }
    puts $f "# end"
    close $f
}
