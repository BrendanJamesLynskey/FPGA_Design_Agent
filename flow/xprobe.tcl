# xprobe.tcl: machine-readable cross-probing for a routed design (brief 18, section 3).
#
#   vivado -mode batch -source flow/xprobe_run.tcl -tclargs <post_route.dcp> <out xprobe.json> [paths per group and kind, default 5]
#   inside flow/build.tcl (FDA_XPROBE=1):   source flow/xprobe.tcl; xprobe_dump $out/xprobe.json
# This file defines xprobe_dump; xprobe_run.tcl opens a checkpoint and calls it.
#
# What project mode offers by clicking (RTL <-> netlist <-> timing report <-> device view), as data:
#   * for the worst setup and hold paths: start and end cell with RTL file and line (cell properties FILE_NAME and
#     LINE_NUMBER, set by synth_design), hierarchy (PARENT, first level = "module"), placement (LOC, site, CLOCK_REGION
#     of the site, PBLOCK) and the path's nets (fanout, ROUTE_STATUS, routed tiles for fanout <= 50);
#   * the high-fanout nets (FLAT_PIN_COUNT > 50): driver cell, RTL file and line, bounding box in clock regions;
#   * every placed slice register/LUT as (module, slice X, slice Y) and each clock region's slice extent, which is what
#     flow/xprobe.py draws as the device map.
# Items Vivado does not give are written as null (mark_unavailable): RTL line of a net's driver when the driver is a
# primitive from an inferred structure with no FILE_NAME, and CLOCK_REGION of a cell (empty: read it from its site).
proc rel {s} { return [regsub {^.*/FPGA_Design_Agent/} $s {}] }
proc q {s} { return "\"[string map [list \\ \\\\ \" \\\" \n { }] $s]\"" }
proc qn {s} { if {$s eq ""} { return null } else { return [q $s] } }
proc nn {s} { if {$s eq "" || ![string is double -strict $s]} { return null } else { return $s } }
proc top_module {name} { set p [split $name /]; if {[llength $p] > 1} { return [lindex $p 0] } else { return "(top)" } }

proc cell_info {c} {
    set loc [get_property LOC $c]
    set site [expr {$loc eq "" ? "" : [get_sites -quiet $loc]}]
    set cr ""
    if {$site ne ""} { set cr [get_property CLOCK_REGION $site] }
    set name [get_property NAME $c]
    return "{\"cell\": [q $name], \"ref\": [q [get_property REF_NAME $c]], \"module\": [q [top_module $name]],\
 \"parent\": [qn [get_property PARENT $c]], \"file\": [qn [rel [get_property FILE_NAME $c]]], \"line\": [nn [get_property LINE_NUMBER $c]],\
 \"loc\": [qn $loc], \"clock_region\": [qn $cr], \"pblock\": [qn [get_property PBLOCK $c]]}"
}

# routed tiles of a net: the tile prefix of every routing node the net uses (the whole net, not only the branch to one sink:
# walking uphill node by node was minutes per path, so it is not done)
proc route_tiles {n} {
    set seen {}
    foreach nd [get_nodes -quiet -of_objects $n] { dict set seen [lindex [split $nd /] 0] 1 }
    return [dict keys $seen]
}

proc net_info {n full {sink ""}} {
    set fan [get_property FLAT_PIN_COUNT $n]
    set tiles {}
    if {$full && $fan <= 50} { catch {set tiles [route_tiles $n]} }
    set drv [get_cells -quiet -of_objects [get_pins -quiet -leaf -of_objects $n -filter {DIRECTION == OUT}]]
    set d null
    if {[llength $drv]} { set d [cell_info [lindex $drv 0]] }
    return "{\"net\": [q [get_property NAME $n]], \"fanout\": [nn $fan], \"route_status\": [qn [get_property ROUTE_STATUS $n]],\
 \"driver\": $d, \"tiles\": \[[join [lmap t $tiles {q $t}] {, }]\]}"
}

proc path_info {p kind} {
    set cells [get_cells -quiet -of_objects [get_pins -quiet -of_objects $p]]
    set sc [get_cells -quiet -of_objects [get_pins [get_property STARTPOINT_PIN $p]]]
    set ec [get_cells -quiet -of_objects [get_pins [get_property ENDPOINT_PIN $p]]]
    set nets [get_nets -quiet -of_objects $p]
    set ni {}
    set ppins [get_pins -quiet -of_objects $p]
    foreach n $nets {
        set sink [lindex [get_pins -quiet -of_objects $n -filter {DIRECTION == IN}] 0]
        foreach pp $ppins { if {[get_property DIRECTION $pp] eq "IN" && [get_nets -quiet -of_objects $pp] eq $n} { set sink $pp; break } }
        lappend ni [net_info $n 1 $sink]
    }
    set ci {}
    foreach c $cells { lappend ci [cell_info $c] }
    return "{\"kind\": [q $kind], \"slack\": [nn [get_property SLACK $p]], \"group\": [q "[get_property STARTPOINT_CLOCK $p] -> [get_property ENDPOINT_CLOCK $p]"],\
 \"datapath_delay\": [nn [get_property DATAPATH_DELAY $p]], \"logic_delay\": [nn [get_property DATAPATH_LOGIC_DELAY $p]], \"net_delay\": [nn [get_property DATAPATH_NET_DELAY $p]],\
 \"logic_levels\": [nn [get_property LOGIC_LEVELS $p]],\
 \"start\": [cell_info $sc], \"end\": [cell_info $ec], \"cells\": \[[join $ci {, }]\], \"nets\": \[[join $ni {, }]\]}"
}

proc xprobe_dump {json {npaths 5} {dcp ""}} {
    # --- worst paths: setup and hold, the worst per clock-pair group first --------------------------------------------
    set plist {}
    foreach kind {setup hold} {
        set flag [expr {$kind eq "setup" ? "-setup" : "-hold"}]
        set seen {}
        foreach p [get_timing_paths $flag -max_paths 200 -nworst 1 -unique_pins] {
            set g "[get_property STARTPOINT_CLOCK $p]>[get_property ENDPOINT_CLOCK $p]"
            dict incr seen $g
            if {[dict get $seen $g] > $npaths} { continue }
            lappend plist [path_info $p $kind]
        }
    }
    # --- high-fanout nets ----------------------------------------------------------------------------------------------
    set hf {}
    set cand {}
    foreach n [get_nets -hier -quiet -filter {TYPE == SIGNAL && FLAT_PIN_COUNT > 50}] { lappend cand [list [get_property FLAT_PIN_COUNT $n] $n] }
    set seen_drv {}
    foreach pr [lsort -integer -decreasing -index 0 $cand] {
        if {[llength $hf] >= 10} { break }
        set n [lindex $pr 1]
        # get_nets -hier lists one net under every hierarchical alias: keep one per driver pin
        set dp [get_pins -quiet -leaf -of_objects $n -filter {DIRECTION == OUT}]
        if {[dict exists $seen_drv $dp]} { continue }
        dict set seen_drv $dp 1
        set pins [get_pins -quiet -leaf -of_objects $n -filter {DIRECTION == IN}]
        set regs {}
        foreach c [get_cells -quiet -of_objects $pins] {
            set loc [get_property LOC $c]
            if {$loc ne ""} { set s [get_sites -quiet $loc]; if {$s ne ""} { dict incr regs [get_property CLOCK_REGION $s] } }
        }
        set rj {}
        dict for {k v} $regs { lappend rj "\"$k\": $v" }
        set lr [join $rj ", "]
        lappend hf "[string range [net_info $n 0] 0 end-1], \"load_regions\": \{$lr\}\}"
    }
    # --- device map: clock regions and placed slice cells ------------------------------------------------------------
    set crs {}
    foreach cr [get_clock_regions] {
        set xs {}; set ys {}
        foreach s [get_sites -quiet -of_objects $cr -filter {SITE_TYPE =~ SLICE*}] {
            if {[regexp {SLICE_X(\d+)Y(\d+)} [get_property NAME $s] -> x y]} { lappend xs $x; lappend ys $y }
        }
        if {[llength $xs]} {
            set xs [lsort -integer $xs]; set ys [lsort -integer $ys]
            lappend crs "{\"name\": [q [get_property NAME $cr]], \"x0\": [lindex $xs 0], \"x1\": [lindex $xs end], \"y0\": [lindex $ys 0], \"y1\": [lindex $ys end]}"
        }
    }
    set mods {}; set midx {}
    set cells {}
    foreach c [get_cells -hier -quiet -filter {PRIMITIVE_LEVEL == LEAF && IS_PRIMITIVE}] {
        set loc [get_property LOC $c]
        if {![regexp {SLICE_X(\d+)Y(\d+)} $loc -> x y]} { continue }
        set m [top_module [get_property NAME $c]]
        if {![dict exists $midx $m]} { dict set midx $m [dict size $midx]; lappend mods $m }
        lappend cells "\[[dict get $midx $m], $x, $y\]"
    }
    set wns [get_property SLACK [lindex [get_timing_paths -setup -max_paths 1] 0]]
    set whs [get_property SLACK [lindex [get_timing_paths -hold -max_paths 1] 0]]
    set f [open $json w]
    puts $f "{\"dcp\": [q [rel $dcp]], \"part\": [q [get_property PART [current_design]]], \"vivado\": [q [version -short]], \"wns\": [nn $wns], \"whs\": [nn $whs],\
     \"paths\": \[[join $plist ",\n"]\],\n\"high_fanout_nets\": \[[join $hf ",\n"]\],\n\"clock_regions\": \[[join $crs {, }]\],\n\"modules\": \[[join [lmap m $mods {q $m}] {, }]\],\n\"slice_cells\": \[[join $cells {,}]\]}"
    close $f
    puts "XPROBE-DONE $json"
}
