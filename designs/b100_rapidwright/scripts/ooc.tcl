# ooc.tcl: implement one block out of context in a pblock, lock it, save it (brief 100, capability 1: the pre-implemented block).
#   B100_PART, B100_TOP, B100_SRC, B100_PBLOCK (e.g. SLICE_X25Y70:SLICE_X36Y89, empty = no pblock), B100_PERIOD, B100_DIRECTIVE, B100_OUT
# Writes <out>_ooc.dcp (placed, routed, locked at routing level) and <out>_run.json.
source [file join [file dirname [info script]] ../../../flow/rw/common.tcl]
b100_threads
set out    $::env(B100_OUT)
set period [env_or B100_PERIOD 3.0]
set times [dict create]
set t0 [clock milliseconds]
foreach f $::env(B100_SRC) { if {[string match *.sv $f]} { read_verilog -sv $f } else { read_verilog $f } }
synth_design -top $::env(B100_TOP) -part $::env(B100_PART) -mode out_of_context -flatten_hierarchy rebuilt
lap synth
create_clock -period $period [get_ports clk]
if {[env_or B100_PBLOCK ""] ne ""} {
    create_pblock pb_blk
    resize_pblock pb_blk -add $::env(B100_PBLOCK)
    add_cells_to_pblock pb_blk [get_cells -hier -filter {PRIMITIVE_LEVEL != MACRO}]
}
opt_design
place_design -directive [env_or B100_DIRECTIVE Default]
lap place
route_design
lap route
write_run_json $out $times $::env(B100_PART) $period
lock_design -level routing
write_checkpoint -force ${out}_ooc.dcp
