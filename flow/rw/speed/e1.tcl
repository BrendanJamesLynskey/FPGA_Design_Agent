# e1.tcl: brief 100B experiment 1, the build after a one-block edit, on reloc_top_edit (four blocks; c2 edited). One run per call.
#   B100_MODE = full   Vivado alone from RTL: synth, opt, place, route, a pblock per block (as designs/b100_rapidwright/scripts/stamp.tcl "alone")
#             = incr   as full, plus read_checkpoint -incremental B100_REF (Vivado's own incremental implementation, the fair rival)
#             = stamp  the top with four black boxes, B100_BLOCKS (four checkpoints, c0 .. c3) read with read_checkpoint -cell; Vivado places the
#                      rest and routes the connections (B100_UNTIL=place stops after placement, for the RapidWright completion route)
#   B100_PART, B100_SRC, B100_PBLOCKS (four ranges), B100_PERIOD (default 3.4), B100_OUT. Writes <out>_routed.dcp (or _placed.dcp), <out>_run.json.
source [file join [file dirname [info script]] ../common.tcl]
b100_threads
set out    $::env(B100_OUT)
set period [env_or B100_PERIOD 3.4]
set mode   $::env(B100_MODE)
set times [dict create]
set t0 [clock milliseconds]
foreach f $::env(B100_SRC) { if {[string match *.sv $f]} { read_verilog -sv $f } else { read_verilog $f } }
synth_design -top reloc_top_edit -part $::env(B100_PART) -flatten_hierarchy rebuilt
lap synth
create_clock -period $period [get_ports clk]
set_property SEVERITY {Warning} [get_drc_checks {NSTD-1 UCIO-1}]
if {$mode eq "stamp"} {
    set i 0
    foreach b $::env(B100_BLOCKS) { read_checkpoint -cell "c$i" $b; incr i }
} else {
    set i 0
    foreach pb $::env(B100_PBLOCKS) {
        create_pblock pb_$i
        resize_pblock pb_$i -add $pb
        add_cells_to_pblock pb_$i [get_cells "c$i"]
        incr i
    }
    if {$mode eq "incr"} { read_checkpoint -incremental $::env(B100_REF) }
}
lap setup
opt_design
place_design
lap place
write_checkpoint -force ${out}_placed.dcp
if {[env_or B100_UNTIL route] eq "place"} { return }
route_design
lap route
write_checkpoint -force ${out}_routed.dcp
write_run_json $out $times $::env(B100_PART) $period
set rs [report_route_status -return_string]
set f [open ${out}_route_status.txt w]; puts $f $rs; close $f
report_timing -setup -max_paths 3 -file ${out}_timing.rpt
if {$mode eq "incr"} { report_incremental_reuse -file ${out}_reuse.rpt }
