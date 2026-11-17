# common.tcl: helpers shared by the brief 100 Vivado scripts.
proc env_or {k d} { if {[info exists ::env($k)] && $::env($k) ne ""} { return $::env($k) } else { return $d } }
proc b100_threads {} {
    set n [env_or B100_THREADS 1]
    set_param general.maxThreads $n
    set_param synth.maxThreads $n
    set_param chipscope.maxJobs 1
}
proc lap {name} {
    upvar t0 t0 times times
    set n [clock milliseconds]
    dict set times $name [expr {($n - $t0) / 1000.0}]
    set t0 $n
}
# The referee numbers of the open design: worst setup and hold slack of the whole design, the worst setup slack per clock group
# is in the timing report. Resources from report_utilization -return_string parsed by the caller in Python; here only the counts.
proc write_run_json {out times part period} {
    set wns [get_property SLACK [lindex [get_timing_paths -setup -max_paths 1] 0]]
    set whs [get_property SLACK [lindex [get_timing_paths -hold -max_paths 1] 0]]
    set lut [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
    set ff  [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]
    set f [open ${out}_run.json w]
    set tj [join [lmap {k v} $times {format {"%s": %s} $k $v}] {, }]
    puts $f "{\"vivado\": \"[version -short]\", \"part\": \"$part\", \"period_ns\": $period, \"wns_ns\": $wns, \"whs_ns\": $whs, \"lut\": $lut, \"ff\": $ff, \"times_s\": {$tj}}"
    close $f
}
