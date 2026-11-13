# annotate.tcl (brief 65A): read a routed checkpoint and write, as JSON, what the block-design viewer shows per block
# and what hiercheck.py compares: every hierarchical cell (path and module), and for each instance path given, its
# utilisation and the worst setup slack of the timed paths that end inside it.
#   vivado -mode batch -source flow/blockdesign/annotate.tcl -tclargs <post_route.dcp> <out.json> <path> [<path> ...]
set dcp [lindex $argv 0]
set out [lindex $argv 1]
set paths [lrange $argv 2 end]
set_param general.maxThreads 1
open_checkpoint $dcp
report_utilization -hierarchical -hierarchical_depth 12 -file [file rootname $out]_util_hier.rpt
proc jstr {s} { return "\"[string map {\\ \\\\ \" \\\"} $s]\"" }
set f [open $out w]
puts $f "\{\"tool\": [jstr [version -short]],"
puts $f " \"hier\": \["
set rows {}
foreach c [get_cells -hierarchical -filter {IS_PRIMITIVE == 0}] {
    lappend rows "  \{\"path\": [jstr $c], \"module\": [jstr [get_property ORIG_REF_NAME $c]], \"ref\": [jstr [get_property REF_NAME $c]]\}"
}
puts $f [join $rows ",\n"]
puts $f " \],"
puts $f " \"blocks\": \{"
set rows {}
foreach p $paths {
    set cells [get_cells -quiet -hierarchical -filter "NAME =~ $p/* && IS_PRIMITIVE == 1"]
    set lut [llength [filter -quiet $cells {REF_NAME =~ LUT*}]]
    set ff [llength [filter -quiet $cells {REF_NAME =~ FD*}]]
    set b36 [llength [filter -quiet $cells {REF_NAME =~ RAMB36*}]]
    set b18 [llength [filter -quiet $cells {REF_NAME =~ RAMB18*}]]
    set dsp [llength [filter -quiet $cells {REF_NAME =~ DSP*}]]
    set lutram [llength [filter -quiet $cells {REF_NAME =~ RAM*M* || REF_NAME =~ RAM32* || REF_NAME =~ RAM64* || REF_NAME =~ SRL*}]]
    set ends [get_pins -quiet -of_objects [filter -quiet $cells {IS_SEQUENTIAL == 1}] -filter {IS_LEAF == 1 && DIRECTION == IN && (REF_PIN_NAME == D || REF_PIN_NAME =~ DI* || REF_PIN_NAME =~ ADDR* || REF_PIN_NAME == CE || REF_PIN_NAME == R || REF_PIN_NAME == S || REF_PIN_NAME =~ WE*)}]
    set wns "null"
    set nend 0
    if {[llength $ends]} {
        set tp [get_timing_paths -quiet -setup -max_paths 1 -nworst 1 -to $ends]
        if {[llength $tp]} { set wns [format %.3f [get_property SLACK $tp]] }
        set nend [llength $ends]
    }
    lappend rows "  [jstr $p]: \{\"lut\": $lut, \"ff\": $ff, \"ramb36\": $b36, \"ramb18\": $b18, \"dsp\": $dsp, \"lutram_srl\": $lutram, \"wns_ns\": $wns, \"endpoints\": $nend\}"
}
puts $f [join $rows ",\n"]
puts $f " \}\}"
close $f
