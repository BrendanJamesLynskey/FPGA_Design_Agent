# stamp.tcl: the top of capability 1 in Vivado (brief 100). Two modes, same top (rtl/reloc_top.sv, four copies of pcs_tx named c0/u_b .. c3/u_b):
#   B100_MODE=stamp: pcs_tx is a black box; each copy g[i].u_b gets its pre-implemented checkpoint B100_BLOCKS (space-separated, one per copy)
#                    by read_checkpoint -cell; Vivado places the rest and routes the connections. The blocks keep placement and routing.
#   B100_MODE=alone: pcs_tx is real RTL; each copy gets a pblock B100_PBLOCKS (space-separated site ranges, one per copy); Vivado places
#                    and routes everything.
# Other parameters: B100_PART, B100_SRC (the rtl files), B100_PERIOD, B100_DIRECTIVE, B100_OUT. Writes <out>_routed.dcp and <out>_run.json.
source [file join [file dirname [info script]] ../../../flow/rw/common.tcl]
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
        read_checkpoint -cell "c$i/u_b" $b
        incr i
    }
} else {
    set i 0
    foreach pb $::env(B100_PBLOCKS) {
        create_pblock pb_$i
        resize_pblock pb_$i -add $pb
        add_cells_to_pblock pb_$i [get_cells "c$i/u_b"]
        incr i
    }
}
opt_design
place_design -directive [env_or B100_DIRECTIVE Default]
lap place
route_design
lap route
write_checkpoint -force ${out}_routed.dcp
write_run_json $out $times $::env(B100_PART) $period
# The block-internal paths: the worst setup path to each endpoint register inside each copy, with the path's data delay, slack and
# logic levels. Endpoint names are relative to the copy so that copies compare endpoint by endpoint.
set f [open ${out}_blocks.csv w]
puts $f "copy,endpoint,data_path_delay_ns,slack_ns,logic_levels"
for {set i 0} {$i < $n} {incr i} {
    set cells [get_cells "c$i/u_b/*"]
    set prefix "c$i/u_b/"
    foreach p [get_timing_paths -setup -from [all_registers -clock_pins -of_objects $cells] -to [all_registers -data_pins -of_objects $cells] -max_paths 2000 -nworst 1 -unique_pins] {
        set e [string map [list $prefix ""] [get_property ENDPOINT_PIN $p]]
        puts $f "$i,$e,[get_property DATAPATH_DELAY $p],[get_property SLACK $p],[get_property LOGIC_LEVELS $p]"
    }
}
close $f
report_timing -setup -max_paths 3 -file ${out}_timing.rpt
