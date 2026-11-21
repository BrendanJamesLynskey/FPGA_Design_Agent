# xvc_capture.tcl (brief 131, NOT YET RUN): the Vivado hardware-manager side of the dbg_xvc board test. Run in batch by xvc_board_session.sh; arguments: host:port of the XVC server, the probes file
# (.ltx) of the build, the record file to write (JSON). It never opens the JTAG cable's hardware server target: only open_hw_target -xvc_url. Reads and captures only.
set xvc [lindex $argv 0]
set ltx [lindex $argv 1]
set out [lindex $argv 2]
proc js_bool {v} { return [expr {$v ? "true" : "false"}] }
set t0 [clock milliseconds]
open_hw_manager
connect_hw_server
open_hw_target -xvc_url $xvc
set dev [lindex [get_hw_devices] 0]
set_property PROBES.FILE $ltx $dev
set_property FULL_PROBES.FILE $ltx $dev
refresh_hw_device $dev
set ilas [get_hw_ilas -of_objects $dev]
set connect_s [expr {([clock milliseconds] - $t0) / 1000.0}]
set n [llength $ilas]
set ila [lindex $ilas 0]
set width [expr {$n ? [llength [get_hw_probes -of_objects $ila]] : 0}]
set probe [lindex [get_hw_probes -of_objects $ila] 0]
# T3: a trigger on pcs_lock = 1 (bit 2 of the probe, docs/dbg_xvc.md) must stay armed for 30 s with the laser off
set_property CONTROL.TRIGGER_POSITION 512 $ila
set held 0
if {$n} {
    set_property DISPLAY_RADIX BINARY $probe
    set_property TRIGGER_COMPARE_VALUE "eq38'b[string repeat X 35]1XX" $probe
    run_hw_ila $ila
    set t1 [clock milliseconds]
    while {([clock milliseconds] - $t1) < 30000} {
        after 1000
        if {[get_property STATUS $ila] ne "Waiting for Trigger"} break
    }
    set held [expr {([clock milliseconds] - $t1) / 1000.0}]
    if {[get_property STATUS $ila] eq "Waiting for Trigger"} { stop_hw_ila $ila }
}
# T3/T4: 20 immediate captures, each uploaded and read back
set caps {}
set rx_los -1; set mod_abs -1; set tx_fault -1; set pgood -1
if {$n} {
    set_property TRIGGER_COMPARE_VALUE "eq38'b[string repeat X 38]" $probe
    for {set i 0} {$i < 20} {incr i} {
        run_hw_ila -trigger_now $ila
        wait_on_hw_ila $ila
        set d [upload_hw_ila_data $ila]
        set ns [get_property DATA_DEPTH $d]
        lappend caps "{\"ok\": true, \"samples\": $ns}"
        if {$i == 0} {
            write_hw_ila_data -csv_file ${out}.first.csv -force $d
        }
    }
}
set fh [open $out w]
puts $fh "{\"xvc\": {\"connected\": [js_bool [expr {$n > 0}]], \"ila_count\": $n, \"probe_width\": $width, \"connect_s\": $connect_s},"
puts $fh " \"held_trigger_s\": $held, \"captures\": \[[join $caps {, }]\]}"
close $fh
close_hw_manager
