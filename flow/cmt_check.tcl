# cmt_check.tcl: VCO and PFD legality of every MMCME2 / PLLE2 in the synthesised netlist (brief 18, section 2b).
#
#   source flow/cmt_check.tcl; cmt_check <report file>
#
# The Clocking Wizard refuses an out-of-range setting and reports jitter; a hand-instantiated MMCME2/PLLE2 gets neither: neither
# report_drc nor report_methodology rejects a VCO outside the speed grade's range (measured, KB skill artix7-mmcm-pll-configuration,
# and again here). This reads DIVCLK_DIVIDE, CLKFBOUT_MULT(_F) and CLKIN1_PERIOD from each primitive and writes one line per
# primitive: "CMT <cell> <MMCM|PLL> VCO <MHz> PFD <MHz> <OK|VIOLATION> <reason>". 7-series only (DS181 v1.27.1 Tables 37 and 38,
# DS187 likewise): MMCM VCO 600 to 1200 / 1440 / 1600 MHz for -1 / -2 / -3, PLL VCO 800 to 1600 / 1866 / 2133 MHz, PFD
# 10 (MMCM) or 19 (PLL) to 450 MHz. Other families: the line says "not checked".
proc cmt_check {rpt} {
    set f [open $rpt w]
    set fam [string tolower [get_property FAMILY [get_parts [get_property PART [current_design]]]]]
    set sg [get_property SPEED [get_parts [get_property PART [current_design]]]]
    set n 0
    foreach c [get_cells -hier -quiet -filter {REF_NAME =~ MMCME2_* || REF_NAME =~ PLLE2_*}] {
        incr n
        set ref [get_property REF_NAME $c]
        set mm [string match MMCME2_* $ref]
        if {![regexp {^(artix7|kintex7|virtex7|zynq|spartan7)} $fam]} {
            puts $f "CMT [get_property NAME $c] [expr {$mm ? "MMCM" : "PLL"}] not checked (family $fam)"
            continue
        }
        set d [get_property DIVCLK_DIVIDE $c]
        set m [expr {$mm ? [get_property CLKFBOUT_MULT_F $c] : [get_property CLKFBOUT_MULT $c]}]
        set tin [get_property CLKIN1_PERIOD $c]
        if {$tin eq "" || $tin == 0 || $tin == 0.0} {
            puts $f "CMT [get_property NAME $c] [expr {$mm ? "MMCM" : "PLL"}] VIOLATION CLKIN1_PERIOD not set (timing uses a wrong input period)"
            continue
        }
        set fin [expr {1000.0 / $tin}]
        set pfd [expr {$fin / $d}]
        set vco [expr {$pfd * $m}]
        set idx [expr {[string match *-3* $sg] ? 2 : ([string match *-2* $sg] ? 1 : 0)}]
        if {$mm} {
            set vmin 600.0; set vmax [lindex {1200.0 1440.0 1600.0} $idx]; set pmin 10.0
        } else {
            set vmin 800.0; set vmax [lindex {1600.0 1866.0 2133.0} $idx]; set pmin 19.0
        }
        set why {}
        if {$vco < $vmin || $vco > $vmax} { lappend why "VCO $vco MHz outside $vmin-$vmax MHz for speed grade $sg" }
        if {$pfd < $pmin || $pfd > 450.0} { lappend why "PFD $pfd MHz outside $pmin-450 MHz" }
        set kind [expr {$mm ? "MMCM" : "PLL"}]
        puts $f [format "CMT %s %s VCO %.3f PFD %.3f %s %s" [get_property NAME $c] $kind $vco $pfd \
            [expr {[llength $why] ? "VIOLATION" : "OK"}] [join $why "; "]]
    }
    if {$n == 0} { puts $f "CMT none" }
    close $f
}
