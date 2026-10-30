# ila_capture.tcl: arm the ILA of an already-programmed board, capture, export.
#
#   vivado -mode batch -source flow/ila_capture.tcl -tclargs <serial> <file.ltx> <out dir> <plan.tcl>
#
# Run by flow/bringup.py, which writes plan.tcl (one entry per capture) and drives
# the board over the UART in step with this script through small files in <out dir>:
#   <name>.go     written by Python when the board is set up for the capture
#   <name>.armed  written here once run_hw_ila has returned (Python then sends the stimulus)
#   <name>.csv / <name>.vcd   the uploaded capture (write_hw_ila_data)
#   <name>.done   written here after the export (or <name>.timeout if it never triggered)
# plan.tcl sets fda_depth and appends to fda_captures:
#   lappend fda_captures [list <name> <AND|OR> <trigger position> [list [list <probe port> <value>] ...]]
# Each named probe port must equal <value> (an integer); ports not named are don't-care.
#
# One ILA probe port can show up as several hw_probes: the .ltx names probes after
# nets, and a register bus's bits can sit on nets with different names after
# synthesis (u_dut/count_reg[*]/Q became six hw_probes). Each hw_probe's MAP property
# says which port bits it carries (e.g. probe8[6:3]), so a port's compare value is cut
# into per-hw_probe binary compares here, and hw_probes.txt records every MAP so
# flow/ila.py can put the CSV columns back together.
#
# Hardware-manager Tcl sequence (trigger set-up, arm/wait/upload, -timeout in minutes,
# CSV/VCD export, no display_hw_ila_data in batch) adapted from AMD's ross-ai-assistant
# skill hw-ila-debug (https://github.com/Xilinx/ross-ai-assistant, commit dce0fb9,
# skills/hw-ila-debug/SKILL.md and REFERENCE.md; MIT, Copyright (c) 2026 Advanced Micro Devices, Inc.).
# It programs nothing: the board must already hold the ILA build (flow/program.py ... ila).

lassign $argv serial ltx out plan
if {$plan eq ""} { error "usage: -tclargs <serial> <file.ltx> <out dir> <plan.tcl>" }
set fda_depth 1024
set fda_captures {}
source $plan

proc fda_wait_file {path timeout_s} {
    set t0 [clock seconds]
    while {![file exists $path]} {
        if {[clock seconds] - $t0 > $timeout_s} { return 0 }
        after 100
    }
    return 1
}
proc fda_touch {path {text ""}} { set f [open $path w]; puts $f $text; close $f }

set_param general.maxThreads 1
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets -quiet "*/Digilent/${serial}*"]
if {[llength $targets] != 1} { error "ila_capture.tcl: expected exactly one target with the given serial, found [llength $targets]" }
open_hw_target $targets
set devs [get_hw_devices -quiet]
if {[llength $devs] != 1 || [get_property PART [lindex $devs 0]] ne "xc7a100t"} {
    error "ila_capture.tcl: expected one xc7a100t on the chain, found $devs"
}
set dev [lindex $devs 0]
current_hw_device $dev
set_property PROBES.FILE $ltx $dev
set_property FULL_PROBES.FILE $ltx $dev
refresh_hw_device $dev
set ilas [get_hw_ilas -quiet -of_objects $dev]
if {[llength $ilas] != 1} { error "ila_capture.tcl: expected one ILA core, found [llength $ilas] (is the ILA build programmed?)" }
set ila [lindex $ilas 0]

# probe port -> its hw_probes, and a map file for the CSV columns
proc fda_map_bits {map} {
    # "probe8[6:3]" (or a space-separated list of such) -> port bit numbers, MSB first
    set bits {}
    foreach tok $map {
        if {[regexp {^probe\d+\[(\d+):(\d+)\]$} $tok -> hi lo]} {
            for {set i $hi} {$i >= $lo} {incr i -1} { lappend bits $i }
        } elseif {[regexp {^probe\d+\[(\d+)\]$} $tok -> i]} {
            lappend bits $i
        } else {
            error "ila_capture.tcl: cannot read hw_probe MAP '$map'"
        }
    }
    return $bits
}
set map [open $out/hw_probes.txt w]
set nprobes 0
foreach p [get_hw_probes -of_objects $ila] {
    set port [get_property PROBE_PORT $p]
    set m [get_property MAP $p]
    lappend probes($port) [list $p [fda_map_bits $m]]
    puts $map "$port [get_property WIDTH $p] [join $m ,] $p"
    incr nprobes
}
close $map
puts "FDA-ILA $ila depth_max=[get_property STATIC.MAX_DATA_DEPTH $ila] ports=[array size probes] hw_probes=$nprobes"

foreach cap $fda_captures {
    lassign $cap name cond pos compares
    if {![fda_wait_file $out/$name.go 300]} { error "ila_capture.tcl: no $name.go from bringup.py within 300 s" }
    foreach port [array names probes] {
        foreach pb $probes($port) {
            lassign $pb p bits
            set_property TRIGGER_COMPARE_VALUE "eq[llength $bits]'b[string repeat X [llength $bits]]" $p
        }
    }
    catch {set_property CONTROL.TRIGGER_MODE BASIC_ONLY $ila}
    # read-only when the core was built without capture qualification (C_EN_STRG_QUAL false)
    catch {set_property CONTROL.CAPTURE_MODE ALWAYS $ila}
    set_property CONTROL.WINDOW_COUNT 1 $ila
    set_property CONTROL.DATA_DEPTH $fda_depth $ila
    set_property CONTROL.TRIGGER_POSITION $pos $ila
    set_property CONTROL.TRIGGER_CONDITION $cond $ila
    foreach c $compares {
        lassign $c port value
        foreach pb $probes($port) {
            lassign $pb p bits
            set b ""
            foreach i $bits { append b [expr {($value >> $i) & 1}] }
            set_property TRIGGER_COMPARE_VALUE "eq[llength $bits]'b$b" $p
        }
    }
    run_hw_ila $ila
    fda_touch $out/$name.armed [get_property STATUS.CORE_STATUS $ila]
    puts "FDA-ARMED $name [get_property STATUS.CORE_STATUS $ila]"
    # -timeout is in minutes
    if {[catch {wait_on_hw_ila -timeout 1 $ila} msg]} {
        fda_touch $out/$name.timeout $msg
        puts "FDA-TIMEOUT $name $msg"
        catch {reset_hw_ila $ila}
        continue
    }
    set data [upload_hw_ila_data $ila]
    write_hw_ila_data -force -csv_file $out/$name.csv $data
    write_hw_ila_data -force -vcd_file $out/$name.vcd $data
    fda_touch $out/$name.done [get_property STATUS.CORE_STATUS $ila]
    puts "FDA-CAPTURED $name"
}
puts "FDA-CAPTURE-DONE"
close_hw_target
disconnect_hw_server
