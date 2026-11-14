# vivado_checks.tcl: the Vivado side of the check suite (brief 71, flow/checks).
#
#   vivado -mode batch -source flow/checks/vivado_checks.tcl -tclargs <checkpoint.dcp> <out_dir> <report,report,...>
#
# Opens ONE checkpoint (post_synth.dcp or post_route.dcp) once and runs every requested report in it, in sequence,
# writing <out_dir>/<name>.rpt (or reset_scan.tsv). A report the licence tier or the tool refuses writes
# <out_dir>/<name>.not_run.txt with Vivado's message instead, so the Python side can say why it did not run.
# AMD's own reports come first (report_methodology, report_drc, report_cdc, report_control_sets, ...); the only
# report of ours is reset_scan: one row per register whose reset pin is not tied to a constant, with the reset's
# root driver traced through buffers and LUT1 inverters (flow/checks/resets.py classifies the rows).
#
# Sourced with ::fda_checks_lib set (the seeded-fault runner), it only defines the procs.

set ::fda_checks_dir [file dirname [file normalize [info script]]]

proc fda_hier_refs {cell} {
    # the hierarchical parents' module names, innermost first ("/"-joined): ORIG_REF_NAME when set, else REF_NAME
    global fda_hcache
    set parent [get_property -quiet PARENT $cell]
    if {$parent eq ""} { return "" }
    if {[info exists fda_hcache($parent)]} { return $fda_hcache($parent) }
    set pc [get_cells -quiet $parent]
    set name ""
    if {$pc ne ""} {
        set name [get_property -quiet ORIG_REF_NAME $pc]
        if {$name eq ""} { set name [get_property -quiet REF_NAME $pc] }
        set up [fda_hier_refs $pc]
        if {$up ne ""} { set name "$name/$up" }
    }
    set fda_hcache($parent) $name
    return $name
}

proc fda_walk {net} {
    # {kind root root_ref inverted path}: the reset net's root driver, through buffers and LUT1 cells
    set inv 0
    set path {}
    for {set i 0} {$i < 16} {incr i} {
        if {$net eq ""} { return [list none "" "" $inv $path] }
        set drv [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}]
        if {[llength $drv] == 0} {
            set p [get_ports -quiet -of_objects [get_nets -quiet -segments $net]]
            if {[llength $p]} { return [list port [lindex $p 0] "" $inv $path] }
            return [list none "" "" $inv $path]
        }
        set c [get_cells -of_objects [lindex $drv 0]]
        set ref [get_property REF_NAME $c]
        if {$ref eq "GND" || $ref eq "VCC"} { return [list const $ref $ref $inv $path] }
        if {[regexp {^(IBUF|IBUF_IBUFDISABLE|IBUF_INTERMDISABLE|IBUFDS|IBUFG|BUFG|BUFGCE|BUFGCE_DIV|BUFH|BUFHCE|BUFR|BUFG_GT|BUFGCTRL|BUFGMUX|BUF)$} $ref]} {
            lappend path $ref
            set net [get_nets -quiet -of_objects [get_pins -quiet -filter {DIRECTION == IN && REF_PIN_NAME =~ I*} -of_objects $c]]
            set net [lindex $net 0]
            continue
        }
        if {$ref eq "LUT1"} {
            lappend path LUT1
            if {[regexp {1$} [get_property INIT $c]]} { set inv [expr {!$inv}] }
            set net [get_nets -quiet -of_objects [get_pins -quiet $c/I0]]
            continue
        }
        return [list cell $c $ref $inv $path]
    }
    return [list deep "" "" $inv $path]
}

proc fda_reset_scan {fname} {
    # one TSV row per register with a reset pin that is not tied to a constant; DSP and block-RAM reset pins too (rows
    # with their primitive's name as ref), for the polarity and clock-domain rules. Written to a temporary file and
    # renamed at the end, so an error never leaves a partial scan that looks complete.
    global fda_hcache
    array unset fda_hcache
    set f [open $fname.part w]
    puts $f [join {cell ref pin pin_inverted clock hier root_kind root root_ref root_inverted path root_clock root_async_reg root_hier d_ref q_refs} "\t"]
    array set walk {}
    array set clk {}
    set pinof [dict create FDRE R FDSE S FDCE CLR FDPE PRE LDCE CLR LDPE PRE]
    foreach c [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE && (REF_NAME =~ FD* || REF_NAME =~ LD*)}] {
        set ref [get_property REF_NAME $c]
        if {![dict exists $pinof $ref]} { continue }
        set pn [dict get $pinof $ref]
        set pin [get_pins -quiet $c/$pn]
        set net [get_nets -quiet -of_objects $pin]
        if {$net eq ""} { continue }
        if {![info exists walk($net)]} { set walk($net) [fda_walk $net] }
        lassign $walk($net) kind root rref rinv path
        if {$kind eq "const"} { continue }
        set pinv [get_property -quiet IS_${pn}_INVERTED $c]
        if {$pinv eq ""} { set pinv 0 }
        set cpin [lindex [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == C || REF_PIN_NAME == G}] 0]
        set cnet [get_nets -quiet -of_objects $cpin]
        if {![info exists clk($cnet)]} { set clk($cnet) [join [get_clocks -quiet -of_objects $cpin] ","] }
        set rclk ""; set rasync ""; set rhier ""
        if {$kind eq "cell"} {
            if {[string match FD* $rref]} {
                set rclk [join [get_clocks -quiet -of_objects [get_pins -quiet $root/C]] ","]
                set rasync [get_property -quiet ASYNC_REG $root]
            }
            set rhier [fda_hier_refs $root]
        }
        set dref ""; set qrefs ""
        if {$ref in {FDCE FDPE LDCE LDPE}} {
            set dn [get_nets -quiet -of_objects [get_pins -quiet $c/D]]
            if {$dn ne ""} { set dref [join [lsort -unique [get_property -quiet REF_NAME [get_cells -quiet -of_objects [get_pins -quiet -leaf -of_objects $dn -filter {DIRECTION == OUT}]]]] ","] }
            set qn [get_nets -quiet -of_objects [get_pins -quiet $c/Q]]
            if {$qn ne ""} { set qrefs [join [lsort -unique [get_property -quiet REF_NAME [get_cells -quiet -of_objects [get_pins -quiet -leaf -of_objects $qn -filter {DIRECTION == IN && REF_PIN_NAME !~ RST* && REF_PIN_NAME !~ *RST*}]]]] ","] }
        }
        puts $f [join [list $c $ref $pn $pinv $clk($cnet) [fda_hier_refs $c] $kind $root $rref $rinv [join $path ">"] $rclk $rasync $rhier $dref $qrefs] "\t"]
    }
    foreach c [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE && (REF_NAME =~ DSP48* || REF_NAME =~ RAMB*)}] {
        set ref [get_property REF_NAME $c]
        set ck [lindex [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == CLK || REF_PIN_NAME == CLKARDCLK || REF_PIN_NAME == CLKBWRCLK}] 0]
        set cks [expr {$ck eq "" ? "" : [join [get_clocks -quiet -of_objects $ck] ","]}]
        foreach pin [get_pins -quiet -of_objects $c -filter {DIRECTION == IN && REF_PIN_NAME =~ RST*}] {
            set net [get_nets -quiet -of_objects $pin]
            if {$net eq ""} { continue }
            if {![info exists walk($net)]} { set walk($net) [fda_walk $net] }
            lassign $walk($net) kind root rref rinv path
            if {$kind eq "const" || $kind eq "none"} { continue }
            set pn [get_property REF_PIN_NAME $pin]
            set pinv [get_property -quiet IS_${pn}_INVERTED $c]
            if {$pinv eq ""} { set pinv 0 }
            set rclk ""; set rasync ""; set rhier ""
            if {$kind eq "cell"} {
                if {[string match FD* $rref]} {
                    set rclk [join [get_clocks -quiet -of_objects [get_pins -quiet $root/C]] ","]
                    set rasync [get_property -quiet ASYNC_REG $root]
                }
                set rhier [fda_hier_refs $root]
            }
            puts $f [join [list $c $ref $pn $pinv $cks [fda_hier_refs $c] $kind $root $rref $rinv [join $path ">"] $rclk $rasync $rhier "" ""] "\t"]
        }
    }
    close $f
    file rename -force $fname.part $fname
}

proc fda_rule_catalogue {fname} {
    # every methodology and DRC rule this Vivado release knows: id, severity, description (verifies the rule ids we map)
    set f [open $fname w]
    foreach c [get_methodology_checks] {
        puts $f [join [list methodology $c [get_property -quiet SEVERITY $c] [get_property -quiet DESCRIPTION $c]] "\t"]
    }
    foreach c [get_drc_checks] {
        puts $f [join [list drc $c [get_property -quiet SEVERITY $c] [get_property -quiet DESCRIPTION $c]] "\t"]
    }
    close $f
}

proc fda_report {name out} {
    # one requested report; a refusal (licence tier, unsupported on this design) is recorded, never fatal
    set cmds [dict create \
        methodology       [list report_methodology -file $out/methodology.rpt] \
        drc               [list report_drc -file $out/drc.rpt] \
        cdc               [list report_cdc -details -file $out/cdc.rpt] \
        control_sets      [list report_control_sets -verbose -file $out/control_sets.rpt] \
        high_fanout       [list report_high_fanout_nets -timing -load_types -max_nets 25 -file $out/high_fanout.rpt] \
        qor_suggestions   [list report_qor_suggestions -file $out/qor_suggestions.rpt] \
        clock_interaction [list report_clock_interaction -delay_type min_max -file $out/clock_interaction.rpt] \
        timing_summary    [list report_timing_summary -max_paths 10 -report_unconstrained -file $out/timing_summary.rpt] \
        utilization       [list report_utilization -file $out/utilization.rpt]]
    if {$name eq "reset_scan"} {
        set cmd [list fda_reset_scan $out/reset_scan.tsv]
    } elseif {$name eq "cmt"} {
        # flow/cmt_check.tcl (brief 18): VCO and PFD legality of hand-instantiated MMCME2/PLLE2 (7-series)
        source [file join $::fda_checks_dir .. cmt_check.tcl]
        set cmd [list cmt_check $out/cmt.rpt]
    } elseif {$name eq "rule_catalogue"} {
        set cmd [list fda_rule_catalogue $out/rule_catalogue.tsv]
    } elseif {[dict exists $cmds $name]} {
        set cmd [dict get $cmds $name]
    } else {
        set f [open $out/$name.not_run.txt w]; puts $f "unknown report $name"; close $f
        return
    }
    set t0 [clock milliseconds]
    if {[catch {uplevel #0 $cmd} err]} {
        set f [open $out/$name.not_run.txt w]
        puts $f "$name not run: $err"
        close $f
    }
    puts "FDA-CHECK $name [expr {[clock milliseconds] - $t0}] ms"
}

if {![info exists ::fda_checks_lib]} {
    lassign $argv dcp out names
    set_param general.maxThreads 1
    file mkdir $out
    open_checkpoint $dcp
    foreach n [split $names ","] { fda_report $n $out }
    puts "FDA-CHECKS-DONE"
}
