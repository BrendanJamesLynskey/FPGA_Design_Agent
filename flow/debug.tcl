# debug.tcl: insert an ILA into a synthesised design from the design's probes.yaml
# (converted to probes.tcl by flow/prepare.py). Sourced by build.tcl after
# synth_design when the build variant is "ila"; opt_design then implements the
# debug core, and build.tcl writes the .ltx probes file next to the bitstream.
#
# Every probe's pins must exist after synthesis with exactly the stated width;
# if not, the build stops and lists close matches, rather than quietly probing
# something else.

proc probe_nets {pattern width} {
    # Probes name register output pins (e.g. u_dut/count_reg[*]/Q): register
    # names survive synthesis, while net names get merged across the hierarchy
    # (u_dut/count[0] becomes the top-level net count[0]).
    set pins [get_pins -quiet $pattern]
    if {[llength $pins] != $width} {
        set cell [lindex [split $pattern /] end-1]
        regsub {\[\*\]$} $cell {} stem
        set near [lsort [get_cells -quiet -hierarchical -filter "NAME =~ *${stem}*"]]
        error "debug.tcl: '$pattern' matched [llength $pins] pins, expected $width. Cells like it: [lrange $near 0 20]"
    }
    # Order bus bits by their last index, so probe bit i is register bit i
    if {$width > 1} {
        set pins [lsort -command {apply {{a b} {
            regexp {\[(\d+)\]/[^/]+$} $a -> ia; regexp {\[(\d+)\]/[^/]+$} $b -> ib
            expr {$ia - $ib}
        }}} $pins]
    }
    set nets {}
    foreach p $pins { lappend nets [get_nets -of_objects $p] }
    return $nets
}

proc insert_ila_core {probes_tcl out} {
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
        puts $map [format "probe%-3d %-12s %3d %3d  %s" $i $name $width 0 $pattern]
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

# --- brief 48: the ILA as an IP, not as a debug core -----------------------------------------------------------------
# Vivado 2026.1 on the free Basic licence tier refuses the debug-core Tcl commands (create_debug_core: Vivado 12-29205), but
# generates, synthesises, places, routes and writes a bitstream for the ILA *IP* (measured, brief 48). So the same probe list
# is built as an ILA IP with matching probe widths, added to the synthesised netlist as a black box that is filled from the
# IP's checkpoint (create_cell -black_box, read_checkpoint -cell), with every probe pin wired to the same register-output nets
# as insert_ila_core would have used, packed into at most 5 probe ports (the Basic tier's limit, flow/prepare.py pack_probes). Only the debug build gets it. The debug hub is added by opt_design. probe_map.txt, the
# probe order and the .ltx keep their meaning, so flow/ila_capture.tcl, flow/ila.py and the exception gate are unchanged.
proc insert_ila_ip {probes_tcl out} {
    source $probes_tcl
    set n [llength $ila_ports]
    if {$n > 5} { error "debug.tcl: $n ILA ports; the Basic licence tier allows 5 (Chipscope 16-620)" }
    set ipdir $out/ila_ip
    file delete -force $ipdir      ;# a clean IP directory per build (filemgmt 20-1440: the dcp was already in the project)
    file mkdir $ipdir
    set ipname fda_ila
    create_ip -name ila -vendor xilinx.com -library ip -module_name $ipname -dir $ipdir
    set ip [get_ips $ipname]
    set cfg [list CONFIG.C_NUM_OF_PROBES $n CONFIG.C_DATA_DEPTH $ila_depth CONFIG.C_INPUT_PIPE_STAGES $ila_pipe \
                 CONFIG.C_TRIGIN_EN false CONFIG.C_TRIGOUT_EN false CONFIG.C_ADV_TRIGGER false CONFIG.C_EN_STRG_QUAL false \
                 CONFIG.ALL_PROBE_SAME_MU true CONFIG.ALL_PROBE_SAME_MU_CNT 1]
    set i 0
    foreach port $ila_ports { lappend cfg CONFIG.C_PROBE${i}_WIDTH [lindex $port 0]; incr i }
    set_property -dict $cfg $ip
    generate_target all $ip
    synth_ip $ip
    set dcp [lindex [glob $ipdir/$ipname/$ipname.dcp] 0]

    create_cell -reference $ipname -black_box $ila_name
    create_pin -direction IN $ila_name/clk
    set i 0
    foreach port $ila_ports {
        create_pin -direction IN -from 0 -to [expr {[lindex $port 0] - 1}] $ila_name/probe$i
        incr i
    }
    read_checkpoint -cell $ila_name $dcp
    connect_net -net [get_nets $ila_clock_net] -objects [get_pins $ila_name/clk]

    # probe_map.txt: one line per named probe: probe<port> <name> <width> <bit offset in the port> <pins>
    set map [open $out/probe_map.txt w]
    set pn [open $out/probe_nets.txt w]      ;# <port> <bit> <net name>: flow/ltx_fix.py needs it (write_debug_probes can lose a bus bit's name)
    set i 0
    set nprobes 0
    foreach port $ila_ports {
        foreach sl [lrange $port 1 end] {
            lassign $sl name pattern width offset
            set nets [probe_nets $pattern $width]
            # every connection is checked: the pin must exist, and must be on a net afterwards (a connect_net that only warns
            # leaves the probe port open, which opt_design reports much later as Chipscope 16-213)
            set ok 0
            for {set b 0} {$b < $width} {incr b} {
                set pin [get_pins -quiet "$ila_name/probe${i}\[[expr {$offset + $b}]\]"]
                if {$pin eq ""} { error "debug.tcl: no pin $ila_name/probe${i}\[[expr {$offset + $b}]\] (pins: [lrange [get_pins -of_objects [get_cells $ila_name]] 0 8])" }
                connect_net -hier -net [lindex $nets $b] -objects $pin
                set onnet [get_nets -quiet -of_objects $pin]
                if {$onnet ne ""} { incr ok; puts $pn "$i [expr {$offset + $b}] $onnet" }
            }
            if {$ok != $width} { error "debug.tcl: probe $name: connected $ok of $width bits to $ila_name/probe$i at offset $offset" }
            puts $map [format "probe%-3d %-12s %3d %3d  %s" $i $name $width $offset $pattern]
            incr nprobes
        }
        incr i
    }
    close $map
    # The debug hub: opt_design adds it, but cannot find its clock for an ILA put into the netlist this way (Chipscope 16-213:
    # dbg_hub/clk has 1 unconnected channels, which stops opt_design). So make the hub now and give it the ILA's clock, as
    # insert_ila_core does. (Measured, brief 48: with or without the hub's own properties the hub's constraint script prints the same
    # CRITICAL WARNINGs, which flow/exceptions_check.py lists as EXC-XDC-DEBUG-HUB.)
    implement_debug_core
    connect_debug_port dbg_hub/clk [get_nets $ila_clock_net]
    # checked here, not 20 s later in opt_design: the hub clock port must now be on the clock net
    set hubclk [get_nets -quiet -of_objects [get_pins -quiet dbg_hub/clk]]
    if {[llength [get_pins -quiet dbg_hub/clk]] && $hubclk eq ""} { error "debug.tcl: dbg_hub/clk is not connected after connect_debug_port" }
    puts "debug.tcl: ILA IP $ila_name ($ipname) with $nprobes probes packed into $n ports, depth $ila_depth"
}

# FDA_ILA_INSERT=core selects the old create_debug_core path (needs a licence tier that allows it, for example 2025.2 Basic);
# the default is the IP route.
proc insert_ila {probes_tcl out} {
    set mode [expr {[info exists ::env(FDA_ILA_INSERT)] && $::env(FDA_ILA_INSERT) ne "" ? $::env(FDA_ILA_INSERT) : "ip"}]
    switch -- $mode {
        core    { insert_ila_core $probes_tcl $out }
        ip      { insert_ila_ip   $probes_tcl $out }
        default { error "debug.tcl: FDA_ILA_INSERT must be ip or core, not '$mode'" }
    }
}
