# delay_table.tcl: the per-copy routed delay and skew table (design section 3), from the routed design in memory.
#
# The crossing exceptions hide the inter-clock paths from timing, so this resets the timing constraints (in memory
# only; the checkpoint and bitstream are already written), re-creates the two primary clocks (the MMCM clocks are
# re-derived), and asks for every path between different clocks. For each copy it writes:
#   delays_paths.csv    one row per crossing endpoint pin: copy, variant, class, dir, clocks, start, end,
#                       data path delay (max corner and min corner, ns)
#   delays_copies.csv   one row per copy: crossing endpoints, the largest and smallest max-corner delay, and the
#                       skew of each multi-bit bus (max - min over its bits, max corner); the largest such skew.
#                       The checker's own reference crossings (u_ref, the storm-request synchroniser pbd_rq_s) are
#                       listed in delays_paths.csv with role "reference" and left out of the per-copy figures.

proc rig_delay_table {out counts} {
    reset_timing
    create_clock -name clk_a -period 10.000 [get_ports CLK100MHZ]
    create_clock -name clk_b -period 10.260 [get_pins u_startup/CFGMCLK]
    update_timing
    set clks [get_clocks]
    set map [dict create]
    foreach cp [rig_copies $counts] { dict set map [lindex $cp 0] $cp }
    set rows [dict create]
    foreach f $clks {
        foreach t $clks {
            if {$f eq $t} { continue }
            foreach dt {max min} {
                set ps [get_timing_paths -quiet -from $f -to $t -delay_type $dt -max_paths 200000 -nworst 1 -unique_pins]
                foreach p $ps {
                    set ep [get_property ENDPOINT_PIN $p]
                    set g [rig_copy_of $ep]
                    if {$g < 0} { continue }
                    set key "$g|$ep"
                    if {![dict exists $rows $key]} {
                        dict set rows $key [dict create g $g from [get_property NAME $f] to [get_property NAME $t] \
                            start [get_property STARTPOINT_PIN $p] end $ep max "" min ""]
                    }
                    dict set rows $key $dt [format %.3f [get_property DATAPATH_DELAY $p]]
                }
            }
        }
    }
    set fh [open $out/delays_paths.csv w]
    puts $fh "copy,variant,class,dir,role,from_clock,to_clock,start,end,delay_max_ns,delay_min_ns"
    set per [dict create]
    dict for {key r} $rows {
        set g [dict get $r g]
        set cp [dict get $map $g]
        set role [expr {[regexp {[./]u_ref/|[./]pbd_rq_s/} [dict get $r end]] ? "reference" : "crossing"}]
        puts $fh [join [list $g [lindex $cp 1] [lindex $cp 4] [lindex $cp 3] $role [dict get $r from] [dict get $r to] \
            [dict get $r start] [dict get $r end] [dict get $r max] [dict get $r min]] ,]
        if {[dict get $r max] ne "" && $role eq "crossing"} {
            # bus = endpoint cell without its bit index
            regsub {\[\d+\]/[A-Z]+$} [dict get $r end] {} bus
            regsub {/[A-Z]+$} $bus {} bus
            dict lappend per $g [list $bus [dict get $r max]]
        }
    }
    close $fh
    set fh [open $out/delays_copies.csv w]
    puts $fh "copy,variant,class,dir,endpoints,delay_max_ns,delay_min_of_max_ns,bus_skew_max_ns,widest_bus"
    foreach cp [rig_copies $counts] {
        set g [lindex $cp 0]
        if {![dict exists $per $g]} {
            puts $fh [join [list $g [lindex $cp 1] [lindex $cp 4] [lindex $cp 3] 0 "" "" "" ""] ,]
            continue
        }
        set ds [lmap x [dict get $per $g] {lindex $x 1}]
        set buses [dict create]
        foreach x [dict get $per $g] { dict lappend buses [lindex $x 0] [lindex $x 1] }
        set skew 0.0; set wb ""
        dict for {b v} $buses {
            if {[llength $v] < 2} { continue }
            set s [expr {[tcl::mathfunc::max {*}$v] - [tcl::mathfunc::min {*}$v]}]
            if {$s > $skew} { set skew $s; set wb "[file tail $b]([llength $v])" }
        }
        puts $fh [join [list $g [lindex $cp 1] [lindex $cp 4] [lindex $cp 3] [llength $ds] \
            [format %.3f [tcl::mathfunc::max {*}$ds]] [format %.3f [tcl::mathfunc::min {*}$ds]] \
            [format %.3f $skew] $wb] ,]
    }
    close $fh
    puts "delay_table: [dict size $rows] crossing endpoints in [dict size $per] copies"
}
