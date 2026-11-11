# measure.tcl: one variant of the brief 24 reference controller, out-of-context on xc7a100tcsg324-1 (or $FSM_PART), Vivado 2025.2.
#   vivado -mode batch -source measure.tcl -tclargs <name> <top> "<GENERIC=v ...>" <period ns> <fsm_extraction> <impl 0|1> <out dir> <mc N|0>
# Writes <out>/<name>.kv (key value lines: LUT, FF, flop types, control sets, FSM log lines, slack per path group, logic levels)
# and, with impl=1, the same after opt/place/route (suffix _route). mc N>1 adds the brief 20 multicycle (setup N, hold N-1) on the
# FSM's own registers (the state and counter registers have a real enable, `ce`).
set th [expr {[info exists ::env(FDA_VIVADO_THREADS)] ? $::env(FDA_VIVADO_THREADS) : 1}]
set_param general.maxThreads $th
set_param synth.maxThreads $th
catch {set_param chipscope.maxJobs 1}
lassign $argv name top generics period extraction impl out mc
set part [expr {[info exists ::env(FSM_PART)] ? $::env(FSM_PART) : "xc7a100tcsg324-1"}]
file mkdir $out
set here [file dirname [file normalize [info script]]]
foreach f {fsm_front ctl_sep ctl_mono top_ratio top_cdc} { read_verilog -sv $here/rtl/$f.sv }
set gen {}
foreach g $generics { lappend gen -generic $g }
set cmd [list synth_design -top $top -part $part -mode out_of_context -fsm_extraction $extraction {*}$gen]
set rc [catch {eval $cmd} msg]
if {$rc} { puts "SYNTH FAILED: $msg"; exit 1 }
set kv [open $out/$name.kv w]
proc put {k v} { global kv; puts $kv "$k $v" }
proc count_ref {pat} { return [llength [get_cells -hier -filter "REF_NAME =~ $pat"]] }

# constraints
set ports_in  [get_ports -quiet -filter {DIRECTION == IN && NAME !~ clk* && NAME !~ aclk && NAME != rst_n}]
set ports_out [get_ports -quiet -filter {DIRECTION == OUT}]
create_clock -name clk -period $period [get_ports clk]
if {[llength [get_ports -quiet aclk]]} { create_clock -name aclk -period [expr {$period * 1.3}] [get_ports aclk] }
if {[llength $ports_in]}  { set_input_delay -clock clk 0.5 $ports_in }
if {[llength $ports_out]} { set_output_delay -clock clk 0.5 $ports_out }
set_input_delay -clock clk 0.5 [get_ports rst_n]
set fsm [get_cells -quiet -hier -filter {REF_NAME =~ FD* && (NAME =~ *st_reg* || NAME =~ *cnt_reg* || NAME =~ *g_zq* || NAME =~ *u_o*)}]
if {$mc > 1} {
    set_multicycle_path $mc -setup -from $fsm -to $fsm
    set_multicycle_path [expr {$mc - 1}] -hold -from $fsm -to $fsm
    put MC_REGS [llength $fsm]
}
proc grp_slack {from to} {
    set p [get_timing_paths -quiet -max_paths 1 -nworst 1 -from $from -to $to]
    if {[llength $p] == 0} { return NA }
    return [get_property SLACK $p]
}
proc grp_levels {from to} {
    set p [get_timing_paths -quiet -max_paths 1 -nworst 1 -from $from -to $to]
    if {[llength $p] == 0} { return NA }
    return [get_property LOGIC_LEVELS $p]
}
proc measure {sfx} {
    global ports_in ports_out period
    set allreg [all_registers]
    put "LUT$sfx" [expr {[count_ref LUT1] + [count_ref LUT2] + [count_ref LUT3] + [count_ref LUT4] + [count_ref LUT5] + [count_ref LUT6]}]
    put "FF$sfx" [llength [get_cells -hier -filter {IS_SEQUENTIAL && REF_NAME =~ FD*}]]
    foreach t {FDRE FDCE FDPE FDSE} { put "${t}$sfx" [count_ref $t] }
    put "CARRY$sfx" [count_ref CARRY4]
    set cs [report_control_sets -verbose -return_string]
    if {[regexp {Total control sets\s*\|\s*(\d+)} $cs -> n]} { put "CTRLSETS$sfx" $n }
    if {[llength [all_inputs]]} {}
    global fsm
    put "WNS_r2r$sfx" [grp_slack $allreg $allreg]
    if {[llength $fsm]} { put "WNS_fsm$sfx" [grp_slack $fsm $fsm] }
    put "LVL_r2r$sfx" [grp_levels $allreg $allreg]
    if {[llength $ports_in]}  { put "WNS_in2r$sfx" [grp_slack $ports_in $allreg]; put "LVL_in2r$sfx" [grp_levels $ports_in $allreg] }
    if {[llength $ports_out]} { put "WNS_r2out$sfx" [grp_slack $allreg $ports_out]; put "LVL_r2out$sfx" [grp_levels $allreg $ports_out]
                                put "WNS_in2out$sfx" [grp_slack $ports_in $ports_out] }
    set p [get_timing_paths -quiet -max_paths 1 -setup]
    if {[llength $p]} { put "WNS$sfx" [get_property SLACK $p] }
    set p [get_timing_paths -quiet -max_paths 1 -hold]
    if {[llength $p]} { put "WHS$sfx" [get_property SLACK $p] }
}
measure ""
if {[string match cdc_* $name]} {
    # brief 16's gate inputs: report_cdc rows and every asynchronous register-to-register path (flow/cdc_structure.py)
    file mkdir $out/$name.cdc
    report_cdc -details -file $out/$name.cdc/cdc_synth.rpt
    source [file normalize $here/../../../cdc_paths.tcl]
    cdc_dump_paths $out/$name.cdc/cdc_paths_synth.rpt
}
write_checkpoint -force $out/$name.dcp
if {$impl} {
    opt_design
    place_design
    route_design
    measure "_route"
}
close $kv
exit 0
