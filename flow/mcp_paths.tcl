# mcp_paths.tcl (brief 20): every multicycle exception of the open design, the registers it names, and their clock enables.
# Vivado 2025.2 raised no TIMING-46 for a multicycle on registers whose CE is tied high (fixture E3, after synthesis and
# after routing), so flow/exceptions_check.py checks the enables itself from this dump (rule EXC-MCP-ENABLE).
#   source flow/mcp_paths.tcl; mcp_dump_paths <out file>
# CLOCK|<name>|<period>
# EXC|<position>|<setup or hold>|<N>|<start or end>|<from expression>|<to expression>
# CELL|<position>|<from or to>|<cell>|<clock>|<CE tied 1/0, or none>|<sequential cells in the CE pin's fan-in, comma separated>
# ERROR|<what>|<message>
# The file ends with "# end". The registers come from re-evaluating each exception's -from/-to object query as
# report_exceptions prints it (cells, or the cells of pins; a clock or port end is listed as such and not checked). This
# is a walk over the named cells (one all_fanin per CE pin), not a path enumeration: enumerating every relaxed path took
# 5 minutes and 6.5 GB on a 16x16 multiply, so it is not used.

proc mcp__cells {expr} {
    if {$expr eq "*" || $expr eq ""} { return [list "*" {}] }
    set objs [uplevel #0 [list subst $expr]]
    set cells {}
    set kind cells
    foreach o $objs {
        set c [get_property -quiet CLASS $o]
        switch -- $c {
            cell { lappend cells $o }
            pin  { lappend cells [get_cells -quiet -of_objects $o] }
            clock { set kind clocks }
            port { set kind ports }
        }
    }
    return [list $kind [lsort -unique $cells]]
}

proc mcp_dump_paths {outf} {
    set out [open $outf w]
    foreach c [get_clocks -quiet] { puts $out "CLOCK|[get_property NAME $c]|[get_property PERIOD $c]" }
    set rep [report_exceptions -return_string]
    set lines [split $rep "\n"]
    set spans {}
    set names {}
    for {set i 0} {$i < [llength $lines] - 1} {incr i} {
        set h [lindex $lines $i]
        set r [lindex $lines [expr {$i + 1}]]
        if {[string match "Position*" $h] && [regexp {^[- ]+$} $r] && [string match "*-*" $r]} {
            foreach ix [regexp -all -inline -indices -- {-+} $r] { lappend spans $ix }
            set first [expr {$i + 2}]
            break
        }
    }
    if {$spans eq ""} { puts $out "# end"; close $out; return }
    set ncol [llength $spans]
    set done {}
    for {set i $first} {$i < [llength $lines]} {incr i} {
        set row [lindex $lines $i]
        if {![regexp {^\d+\s} $row]} { if {[string trim $row] eq ""} { break } else { continue } }
        set cols {}
        for {set k 0} {$k < $ncol} {incr k} {
            set a [lindex [lindex $spans $k] 0]
            set b [expr {$k + 1 < $ncol ? [lindex [lindex $spans [expr {$k + 1}]] 0] - 1 : [string length $row]}]
            lappend cols [string trim [string range $row $a $b]]
        }
        lassign $cols pos from thru to setup hold
        set kind ""
        if {[regexp {cycles=(\d+)(\((start|end)\))?} $setup -> n - edge]} {
            set kind setup
            if {$edge eq ""} { set edge end }
        } elseif {[regexp {cycles=(\d+)(\((start|end)\))?} $hold -> n - edge]} {
            set kind hold
            if {$edge eq ""} { set edge start }
        }
        if {$kind eq ""} { continue }
        puts $out "EXC|$pos|$kind|$n|$edge|$from|$to"
        foreach side {from to} expr [list $from $to] {
            if {[catch {lassign [mcp__cells $expr] what cells} err]} { puts $out "ERROR|$pos $side|$err"; continue }
            if {$what ne "cells"} { puts $out "CELL|$pos|$side|<$what>||none|"; continue }
            foreach c $cells {
                if {[catch {
                    set clk [get_clocks -quiet -of_objects [get_pins -quiet -filter {IS_CLOCK} -of_objects [get_cells $c]]]
                    set ce [get_pins -quiet -filter {REF_PIN_NAME == CE} -of_objects [get_cells $c]]
                    if {$ce eq ""} {
                        puts $out "CELL|$pos|$side|$c|[lindex $clk 0]|none|"
                    } else {
                        set net [get_nets -quiet -of_objects $ce]
                        set tied [expr {[lsearch -exact {POWER GROUND} [get_property TYPE $net]] >= 0 ? 1 : 0}]
                        set regs {}
                        foreach q [all_fanin -quiet -flat -startpoints_only $ce] {
                            set qc [get_cells -quiet -of_objects $q]
                            if {$qc ne "" && [get_property IS_SEQUENTIAL $qc]} { lappend regs $qc }
                        }
                        puts $out "CELL|$pos|$side|$c|[lindex $clk 0]|$tied|[join [lsort -unique $regs] ,]"
                    }
                } err]} { puts $out "ERROR|$c|$err" }
            }
        }
    }
    puts $out "# end"
    close $out
}
