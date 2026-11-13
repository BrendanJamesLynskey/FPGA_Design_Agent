# connect.tcl: the connectivity the block-design check (hiercheck.py) compares with the graph's links.
# The routed netlist cannot answer "which RTL port drives which": synthesis rebuilds the hierarchy's boundaries (pins
# become D[0], Q[0]) and moves logic across them. So this synthesises the same sources again with the hierarchy kept
# (synth_design -flatten_hierarchy none), and writes, for each hierarchical cell directly inside the top or inside a
# generated module (the names in <genmods>, one per line), each of its pins with its direction and the net it meets one
# level up (two pins on the same net are wired to each other there; "" for a pin left unconnected or tied to a
# constant), and every hierarchical cell (path and module).
#   vivado -mode batch -source flow/blockdesign/connect.tcl -tclargs <build>/inputs.tcl <out.json> <genmods.txt>
set inputs [lindex $argv 0]
set outj [lindex $argv 1]
set gm [open [lindex $argv 2]]
set genmods [split [string trim [read $gm]] "\n"]
close $gm
source $inputs
set_param general.maxThreads 1
foreach f $sources { read_verilog -sv $f }
set gen_args {}
foreach g $generics { lappend gen_args -generic $g }
synth_design -top $top -part $part -flatten_hierarchy none {*}$gen_args
proc jstr {s} { return "\"[string map {\\ \\\\ \" \\\"} $s]\"" }
set f [open $outj w]
puts $f "\{\"tool\": [jstr [version -short]], \"netlist\": \"synth_design -flatten_hierarchy none\","
puts $f " \"hier\": \["
set rows {}
foreach c [get_cells -hierarchical -filter {IS_PRIMITIVE == 0}] {
    lappend rows "  \{\"path\": [jstr $c], \"module\": [jstr [get_property ORIG_REF_NAME $c]]\}"
}
puts $f [join $rows ",\n"]
puts $f " \],"
puts $f " \"pins\": \["
set rows {}
foreach c [get_cells -hierarchical -filter {IS_PRIMITIVE == 0}] {
    set k [string last "/" $c]
    set open [expr {$k < 0}]
    if {!$open} {
        set pc [get_cells -quiet [string range $c 0 [expr {$k - 1}]]]
        set open [expr {[llength $pc] && [lsearch -exact $genmods [get_property ORIG_REF_NAME $pc]] >= 0}]
    }
    if {!$open} { continue }
    foreach p [get_pins -quiet -of_objects $c] {
        set n [get_nets -quiet -boundary_type upper -of_objects $p]
        if {![llength $n]} {
            set n ""                                                     ;# the port exists but nothing connects to it here
        } else {
            set n [lindex $n 0]
            if {[get_property TYPE $n] in {GROUND POWER}} { set n "" }   ;# a constant: not a connection between blocks
        }
        lappend rows "  \{\"pin\": [jstr $p], \"dir\": [jstr [get_property DIRECTION $p]], \"net\": [jstr $n]\}"
    }
}
puts $f [join $rows ",\n"]
puts $f " \]\}"
close $f
