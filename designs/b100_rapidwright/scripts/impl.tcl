# impl.tcl: synthesis, placement and routing with Vivado alone, one run per call (brief 100). Parameters come from the environment.
#   B100_PART, B100_TOP, B100_SRC (space-separated files), B100_XDC (optional), B100_OUT (output prefix, no extension),
#   B100_PERIOD (ns, default 4.0), B100_DIRECTIVE (place_design directive, default Default), B100_THREADS (default 1)
#   B100_FROM: synth (default) | a synth checkpoint to start from (skips synthesis)
# Writes <out>_synth.dcp (when synthesised here), <out>_placed.dcp, <out>_routed.dcp, <out>_run.json.
source [file join [file dirname [info script]] common.tcl]
b100_threads
set part   $::env(B100_PART)
set out    $::env(B100_OUT)
set period [env_or B100_PERIOD 4.0]
set dir    [env_or B100_DIRECTIVE Default]
set from   [env_or B100_FROM synth]
set times [dict create]
set t0 [clock milliseconds]
if {$from eq "synth"} {
    foreach f $::env(B100_SRC) { if {[string match *.sv $f]} { read_verilog -sv $f } else { read_verilog $f } }
    if {[info exists ::env(B100_XDC)] && $::env(B100_XDC) ne ""} { read_xdc $::env(B100_XDC) }
    synth_design -top $::env(B100_TOP) -part $part -flatten_hierarchy rebuilt
    lap synth
    write_checkpoint -force ${out}_synth.dcp
} else {
    open_checkpoint $from
}
set_property SEVERITY {Warning} [get_drc_checks {NSTD-1 UCIO-1}]
if {[llength [get_clocks -quiet]] == 0} { create_clock -period $period [get_ports clk] }
opt_design
place_design -directive $dir
lap place
write_checkpoint -force ${out}_placed.dcp
route_design
lap route
write_checkpoint -force ${out}_routed.dcp
write_run_json $out $times $part $period
