# measure_io.tcl: the reference controller on real pins (non-OOC), placed and routed on xc7a100tcsg324-1, Vivado 2025.2.
#   vivado -mode batch -source measure_io.tcl -tclargs <name> "<GENERIC=v ...>" <iob 0|1> <out dir>
# For each output port: the cell that drives the pad's buffer (a flop or a LUT), its site and whether the flop sits in the I/O block
# (OLOGIC / ILOGIC), and the routed clock-to-output (data path delay incl. the output buffer); the same for each input port's first cell.
set th [expr {[info exists ::env(FDA_VIVADO_THREADS)] ? $::env(FDA_VIVADO_THREADS) : 1}]
set_param general.maxThreads $th
set_param synth.maxThreads $th
lassign $argv name generics iob out
file mkdir $out
set here [file dirname [file normalize [info script]]]
foreach f {fsm_front ctl_sep top_io} { read_verilog -sv $here/rtl/$f.sv }
read_xdc $here/xdc/top_io.xdc
set gen {}; foreach g $generics { lappend gen -generic $g }
synth_design -top top_io -part xc7a100tcsg324-1 {*}$gen
if {$iob} {
    set_property IOB TRUE [get_ports {cmd_ready cmd_ack bus_req bus_addr_v bus_valid bus_last rsp_valid rsp_err}]
    catch {set_property IOB TRUE [get_cells -hier -filter {REF_NAME =~ FD* && NAME =~ *u_i*}]}
}
set_property SEVERITY {Warning} [get_drc_checks {NSTD-1 UCIO-1}]
opt_design; place_design; route_design
set kv [open $out/$name.kv w]
set outs {cmd_ready cmd_ack bus_req bus_addr_v bus_valid bus_last rsp_valid rsp_err}
foreach p $outs {
    set pad [get_ports $p]
    set obuf [get_cells -of [get_nets -of $pad]]
    set drv_pin [get_pins -leaf -of [get_nets -of [get_pins [get_property NAME $obuf]/I]] -filter {DIRECTION == OUT}]
    set drv [get_cells -of $drv_pin]
    set path [get_timing_paths -quiet -to $pad -max_paths 1]
    set d [expr {[llength $path] ? [get_property DATAPATH_DELAY $path] : "NA"}]
    set lv [expr {[llength $path] ? [get_property LOGIC_LEVELS $path] : "NA"}]
    set sl [expr {[llength $path] ? [get_property SLACK $path] : "NA"}]
    puts $kv "OUT $p [get_property REF_NAME $drv] [get_property SITE $drv] [get_property BEL $drv] datapath=$d levels=$lv slack=$sl"
}
foreach p {cmd_valid gnt ack nack rsp_ready} {
    set pad [get_ports $p]
    set path [get_timing_paths -quiet -from $pad -max_paths 1]
    set d [expr {[llength $path] ? [get_property DATAPATH_DELAY $path] : "NA"}]
    set ep [expr {[llength $path] ? [get_property ENDPOINT_PIN $path] : "NA"}]
    set sl [expr {[llength $path] ? [get_property SLACK $path] : "NA"}]
    puts $kv "IN $p $ep datapath=$d slack=$sl"
}
foreach t {setup hold} {
    set path [get_timing_paths -quiet -max_paths 1 -$t]
    puts $kv "WS_$t [get_property SLACK $path]"
}
close $kv
report_timing_summary -file $out/$name.timing.rpt
exit 0
