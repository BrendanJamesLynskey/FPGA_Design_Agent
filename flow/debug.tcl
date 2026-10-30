# debug.tcl: insert an ILA into a synthesised design from the design's probes.yaml
# (converted to probes.tcl by flow/prepare.py). Sourced by build.tcl after
# synth_design when the build variant is "ila"; opt_design then implements the
# debug core, and build.tcl writes the .ltx probes file next to the bitstream.
#
# Every probe's nets must exist after synthesis with exactly the stated width;
# if not, the build stops and lists close matches, rather than quietly probing
# something else.

proc probe_nets {pattern width} {
    set nets [get_nets -quiet $pattern]
    if {[llength $nets] != $width} {
        set leaf [lindex [split $pattern /] end]
        regsub {\[\*\]$} $leaf {} stem
        set near [get_nets -quiet -hierarchical -filter "NAME =~ *${stem}*"]
        error "debug.tcl: '$pattern' matched [llength $nets] nets, expected $width. Nets like it: [lrange $near 0 20]"
    }
    # Order bus bits by index so probe bit i is net bit i
    if {$width > 1} {
        set nets [lsort -command {apply {{a b} {
            regexp {\[(\d+)\]$} $a -> ia; regexp {\[(\d+)\]$} $b -> ib
            expr {$ia - $ib}
        }}} $nets]
    }
    return $nets
}

proc insert_ila {probes_tcl out} {
    source $probes_tcl
    create_debug_core $ila_name ila
    set core [get_debug_cores $ila_name]
    set_property C_DATA_DEPTH          $ila_depth $core
    set_property C_INPUT_PIPE_STAGES   $ila_pipe  $core
    set_property C_TRIGIN_EN           false      $core
    set_property C_TRIGOUT_EN          false      $core
    set_property C_ADV_TRIGGER         false      $core
    set_property C_EN_STRG_QUAL        false      $core
    set_property ALL_PROBE_SAME_MU     true       $core
    set_property ALL_PROBE_SAME_MU_CNT 1          $core
    set_property port_width 1 [get_debug_ports $ila_name/clk]
    connect_debug_port $ila_name/clk [get_nets $ila_clock_net]

    set map [open $out/probe_map.txt w]
    set i 0
    foreach pr $ila_probes {
        lassign $pr name pattern width
        set nets [probe_nets $pattern $width]
        if {$i > 0} { create_debug_port $ila_name probe }
        set port $ila_name/probe$i
        set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports $port]
        set_property port_width $width [get_debug_ports $port]
        connect_debug_port $port $nets
        puts $map [format "probe%-3d %-12s %3d  %s" $i $name $width $pattern]
        incr i
    }
    close $map

    # The debug hub runs from the same clock (JTAG-to-hub clock domain crossing is the hub's job)
    set_property C_CLK_INPUT_FREQ_HZ 100000000 [get_debug_cores dbg_hub]
    set_property C_ENABLE_CLK_DIVIDER false     [get_debug_cores dbg_hub]
    set_property C_USER_SCAN_CHAIN 1            [get_debug_cores dbg_hub]
    connect_debug_port dbg_hub/clk [get_nets $ila_clock_net]
    puts "debug.tcl: ILA $ila_name with $i probes, depth $ila_depth"
}
