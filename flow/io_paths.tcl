# io_paths.tcl (brief 20 part B): the I/O timing, the clocks and the worst internal paths of the open (routed) design,
# for flow/io_check.py (gates io_timing_clean and the uncertainty record in flow/gates.py).
#   source flow/io_paths.tcl; io_dump_paths <out file>
# CLOCK|<name>|<period>|<waveform>|<virtual 1/0>|<generated 1/0>|<source objects>|<input jitter>
# PORT|<name>|<in/out>|<IOB-packed register 1/0/none>|<first register>|<synchroniser 1/0>|<its primitive>
#      IOB: the register the port drives (input) or is driven by (output) sits in an ILOGIC/OLOGIC site (none: no register
#      next to the port). The primitive is the register's REF_NAME (IDDRE1, OSERDESE3, FDRE, ...; empty if not one
#      register): flow/io_check.py finds DDR ports by it. Synchroniser: an input's first register has ASYNC_REG and drives a second ASYNC_REG register.
# IO|<port>|<in/out>|<max/min>|<slack>|<requirement>|<io delay>|<startpoint clock>|<endpoint clock>|<corner>|<uncertainty>
#      the worst path from (input) or to (output) the port for that delay type; NOIO|<port>|<in/out>|<max/min> when
#      Vivado has no such path (no delay of that type, a false path, a clock group)
# WORST|<setup/hold>|<slack>|<requirement>|<startpoint clock>|<endpoint clock>|<corner>|<uncertainty>|<pessimism>|<from>|<to>
# ERROR|<what>|<message>
# The file ends with "# end". Properties are the timing-path object's own (INPUT_DELAY, OUTPUT_DELAY, CORNER,
# UNCERTAINTY, CLOCK_PESSIMISM; Vivado 2026.1). The uncertainty breakdown (TSJ, TIJ, DJ, PE) is only in report_timing's
# text: build.tcl writes timing_worst_setup.rpt and timing_worst_hold.rpt for it.

proc io__v {x} { if {$x eq ""} { return "" }; return $x }

proc io__path {f kind port dir dt} {
    if {$dir eq "in"} {
        set p [lindex [get_timing_paths -quiet -from $port -delay_type $dt -max_paths 1 -nworst 1] 0]
    } else {
        set p [lindex [get_timing_paths -quiet -to $port -delay_type $dt -max_paths 1 -nworst 1] 0]
    }
    if {$p eq ""} { puts $f "NOIO|$port|$dir|$dt"; return }
    set iod [expr {$dir eq "in" ? [get_property -quiet INPUT_DELAY $p] : [get_property -quiet OUTPUT_DELAY $p]}]
    puts $f [join [list IO $port $dir $dt [get_property SLACK $p] [get_property REQUIREMENT $p] [io__v $iod] \
        [get_property -quiet STARTPOINT_CLOCK $p] [get_property -quiet ENDPOINT_CLOCK $p] [get_property -quiet CORNER $p] \
        [get_property -quiet UNCERTAINTY $p]] |]
}

proc io_dump_paths {out} {
    set f [open $out w]
    if {[catch {
        foreach c [get_clocks -quiet] {
            set src [get_property -quiet SOURCE_PINS $c]
            set virt [expr {$src eq "" ? 1 : 0}]
            set gen [expr {[string is true -strict [get_property -quiet IS_GENERATED $c]] ? 1 : 0}]
            puts $f [join [list CLOCK $c [get_property PERIOD $c] [get_property WAVEFORM $c] $virt $gen $src \
                [io__v [get_property -quiet INPUT_JITTER $c]]] |]
        }
        foreach port [lsort [get_ports -quiet -filter {DIRECTION == IN || DIRECTION == OUT}]] {
            set dir [expr {[get_property DIRECTION $port] eq "IN" ? "in" : "out"}]
            # the register next to the port: through the I/O buffer only
            if {$dir eq "in"} {
                set regs [get_cells -quiet -of_objects [all_fanout -quiet -flat -endpoints_only $port] \
                    -filter {IS_SEQUENTIAL}]
            } else {
                set regs [get_cells -quiet -of_objects [all_fanin -quiet -flat -startpoints_only $port] \
                    -filter {IS_SEQUENTIAL}]
            }
            set iob none; set first ""; set sync 0; set prim ""
            if {[llength $regs] == 1} {
                set first [lindex $regs 0]
                set prim [get_property -quiet REF_NAME $first]
                set bel [get_property -quiet BEL $first]
                set iob [expr {[regexp {^(I|O)LOGIC} $bel] ? 1 : 0}]
                if {$dir eq "in" && [string is true -strict [get_property -quiet ASYNC_REG $first]]} {
                    foreach n [get_cells -quiet -of_objects [all_fanout -quiet -flat -endpoints_only \
                            [get_pins -quiet -filter {REF_PIN_NAME == Q} -of_objects $first]] -filter {IS_SEQUENTIAL}] {
                        if {[string is true -strict [get_property -quiet ASYNC_REG $n]]} { set sync 1 }
                    }
                }
            } elseif {[llength $regs] > 1} {
                set first "[llength $regs] registers"
            }
            puts $f [join [list PORT $port $dir $iob $first $sync $prim] |]
            foreach dt {max min} { io__path $f IO $port $dir $dt }
        }
        foreach {kind dt} {setup max hold min} {
            set p [lindex [get_timing_paths -quiet -delay_type $dt -max_paths 1 -nworst 1] 0]
            if {$p eq ""} { continue }
            puts $f [join [list WORST $kind [get_property SLACK $p] [get_property REQUIREMENT $p] \
                [get_property -quiet STARTPOINT_CLOCK $p] [get_property -quiet ENDPOINT_CLOCK $p] \
                [get_property -quiet CORNER $p] [get_property -quiet UNCERTAINTY $p] \
                [get_property -quiet CLOCK_PESSIMISM $p] [get_property -quiet STARTPOINT_PIN $p] \
                [get_property -quiet ENDPOINT_PIN $p]] |]
        }
    } err]} {
        puts $f "ERROR|dump|[string map {| / \n { }} $err]"
    }
    puts $f "# end"
    close $f
}
