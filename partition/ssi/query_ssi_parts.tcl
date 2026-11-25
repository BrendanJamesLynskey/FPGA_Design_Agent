# query_ssi_parts.tcl (brief 151, owner scope note 2026-11-22): which parts of the installed Vivado device support have more than one SLR (SSI), by family and by name pattern. Run: OUT=results/b151/ssi_parts_query.txt vivado -mode batch -source this file. Light: no synthesis, no implementation.
set fh [open $::env(OUT) w]
array set fam {}; array set slr {}
foreach p [get_parts] {
    set f [get_property FAMILY $p]; set s [get_property SLRS $p]
    if {![info exists fam($f)]} { set fam($f) 0 }; incr fam($f)
    if {![info exists slr($s)]} { set slr($s) 0 }; incr slr($s)
}
puts $fh "families: [array get fam]"
puts $fh "SLRS values: [array get slr]"
foreach pat {xcvu* xcku* xcvc* xcvm* xcvp* xcve* xcvh* xc7v*} { puts $fh "$pat [llength [get_parts $pat]]" }
close $fh
