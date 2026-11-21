# run_point.tcl (brief 151): one point of the partition sweep, out of context, non-project. NOT RUN YET (Vivado runs are queued in
# _handoff/fpga_agent/vivado_later_queue.md, decision 27); written against the commands of flow/ipchar.tcl and checked only for
# Tcl syntax. Environment (set by sweep.py): PART, T_NS, HS, STAGES, KEEP, RETIME, DIST, NM, W, D, OUT (directory), THREADS.
# Vivado is run with general.maxThreads 1, synth.maxThreads 1 (house rules); place and route at default directives.
set part   $::env(PART)
set t_ns   $::env(T_NS)
set out    $::env(OUT)
file mkdir $out
set_param general.maxThreads 1
set_param synth.maxThreads 1
set root [file normalize [file dirname [info script]]/..]
set srcs [list $root/partition/rtl/part_stage.sv $root/partition/rtl/part_sys.sv $root/ip_lib/pipe_reg/rtl/pipe_reg.sv \
               $root/ip_lib/pipe_reg/rtl/pipe_reg_slice.sv $root/ip_lib/credit_chan/rtl/credit_chan.sv]
read_verilog -sv $srcs
set t0 [clock seconds]
set args [list -top part_sys -part $part -mode out_of_context -flatten_hierarchy rebuilt \
          -generic W=$::env(W) -generic NM=$::env(NM) -generic D=$::env(D) -generic HS=$::env(HS) -generic STAGES=$::env(STAGES) \
          -generic KEEP=$::env(KEEP)]
if {$::env(RETIME) == 1} { lappend args -retiming }
synth_design {*}$args
set t_synth [expr {[clock seconds] - $t0}]
# clock and a virtual clock for the ports, so that a point with no registers still has timed (port to port) paths
create_clock -name aclk -period $t_ns [get_ports aclk]
create_clock -name vclk -period $t_ns
set_input_delay  -clock vclk 0 [get_ports -filter {DIRECTION == IN && NAME != aclk}]
set_output_delay -clock vclk 0 [get_ports -filter {DIRECTION == OUT}]
# pblocks: stage i in one clock region on the line from region A (lowest column and row) to region B (highest), DIST in 0..1
set regs [get_clock_regions]
set cols {}; set rows {}
foreach r $regs { lappend cols [get_property COLUMN_INDEX $r]; lappend rows [get_property ROW_INDEX $r] }
set c0 [tcl::mathfunc::min {*}$cols]; set c1 [tcl::mathfunc::max {*}$cols]
set r0 [tcl::mathfunc::min {*}$rows]; set r1 [tcl::mathfunc::max {*}$rows]
set dist $::env(DIST)
set nm $::env(NM)
for {set i 0} {$i < $nm && $dist >= 0} {incr i} {
    set f [expr {$nm > 1 ? double($i) / ($nm - 1) * $dist : 0.0}]
    set c [expr {int(round($c0 + ($c1 - $c0) * $f))}]
    set r [expr {int(round($r0 + ($r1 - $r0) * $f))}]
    set cr [get_clock_regions X${c}Y${r}]
    if {$cr eq ""} { set cr [lindex $regs 0] }
    create_pblock pb_$i
    resize_pblock pb_$i -add $cr
    add_cells_to_pblock pb_$i [get_cells -hier -filter "NAME =~ g_m\\\[$i\\\].*"]
}
set t1 [clock seconds]
opt_design
place_design
route_design
set t_impl [expr {[clock seconds] - $t1}]
# results
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1]]
set util [report_utilization -return_string]
set fh [open $out/point.json w]
puts $fh "\{\"part\": \"$part\", \"t_ns\": $t_ns, \"wns_ns\": $wns, \"synth_s\": $t_synth, \"impl_s\": $t_impl,"
# the boundary paths: from the registers of boundary i to those of boundary i+1 (the logic of stage i and the route to it)
set worst_b ""; set worst_slack 1e9; set share ""
for {set i 0} {$i < $nm} {incr i} {
    set from [get_cells -hier -filter "NAME =~ g_b\\\[$i\\\].*" -quiet]
    set to   [get_cells -hier -filter "NAME =~ g_b\\\[[expr {$i + 1}]\\\].*" -quiet]
    if {$from eq "" || $to eq ""} { continue }
    set p [get_timing_paths -from $from -to $to -max_paths 1 -quiet]
    if {$p eq ""} { continue }
    set s [get_property SLACK $p]
    if {$s < $worst_slack} {
        set worst_slack $s; set worst_b $i
        set txt [report_timing -from $from -to $to -max_paths 1 -return_string]
        regexp {Data Path Delay:\s+([0-9.]+)ns\s+\(logic ([0-9.]+)ns \(([0-9.]+)%\)\s+route ([0-9.]+)ns \(([0-9.]+)%\)\)} $txt -> dp lg lgp rt rtp
        set share $rtp
    }
}
puts $fh "\"boundary_worst_index\": \"$worst_b\", \"boundary_worst_slack_ns\": $worst_slack, \"boundary_route_share_pct\": \"$share\","
regexp {CLB LUTs\s*\|\s*([0-9]+)} $util -> luts
regexp {CLB Registers\s*\|\s*([0-9]+)} $util -> ffs
if {![info exists luts]} { regexp {Slice LUTs\s*\|\s*([0-9]+)} $util -> luts }
if {![info exists ffs]}  { regexp {Slice Registers\s*\|\s*([0-9]+)} $util -> ffs }
puts $fh "\"lut\": $luts, \"ff\": $ffs\}"
close $fh
report_timing_summary -file $out/timing_summary.rpt
write_checkpoint -force $out/routed.dcp
