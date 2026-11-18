# stamp.tcl: the top of capability 1 in Vivado (brief 100). Two modes, same top (rtl/reloc_top.sv, four copies of pcs_unit named c0 .. c3):
#   B100_MODE=stamp: pcs_tx is a black box; each copy g[i].u_b gets its pre-implemented checkpoint B100_BLOCKS (space-separated, one per copy)
#                    by read_checkpoint -cell; Vivado places the rest and routes the connections. The blocks keep placement and routing.
#   B100_MODE=alone: pcs_tx is real RTL; each copy gets a pblock B100_PBLOCKS (space-separated site ranges, one per copy); Vivado places
#                    and routes everything.
# B100_UNTIL=place stops after placement (the checkpoint then goes to RapidWright, see run_c1.sh). Other parameters: B100_PART, B100_SRC (the rtl files), B100_PERIOD, B100_DIRECTIVE, B100_OUT. Writes <out>_routed.dcp and <out>_run.json.
source [file join [file dirname [info script]] ../../../flow/rw/common.tcl]
source [file join [file dirname [info script]] blocks.tcl]
b100_threads
set out    $::env(B100_OUT)
set period [env_or B100_PERIOD 3.4]
set mode   $::env(B100_MODE)
set n      4
set times [dict create]
set t0 [clock milliseconds]
foreach f $::env(B100_SRC) { if {[string match *.sv $f]} { read_verilog -sv $f } else { read_verilog $f } }
synth_design -top reloc_top -part $::env(B100_PART) -flatten_hierarchy rebuilt 
lap synth
create_clock -period $period [get_ports clk]
set_property SEVERITY {Warning} [get_drc_checks {NSTD-1 UCIO-1}]
if {$mode eq "stamp"} {
    set i 0
    foreach b $::env(B100_BLOCKS) {
        read_checkpoint -cell "c$i" $b
        incr i
    }
} else {
    set i 0
    foreach pb $::env(B100_PBLOCKS) {
        create_pblock pb_$i
        resize_pblock pb_$i -add $pb
        add_cells_to_pblock pb_$i [get_cells "c$i"]
        incr i
    }
}
opt_design
place_design -directive [env_or B100_DIRECTIVE Default]
lap place
write_checkpoint -force ${out}_placed.dcp
if {[env_or B100_UNTIL route] eq "place"} { return }
route_design
lap route
write_checkpoint -force ${out}_routed.dcp
write_run_json $out $times $::env(B100_PART) $period
block_paths $out
report_timing -setup -max_paths 3 -file ${out}_timing.rpt
